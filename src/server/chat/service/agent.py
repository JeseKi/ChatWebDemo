# -*- coding: utf-8 -*-
"""Agent construction and prompt formatting for ChatWeb."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

from ..models import ChatMessage
from ..tools import get_chat_tools
from .constants import DEFAULT_MODEL_ID, MAX_HISTORY_MESSAGES


async def stream_agent_events(
    prompt: str,
    *,
    user_id: str,
    session_id: str,
) -> AsyncIterator[Any]:
    agent = build_chat_agent()
    async for event in agent.arun(
        prompt,
        stream=True,
        stream_events=True,
        user_id=user_id,
        session_id=session_id,
    ):
        yield event


def build_chat_agent() -> Any:
    from agno.agent import Agent
    from agno.models.openai.like import OpenAILike

    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    model_id = os.getenv("OPENAI_MODEL", DEFAULT_MODEL_ID)
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY")
    if not base_url:
        raise RuntimeError("Missing OPENAI_BASE_URL")

    return Agent(
        model=OpenAILike(id=model_id, api_key=api_key, base_url=base_url),
        tools=get_chat_tools(),
        instructions=(
            "You are a concise support assistant. Use available tools when they are "
            "needed to answer factual order questions. Answer in the user's language."
        ),
        markdown=True,
        tool_call_limit=4,
    )


def build_agent_input(messages: list[ChatMessage]) -> str:
    recent_messages = messages[-MAX_HISTORY_MESSAGES:]
    lines = [
        "Conversation history follows. Answer the latest user message.",
        "",
    ]
    for item in recent_messages:
        role = "User" if item.role == "user" else "Assistant"
        lines.append(f"{role}: {item.content}")
    return "\n".join(lines)
