# -*- coding: utf-8 -*-
"""OpenAI-compatible agent streaming for ChatWeb."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI
from openai.types.chat.chat_completion_chunk import ChoiceDeltaToolCall

from ..models import ChatMessage
from ..tools import ChatTool, get_chat_tools
from .constants import (
    CHAT_AGENT_HISTORY_PROMPT,
    CHAT_AGENT_INSTRUCTIONS,
    DEFAULT_MODEL_ID,
    MAX_HISTORY_MESSAGES,
)

CHAT_TOOL_CALL_LIMIT = 4


@dataclass
class ChatToolEventPayload:
    tool_name: str
    tool_args: dict[str, Any]
    result: Any = None
    tool_call_id: str | None = None


@dataclass
class ChatRunEvent:
    event: str
    content: str | None = None
    reasoning_content: str | None = None
    tool: ChatToolEventPayload | None = None


async def stream_agent_events(
    prompt: str,
    *,
    user_id: str,
) -> AsyncIterator[ChatRunEvent]:
    agent = build_chat_agent()
    async for event in agent.arun(
        prompt,
        user_id=user_id,
    ):
        yield event


def build_chat_agent() -> "OpenAICompatibleChatAgent":
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    model_id = os.getenv("OPENAI_MODEL", DEFAULT_MODEL_ID)
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY")
    if not base_url:
        raise RuntimeError("Missing OPENAI_BASE_URL")

    return OpenAICompatibleChatAgent(
        client=AsyncOpenAI(api_key=api_key, base_url=base_url),
        model_id=model_id,
        tools=get_chat_tools(),
    )


class OpenAICompatibleChatAgent:
    """Small agent loop for OpenAI-compatible chat completion providers."""

    def __init__(
        self,
        *,
        client: AsyncOpenAI,
        model_id: str,
        tools: list[ChatTool] | None = None,
    ):
        self.client = client
        self.model_id = model_id
        self.tools = tools or []
        self.tool_specs = [tool.spec for tool in self.tools]
        self.tool_registry = {
            str(tool.spec.get("function", {}).get("name")): tool.handler
            for tool in self.tools
            if isinstance(tool.spec.get("function"), dict)
            and tool.spec.get("function", {}).get("name")
        }

    async def arun(
        self,
        prompt: str,
        *,
        user_id: str,
    ) -> AsyncIterator[ChatRunEvent]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": CHAT_AGENT_INSTRUCTIONS},
            {"role": "user", "content": prompt},
        ]
        tool_calls_used = 0

        while True:
            content_chunks: list[str] = []
            tool_call_deltas: list[dict[str, Any]] = []
            request_params: dict[str, Any] = {
                "model": self.model_id,
                "messages": messages,
                "stream": True,
                "stream_options": {"include_usage": True},
                "user": user_id,
            }
            if self.tool_specs and tool_calls_used < CHAT_TOOL_CALL_LIMIT:
                request_params["tools"] = self.tool_specs
                request_params["tool_choice"] = "auto"

            stream = await self.client.chat.completions.create(**request_params)

            async for chunk in stream:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta
                reasoning_delta = _extract_reasoning_delta(delta)
                if reasoning_delta:
                    yield ChatRunEvent(
                        event="RunReasoningContent",
                        reasoning_content=reasoning_delta,
                    )

                if delta.content is not None:
                    content_chunks.append(delta.content)
                    yield ChatRunEvent(event="RunContent", content=delta.content)

                if delta.tool_calls is not None:
                    _merge_tool_call_deltas(tool_call_deltas, delta.tool_calls)

            tool_calls = _finalize_tool_calls(tool_call_deltas)
            if not tool_calls:
                return

            messages.append(
                {
                    "role": "assistant",
                    "content": "".join(content_chunks) or None,
                    "tool_calls": tool_calls,
                }
            )

            for tool_call in tool_calls:
                tool_calls_used += 1
                result = self._execute_tool_call(
                    tool_call,
                    allowed=tool_calls_used <= CHAT_TOOL_CALL_LIMIT,
                )
                yield ChatRunEvent(
                    event="ToolCallStarted",
                    tool=ChatToolEventPayload(
                        tool_name=result.name,
                        tool_args=result.arguments,
                        tool_call_id=result.id,
                    ),
                )
                yield ChatRunEvent(
                    event="ToolCallCompleted",
                    tool=ChatToolEventPayload(
                        tool_name=result.name,
                        tool_args=result.arguments,
                        result=result.output,
                        tool_call_id=result.id,
                    ),
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": result.id,
                        "name": result.name,
                        "content": json.dumps(
                            result.output,
                            ensure_ascii=False,
                            default=str,
                        ),
                    }
                )

            if tool_calls_used >= CHAT_TOOL_CALL_LIMIT:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Tool call limit reached. Use the available tool results "
                            "to provide the final answer."
                        ),
                    }
                )

    def _execute_tool_call(
        self,
        tool_call: dict[str, Any],
        *,
        allowed: bool,
    ) -> "_ToolExecutionResult":
        function = tool_call.get("function") if isinstance(tool_call, dict) else None
        function = function if isinstance(function, dict) else {}
        name = str(function.get("name") or "unknown_tool")
        arguments = _load_tool_arguments(function.get("arguments"))
        tool_call_id = str(tool_call.get("id") or f"tool-{name}")

        if not allowed:
            return _ToolExecutionResult(
                id=tool_call_id,
                name=name,
                arguments=arguments,
                output={"error": "Tool call limit reached."},
            )

        tool = self.tool_registry.get(name)
        if tool is None:
            return _ToolExecutionResult(
                id=tool_call_id,
                name=name,
                arguments=arguments,
                output={"error": f"Unknown tool: {name}"},
            )

        try:
            output = tool(**arguments)
        except TypeError as exc:
            output = {"error": f"Invalid tool arguments: {exc}"}
        except Exception as exc:  # pragma: no cover - defensive tool isolation
            output = {"error": f"Tool execution failed: {exc}"}

        return _ToolExecutionResult(
            id=tool_call_id,
            name=name,
            arguments=arguments,
            output=output,
        )


@dataclass
class _ToolExecutionResult:
    id: str
    name: str
    arguments: dict[str, Any]
    output: Any


def build_agent_input(messages: list[ChatMessage]) -> str:
    recent_messages = messages[-MAX_HISTORY_MESSAGES:]
    lines = [
        CHAT_AGENT_HISTORY_PROMPT,
        "",
    ]
    for item in recent_messages:
        role = "User" if item.role == "user" else "Assistant"
        lines.append(f"{role}: {item.content}")
    return "\n".join(lines)


def _extract_reasoning_delta(delta: Any) -> str | None:
    if hasattr(delta, "reasoning_content") and delta.reasoning_content is not None:
        return str(delta.reasoning_content)
    if hasattr(delta, "reasoning") and delta.reasoning is not None:
        return str(delta.reasoning)
    if isinstance(getattr(delta, "model_extra", None), dict):
        model_extra = delta.model_extra
        for key in ("reasoning_content", "reasoning"):
            if model_extra.get(key) is not None:
                return str(model_extra[key])
    return None


def _merge_tool_call_deltas(
    tool_calls: list[dict[str, Any]],
    tool_call_deltas: list[ChoiceDeltaToolCall],
) -> None:
    """Build tool calls from streamed tool call data.

    This mirrors OpenAI chat delta handling: each delta is keyed by its
    streamed index, with function name and argument chunks accumulated until the
    model finishes the assistant turn.
    """
    for tool_call_delta in tool_call_deltas:
        index = tool_call_delta.index or 0
        while len(tool_calls) <= index:
            tool_calls.append({})

        entry = tool_calls[index]
        if not entry:
            entry["id"] = tool_call_delta.id
            entry["type"] = tool_call_delta.type or "function"
            entry["function"] = {
                "name": "",
                "arguments": "",
            }

        if tool_call_delta.id:
            entry["id"] = tool_call_delta.id
        if tool_call_delta.type:
            entry["type"] = tool_call_delta.type
        if tool_call_delta.function is not None:
            if tool_call_delta.function.name:
                entry["function"]["name"] = tool_call_delta.function.name
            if tool_call_delta.function.arguments:
                entry["function"]["arguments"] += tool_call_delta.function.arguments


def _finalize_tool_calls(tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    finalized: list[dict[str, Any]] = []
    for index, tool_call in enumerate(tool_calls):
        function = tool_call.get("function")
        if not isinstance(function, dict):
            continue
        name = function.get("name")
        if not name:
            continue
        finalized.append(
            {
                "id": str(tool_call.get("id") or f"call_{index + 1}"),
                "type": str(tool_call.get("type") or "function"),
                "function": {
                    "name": str(name),
                    "arguments": str(function.get("arguments") or "{}"),
                },
            }
        )
    return finalized


def _load_tool_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {"value": value}
    return parsed if isinstance(parsed, dict) else {"value": parsed}
