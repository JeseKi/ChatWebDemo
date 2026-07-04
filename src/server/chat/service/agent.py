# -*- coding: utf-8 -*-
"""Compatibility facade for ChatWeb Agent streaming."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextvars import ContextVar
from typing import Any

from openai import AsyncOpenAI

from src.server.chat.agent.base import BaseAgent, ChatRunEvent
from src.server.chat.agent.contracts import LLMImage, LLMMessage
from src.server.chat.agent.example import build_chat_agent
from src.server.chat.agent.providers.openai_chat import OpenAIChatCompletionsProvider
from src.server.chat.service.images import (
    content_without_image_markers,
    extract_image_urls,
    get_user_image,
    image_id_from_url,
)
from src.server.chat.service.model_catalog import ModelConfig

from ..models import ChatMessage
from ..tools import ChatTool
from .constants import (
    CHAT_AGENT_HISTORY_PROMPT,
    CHAT_AGENT_INSTRUCTIONS,
    MAX_HISTORY_MESSAGES,
)

CHAT_TOOL_CALL_LIMIT = 4
_current_model_config: ContextVar[ModelConfig | None] = ContextVar(
    "current_model_config",
    default=None,
)
_current_thinking_effort: ContextVar[str | None] = ContextVar(
    "current_thinking_effort",
    default=None,
)


async def stream_agent_events(
    prompt: str | list[LLMMessage],
    *,
    user_id: str,
) -> AsyncIterator[ChatRunEvent]:
    agent = build_chat_agent(
        model_config=_current_model_config.get(),
        thinking_effort=_current_thinking_effort.get(),
    )
    if isinstance(prompt, list):
        async for event in agent.arun_messages(prompt, user_id=user_id):
            yield event
        return
    async for event in agent.arun(prompt, user_id=user_id):
        yield event


def set_agent_model_context(
    model_config: ModelConfig | None,
    thinking_effort: str | None,
) -> tuple[object, object]:
    return (
        _current_model_config.set(model_config),
        _current_thinking_effort.set(thinking_effort),
    )


def reset_agent_model_context(tokens: tuple[object, object]) -> None:
    model_token, effort_token = tokens
    _current_model_config.reset(model_token)  # type: ignore[arg-type]
    _current_thinking_effort.reset(effort_token)  # type: ignore[arg-type]


class OpenAICompatibleChatAgent(BaseAgent):
    """Backward-compatible wrapper for existing tests and imports."""

    def __init__(
        self,
        *,
        client: AsyncOpenAI,
        model_id: str,
        tools: list[ChatTool] | None = None,
    ):
        provider = OpenAIChatCompletionsProvider(client=client, model_id=model_id)
        super().__init__(
            provider=provider,
            instructions=CHAT_AGENT_INSTRUCTIONS,
            tools=tools,
            max_tool_calls=CHAT_TOOL_CALL_LIMIT,
        )
        self.client = client
        self.model_id = model_id
        self.tool_registry = {
            tool.name: tool.handler for tool in self.tools if tool.name
        }


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


class AgentMessageHistory(list[LLMMessage]):
    def __init__(self, messages: list[LLMMessage], text_view: str):
        super().__init__(messages)
        self.text_view = text_view

    def __contains__(self, value: object) -> bool:
        if isinstance(value, str):
            return value in self.text_view
        return super().__contains__(value)

    def __str__(self) -> str:
        return self.text_view


def build_agent_messages(messages: list[ChatMessage]) -> list[LLMMessage]:
    output: list[LLMMessage] = [LLMMessage(role="system", content=CHAT_AGENT_INSTRUCTIONS)]
    for item in messages[-MAX_HISTORY_MESSAGES:]:
        content = content_without_image_markers(item.content)
        output.append(
            LLMMessage(
                role="user" if item.role == "user" else "assistant",
                content=content,
                images=_images_for_message(item) if item.role == "user" else [],
            )
        )
    return AgentMessageHistory(output, build_agent_input(messages))


def _images_for_message(message: ChatMessage) -> list[LLMImage]:
    images: list[LLMImage] = []
    for url in extract_image_urls(message.content):
        image_id = image_id_from_url(url)
        if not image_id:
            continue
        stored = get_user_image(message.user_id, image_id)
        if stored is None:
            continue
        images.append(
            LLMImage(
                mime_type=stored.mime_type,
                base64_data=stored.base64_data,
                data_bytes=stored.data_bytes,
                width=stored.width,
                height=stored.height,
            )
        )
    return images


def _load_tool_arguments(value: Any) -> dict[str, Any]:
    from src.server.chat.agent.contracts import load_tool_arguments

    return load_tool_arguments(value)
