# -*- coding: utf-8 -*-
"""OpenAI Responses API provider adapter."""

from __future__ import annotations

import json
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
from .usage import openai_responses_usage


class OpenAIResponsesProvider(LLMProvider):
    name = "openai_responses"

    def __init__(
        self,
        *,
        client: AsyncOpenAI,
        model_id: str,
        max_output: int | None = None,
        reasoning_effort: str | None = None,
    ):
        self.client = client
        self.model_id = model_id
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
        instructions, input_items = _to_response_input(messages)
        request_params: dict[str, Any] = {
            "model": self.model_id,
            "input": input_items,
            "instructions": instructions,
            "stream": True,
            "user": user_id,
        }
        if allow_tools:
            request_params["tools"] = [_responses_tool(tool) for tool in tools]
            request_params["tool_choice"] = "auto"
        if self.max_output is not None:
            request_params["max_output_tokens"] = self.max_output
        if self.reasoning_effort:
            request_params["reasoning"] = {"effort": self.reasoning_effort}

        stream = await self.client.responses.create(**request_params)
        calls: dict[int, dict[str, Any]] = {}
        response_items: list[dict[str, Any]] = []
        token_usage = None

        async for event in stream:
            event_type = str(getattr(event, "type", ""))
            if event_type == "response.output_text.delta":
                delta = getattr(event, "delta", None)
                if delta:
                    yield LLMProviderEvent(type="content_delta", content=str(delta))
                continue

            if "reasoning" in event_type and "delta" in event_type:
                delta = getattr(event, "delta", None)
                if delta:
                    yield LLMProviderEvent(
                        type="reasoning_delta",
                        reasoning_content=str(delta),
                    )
                continue

            if event_type == "response.output_item.added":
                output_index = int(getattr(event, "output_index", 0) or 0)
                item = _to_plain_dict(getattr(event, "item", None))
                if item.get("type") == "function_call":
                    calls[output_index] = {
                        "id": str(item.get("call_id") or item.get("id") or ""),
                        "name": str(item.get("name") or ""),
                        "arguments": str(item.get("arguments") or ""),
                    }
                response_items.append(item)
                continue

            if event_type == "response.function_call_arguments.delta":
                output_index = int(getattr(event, "output_index", 0) or 0)
                calls.setdefault(output_index, {"id": "", "name": "", "arguments": ""})
                calls[output_index]["arguments"] += str(getattr(event, "delta", "") or "")
                continue

            if event_type == "response.function_call_arguments.done":
                output_index = int(getattr(event, "output_index", 0) or 0)
                item = _to_plain_dict(getattr(event, "item", None))
                if item:
                    calls[output_index] = {
                        "id": str(item.get("call_id") or item.get("id") or ""),
                        "name": str(item.get("name") or ""),
                        "arguments": str(item.get("arguments") or "{}"),
                    }
                continue

            if event_type == "response.completed":
                response = getattr(event, "response", None)
                output = getattr(response, "output", None)
                if output is not None:
                    response_items = [_to_plain_dict(item) for item in output]
                token_usage = openai_responses_usage(
                    self.name,
                    self.model_id,
                    getattr(response, "usage", None),
                )

        for index, call in sorted(calls.items()):
            name = call.get("name")
            if not name:
                continue
            call_id = call.get("id") or f"call_{index + 1}"
            arguments = call.get("arguments") or "{}"
            yield LLMProviderEvent(
                type="tool_call",
                tool_call=LLMToolCall(
                    id=str(call_id),
                    name=str(name),
                    arguments=load_tool_arguments(arguments),
                    raw={"arguments": arguments},
                ),
            )
        if response_items:
            yield LLMProviderEvent(
                type="metadata",
                provider_metadata={"response_items": response_items},
            )
        if token_usage is not None:
            yield LLMProviderEvent(type="usage", usage=token_usage)

    def build_assistant_message(
        self,
        *,
        content: str | None,
        reasoning_content: str | None,
        tool_calls: list[LLMToolCall],
        provider_metadata: dict[str, Any],
    ) -> LLMMessage:
        return LLMMessage(
            role="assistant",
            content=content,
            tool_calls=tool_calls,
            provider_metadata=provider_metadata,
        )

    def build_tool_message(self, tool_call: LLMToolCall, output: Any) -> LLMMessage:
        return LLMMessage(
            role="tool",
            tool_call_id=tool_call.id,
            name=tool_call.name,
            content=json.dumps(output, ensure_ascii=False, default=str),
            provider_metadata={
                "response_item": {
                    "type": "function_call_output",
                    "call_id": tool_call.id,
                    "output": json.dumps(output, ensure_ascii=False, default=str),
                }
            },
        )


def _to_response_input(messages: list[LLMMessage]) -> tuple[str | None, list[dict[str, Any]]]:
    instructions = None
    input_items: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "system":
            instructions = message.content or ""
            continue
        if message.role == "tool":
            raw_item = message.provider_metadata.get("response_item")
            if isinstance(raw_item, dict):
                input_items.append(raw_item)
            else:
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": message.tool_call_id or "",
                        "output": message.content or "",
                    }
                )
            continue
        if message.role == "assistant":
            raw_items = message.provider_metadata.get("response_items")
            if isinstance(raw_items, list):
                input_items.extend(item for item in raw_items if isinstance(item, dict))
            elif message.content:
                input_items.append({"role": "assistant", "content": message.content})
            continue
        if message.images:
            content: list[dict[str, Any]] = []
            if message.content:
                content.append({"type": "input_text", "text": message.content})
            for image in message.images:
                content.append({"type": "input_image", "image_url": image.data_url})
            input_items.append({"role": "user", "content": content})
        else:
            input_items.append({"role": "user", "content": message.content or ""})
    return instructions, input_items


def _responses_tool(tool: AgentTool) -> dict[str, Any]:
    return {
        "type": "function",
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.parameters,
        "strict": tool.strict,
    }


def _to_plain_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        return dumped if isinstance(dumped, dict) else {}
    if hasattr(value, "to_dict"):
        dumped = value.to_dict()
        return dumped if isinstance(dumped, dict) else {}
    return {}
