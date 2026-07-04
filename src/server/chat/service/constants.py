# -*- coding: utf-8 -*-
"""ChatWeb service constants."""

DEFAULT_MODEL_ID = "gpt-5.4-mini"
MAX_HISTORY_MESSAGES = 20
CHAT_AGENT_INSTRUCTIONS = (
    "You are a concise support assistant. Use available tools when they are "
    "needed to answer factual order questions. Answer in the user's language."
)
CHAT_AGENT_HISTORY_PROMPT = "Conversation history follows. Answer the latest user message."
