# -*- coding: utf-8 -*-
"""Example support Agent for ChatWeb."""

from __future__ import annotations

from .base import BaseAgent
from .factory import build_llm_provider
from ..service.constants import CHAT_AGENT_INSTRUCTIONS
from ..tools import get_chat_tools


def build_chat_agent() -> BaseAgent:
    return BaseAgent(
        provider=build_llm_provider(),
        instructions=CHAT_AGENT_INSTRUCTIONS,
        tools=get_chat_tools(),
    )

