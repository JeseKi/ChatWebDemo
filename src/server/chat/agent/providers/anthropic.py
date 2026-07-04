# -*- coding: utf-8 -*-
"""Anthropic Messages provider adapter."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from ..contracts import (
    LLMMessage,
    LLMProvider,
    LLMProviderEvent,
    LLMToolCall,
)
from ..tools import AgentTool


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        model_id: str,
        max_output: int | None = None,
        base_url: str | None = None,
    ):
        self.api_key = api_key
        self.model_id = model_id
        self.max_output = max_output
        self.base_url = base_url
        self._client: Any | None = None

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic
            except ModuleNotFoundError as exc:  # pragma: no cover - environment setup
                raise RuntimeError(
                    "anthropic package is required for Anthropic chat models"
                ) from exc
            self._client = AsyncAnthropic(api_key=self.api_key, base_url=self.base_url)
        return self._client

    async def stream_turn(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[AgentTool],
        user_id: str,
        allow_tools: bool,
    ) -> AsyncIterator[LLMProviderEvent]:
        system, anthropic_messages = _to_anthropic_messages(messages)
        request_params: dict[str, Any] = {
            "model": self.model_id,
            "max_tokens": self.max_output or 4096,
            "messages": anthropic_messages,
            "metadata": {"user_id": user_id},
            "stream": True,
        }
        if system:
            request_params["system"] = system
        if allow_tools:
            request_params["tools"] = [_anthropic_tool(tool) for tool in tools]

        stream = self.client.messages.create(**request_params)
        active_tool: dict[str, Any] | None = None
        tool_calls: list[LLMToolCall] = []
        thinking_blocks: list[dict[str, Any]] = []

        async for event in stream:
            event_type = str(getattr(event, "type", ""))
            if event_type == "content_block_start":
                block = getattr(event, "content_block", None)
                block_type = str(getattr(block, "type", ""))
                if block_type == "tool_use":
                    active_tool = {
                        "id": str(getattr(block, "id", "")),
                        "name": str(getattr(block, "name", "")),
                        "arguments": "",
                    }
                elif block_type == "thinking":
                    thinking_blocks.append(_to_plain_dict(block))
                continue

            if event_type == "content_block_delta":
                delta = getattr(event, "delta", None)
                delta_type = str(getattr(delta, "type", ""))
                if delta_type == "text_delta":
                    text = getattr(delta, "text", None)
                    if text:
                        yield LLMProviderEvent(type="content_delta", content=str(text))
                elif delta_type == "thinking_delta":
                    thinking = getattr(delta, "thinking", None)
                    if thinking:
                        yield LLMProviderEvent(
                            type="reasoning_delta",
                            reasoning_content=str(thinking),
                        )
                elif delta_type == "input_json_delta" and active_tool is not None:
                    active_tool["arguments"] += str(
                        getattr(delta, "partial_json", "") or ""
                    )
                elif delta_type == "signature_delta" and thinking_blocks:
                    thinking_blocks[-1]["signature"] = str(
                        getattr(delta, "signature", "") or ""
                    )
                continue

            if event_type == "content_block_stop" and active_tool is not None:
                tool_calls.append(
                    LLMToolCall(
                        id=active_tool["id"],
                        name=active_tool["name"],
                        arguments=_load_json_object(active_tool["arguments"]),
                        raw={"arguments": active_tool["arguments"]},
                    )
                )
                active_tool = None

        for tool_call in tool_calls:
            yield LLMProviderEvent(type="tool_call", tool_call=tool_call)
        if thinking_blocks:
            yield LLMProviderEvent(
                type="metadata",
                provider_metadata={"anthropic_thinking_blocks": thinking_blocks},
            )

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
        )


def _to_anthropic_messages(messages: list[LLMMessage]) -> tuple[str | None, list[dict[str, Any]]]:
    system = None
    output: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "system":
            system = message.content or ""
            continue
        if message.role == "assistant":
            content: list[dict[str, Any]] = []
            thinking_blocks = message.provider_metadata.get("anthropic_thinking_blocks")
            if isinstance(thinking_blocks, list):
                content.extend(item for item in thinking_blocks if isinstance(item, dict))
            if message.content:
                content.append({"type": "text", "text": message.content})
            for tool_call in message.tool_calls:
                content.append(
                    {
                        "type": "tool_use",
                        "id": tool_call.id,
                        "name": tool_call.name,
                        "input": tool_call.arguments,
                    }
                )
            if content:
                output.append({"role": "assistant", "content": content})
            continue
        if message.role == "tool":
            output.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": message.tool_call_id or "",
                            "content": message.content or "",
                        }
                    ],
                }
            )
            continue
        if message.images:
            user_content: list[dict[str, Any]] = []
            if message.content:
                user_content.append({"type": "text", "text": message.content})
            for image in message.images:
                user_content.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": image.mime_type,
                            "data": image.base64_data,
                        },
                    }
                )
            output.append({"role": "user", "content": user_content})
        else:
            output.append({"role": "user", "content": message.content or ""})
    return system, output


def _anthropic_tool(tool: AgentTool) -> dict[str, Any]:
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.parameters,
    }


def _load_json_object(value: str) -> dict[str, Any]:
    if not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {"value": value}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def _to_plain_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        return dumped if isinstance(dumped, dict) else {}
    return {}
