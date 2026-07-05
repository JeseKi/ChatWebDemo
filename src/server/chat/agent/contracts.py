# -*- coding: utf-8 -*-
"""Provider-neutral contracts for ChatWeb agents."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal

AgentRole = Literal["system", "user", "assistant", "tool"]
LLMProviderEventType = Literal[
    "content_delta",
    "reasoning_delta",
    "tool_call",
    "metadata",
    "usage",
]


@dataclass(frozen=True)
class LLMToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMImage:
    mime_type: str
    base64_data: str
    data_bytes: bytes
    width: int
    height: int

    @property
    def data_url(self) -> str:
        return f"data:{self.mime_type};base64,{self.base64_data}"


@dataclass(frozen=True)
class LLMTokenUsage:
    provider: str
    model_id: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    reasoning_tokens: int | None = None
    cached_input_tokens: int | None = None
    tool_tokens: int | None = None
    raw_usage: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMMessage:
    role: AgentRole
    content: str | None = None
    images: list[LLMImage] = field(default_factory=list)
    tool_calls: list[LLMToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None
    provider_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMProviderEvent:
    type: LLMProviderEventType
    content: str | None = None
    reasoning_content: str | None = None
    tool_call: LLMToolCall | None = None
    provider_metadata: dict[str, Any] = field(default_factory=dict)
    usage: LLMTokenUsage | None = None


class LLMProvider(ABC):
    """Async streaming interface implemented by every model provider adapter."""

    name: str
    model_id: str

    @abstractmethod
    def stream_turn(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[Any],
        user_id: str,
        allow_tools: bool,
    ) -> AsyncIterator[LLMProviderEvent]:
        """Stream one provider turn and emit normalized deltas/tool calls."""

    def build_initial_messages(
        self,
        *,
        instructions: str,
        prompt: str,
        images: list[LLMImage] | None = None,
    ) -> list[LLMMessage]:
        return [
            LLMMessage(role="system", content=instructions),
            LLMMessage(role="user", content=prompt, images=images or []),
        ]

    def build_assistant_message(
        self,
        *,
        content: str | None,
        reasoning_content: str | None,
        tool_calls: list[LLMToolCall],
        provider_metadata: dict[str, Any],
    ) -> LLMMessage:
        metadata = dict(provider_metadata)
        if reasoning_content and "reasoning_content" not in metadata:
            metadata["reasoning_content"] = reasoning_content
        return LLMMessage(
            role="assistant",
            content=content,
            tool_calls=tool_calls,
            provider_metadata=metadata,
        )

    def build_tool_message(self, tool_call: LLMToolCall, output: Any) -> LLMMessage:
        return LLMMessage(
            role="tool",
            name=tool_call.name,
            tool_call_id=tool_call.id,
            content=json.dumps(output, ensure_ascii=False, default=str),
        )


def load_tool_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {"value": value}
    return parsed if isinstance(parsed, dict) else {"value": parsed}
