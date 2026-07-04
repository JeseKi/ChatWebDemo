# -*- coding: utf-8 -*-
"""Example support Agent for ChatWeb."""

from __future__ import annotations

from .base import BaseAgent
from .factory import build_llm_provider
from ..service.constants import CHAT_AGENT_INSTRUCTIONS
from ..tools import get_chat_tools
from typing import Any


def build_chat_agent(
    model_config: Any | None = None,
    thinking_effort: str | None = None,
) -> BaseAgent:
    if model_config is None:
        raise RuntimeError("Chat model config is required")
    provider = build_llm_provider(model_config=model_config, thinking_effort=thinking_effort)
    return BaseAgent(
        provider=provider,
        instructions=CHAT_AGENT_INSTRUCTIONS,
        tools=get_chat_tools(),
        keep_thinking_content=bool(model_config.keep_thinking_content),
    )
