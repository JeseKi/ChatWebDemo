# -*- coding: utf-8 -*-
"""OpenAI Chat Completions provider adapters."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

from ..contracts import (
    LLMMessage,
    LLMProvider,
    LLMProviderEvent,
    LLMToolCall,
    load_tool_arguments,
)
from ..tools import AgentTool


class OpenAIChatCompletionsProvider(LLMProvider):
    name = "openai_chat"

    def __init__(
        self,
        *,
        client: AsyncOpenAI,
        model_id: str,
        stream_options: dict[str, Any] | None = None,
        max_output: int | None = None,
        reasoning_effort: str | None = None,
    ):
        self.client = client
        self.model_id = model_id
        self.stream_options = stream_options or {"include_usage": True}
        self.max_output = max_output
        self.reasoning_effort = reasoning_effort

    async def stream_turn(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[AgentTool],
        user_id: str,
        allow_tools: bool,
    ) -> AsyncIterator[LLMProviderEvent]:
        request_params: dict[str, Any] = {
            "model": self.model_id,
            "messages": [_to_chat_message(message) for message in messages],
            "stream": True,
            "stream_options": self.stream_options,
            "user": user_id,
        }
        if self.max_output is not None:
            request_params["max_completion_tokens"] = self.max_output
        if self.reasoning_effort:
            request_params["reasoning_effort"] = self.reasoning_effort
        if allow_tools:
            request_params["tools"] = [_openai_chat_tool(tool) for tool in tools]
            request_params["tool_choice"] = "auto"

        stream = await self.client.chat.completions.create(**request_params)
        tool_call_deltas: list[dict[str, Any]] = []

        async for chunk in stream:
            if not getattr(chunk, "choices", None):
                continue

            delta = chunk.choices[0].delta
            reasoning_delta = _extract_reasoning_delta(delta)
            if reasoning_delta:
                yield LLMProviderEvent(
                    type="reasoning_delta",
                    reasoning_content=reasoning_delta,
                )

            if getattr(delta, "content", None) is not None:
                yield LLMProviderEvent(type="content_delta", content=str(delta.content))

            if getattr(delta, "tool_calls", None) is not None:
                _merge_tool_call_deltas(tool_call_deltas, delta.tool_calls)

        for tool_call in _finalize_tool_calls(tool_call_deltas):
            yield LLMProviderEvent(type="tool_call", tool_call=tool_call)


def _to_chat_message(message: LLMMessage) -> dict[str, Any]:
    if message.role == "system":
        return {"role": "system", "content": message.content or ""}
    if message.role == "user":
        if not message.images:
            return {"role": "user", "content": message.content or ""}
        content: list[dict[str, Any]] = []
        if message.content:
            content.append({"type": "text", "text": message.content})
        for image in message.images:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": image.data_url},
                }
            )
        return {"role": "user", "content": content}
    if message.role == "tool":
        return {
            "role": "tool",
            "tool_call_id": message.tool_call_id or "",
            "name": message.name or "",
            "content": message.content or "",
        }

    payload: dict[str, Any] = {
        "role": "assistant",
        "content": message.content,
    }
    reasoning_content = message.provider_metadata.get("reasoning_content")
    if reasoning_content:
        payload["reasoning_content"] = reasoning_content
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.name,
                    "arguments": _arguments_as_json(tool_call),
                },
            }
            for tool_call in message.tool_calls
        ]
    return payload


def _openai_chat_tool(tool: AgentTool) -> dict[str, Any]:
    return tool.spec


def _arguments_as_json(tool_call: LLMToolCall) -> str:
    raw_arguments = tool_call.raw.get("arguments")
    if isinstance(raw_arguments, str):
        return raw_arguments
    import json

    return json.dumps(tool_call.arguments, ensure_ascii=False, default=str)


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
    tool_call_deltas: Any,
) -> None:
    for tool_call_delta in tool_call_deltas:
        index = getattr(tool_call_delta, "index", None) or 0
        while len(tool_calls) <= index:
            tool_calls.append({})

        entry = tool_calls[index]
        if not entry:
            entry["id"] = getattr(tool_call_delta, "id", None)
            entry["type"] = getattr(tool_call_delta, "type", None) or "function"
            entry["function"] = {"name": "", "arguments": ""}

        if getattr(tool_call_delta, "id", None):
            entry["id"] = tool_call_delta.id
        if getattr(tool_call_delta, "type", None):
            entry["type"] = tool_call_delta.type

        function = getattr(tool_call_delta, "function", None)
        if function is not None:
            if getattr(function, "name", None):
                entry["function"]["name"] = function.name
            if getattr(function, "arguments", None):
                entry["function"]["arguments"] += function.arguments


def _finalize_tool_calls(tool_calls: list[dict[str, Any]]) -> list[LLMToolCall]:
    finalized: list[LLMToolCall] = []
    for index, tool_call in enumerate(tool_calls):
        function = tool_call.get("function")
        if not isinstance(function, dict):
            continue
        name = function.get("name")
        if not name:
            continue
        arguments_raw = str(function.get("arguments") or "{}")
        tool_call_id = str(tool_call.get("id") or f"call_{index + 1}")
        finalized.append(
            LLMToolCall(
                id=tool_call_id,
                name=str(name),
                arguments=load_tool_arguments(arguments_raw),
                raw={"arguments": arguments_raw},
            )
        )
    return finalized
