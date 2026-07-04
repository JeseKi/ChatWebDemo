# -*- coding: utf-8 -*-
"""Compatibility facade for ChatWeb Agent streaming."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

from src.server.chat.agent.base import BaseAgent, ChatRunEvent
from src.server.chat.agent.example import build_chat_agent
from src.server.chat.agent.providers.openai_chat import OpenAIChatCompletionsProvider

from ..models import ChatMessage
from ..tools import ChatTool
from .constants import (
    CHAT_AGENT_HISTORY_PROMPT,
    CHAT_AGENT_INSTRUCTIONS,
    MAX_HISTORY_MESSAGES,
)

CHAT_TOOL_CALL_LIMIT = 4


async def stream_agent_events(
    prompt: str,
    *,
    user_id: str,
) -> AsyncIterator[ChatRunEvent]:
    agent = build_chat_agent()
    async for event in agent.arun(prompt, user_id=user_id):
        yield event


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


def _load_tool_arguments(value: Any) -> dict[str, Any]:
    from src.server.chat.agent.contracts import load_tool_arguments

    return load_tool_arguments(value)
