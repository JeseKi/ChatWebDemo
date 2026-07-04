# -*- coding: utf-8 -*-
"""DeepSeek Chat Completions provider adapter."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

from ..contracts import LLMMessage, LLMProviderEvent, LLMToolCall
from ..tools import AgentTool
from .openai_chat import (
    OpenAIChatCompletionsProvider,
    _extract_reasoning_delta,
    _finalize_tool_calls,
    _merge_tool_call_deltas,
    _openai_chat_tool,
    _to_chat_message,
)


class DeepSeekProvider(OpenAIChatCompletionsProvider):
    """OpenAI-compatible adapter with DeepSeek thinking-mode rules."""

    name = "deepseek"

    def __init__(
        self,
        *,
        client: AsyncOpenAI,
        model_id: str,
        max_output: int | None = None,
        reasoning_effort: str | None = None,
        thinking_enabled: bool | None = None,
    ):
        super().__init__(client=client, model_id=model_id, stream_options={})
        self.max_output = max_output
        self.reasoning_effort = reasoning_effort
        self.thinking_enabled = thinking_enabled

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
            "user": user_id,
        }
        if self.reasoning_effort:
            request_params["reasoning_effort"] = self.reasoning_effort
        if self.max_output is not None:
            request_params["max_tokens"] = self.max_output
        if self.thinking_enabled is not None:
            request_params["extra_body"] = {
                "thinking": {
                    "type": "enabled" if self.thinking_enabled else "disabled",
                }
            }
        if allow_tools:
            request_params["tools"] = [_openai_chat_tool(tool) for tool in tools]
            # DeepSeek thinking-mode tool calls rely on the API default behavior.
            # Some DeepSeek-compatible agent routes reject explicit tool_choice.

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

    def build_assistant_message(
        self,
        *,
        content: str | None,
        reasoning_content: str | None,
        tool_calls: list[LLMToolCall],
        provider_metadata: dict[str, Any],
    ) -> LLMMessage:
        message = super().build_assistant_message(
            content=content,
            reasoning_content=reasoning_content,
            tool_calls=tool_calls,
            provider_metadata=provider_metadata,
        )
        if message.tool_calls and message.content is None:
            message.content = ""
        return message
