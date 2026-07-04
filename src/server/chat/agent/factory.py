# -*- coding: utf-8 -*-
"""Agent provider factory driven by LLM_* environment settings."""

from __future__ import annotations

import os
from typing import Literal

from openai import AsyncOpenAI

from .contracts import LLMProvider
from .providers.anthropic import AnthropicProvider
from .providers.deepseek import DeepSeekProvider
from .providers.google import GoogleGeminiProvider
from .providers.openai_chat import OpenAIChatCompletionsProvider
from .providers.openai_responses import OpenAIResponsesProvider

LLMProviderName = Literal[
    "openai_chat",
    "openai_responses",
    "deepseek",
    "anthropic",
    "google",
]

DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-pro"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-6"
DEFAULT_GOOGLE_MODEL = "gemini-3.5-flash"


def build_llm_provider() -> LLMProvider:
    provider = _provider_name()
    model_override = _env("LLM_MODEL")

    if provider == "openai_chat":
        api_key = _required_env("LLM_OPENAI_API_KEY")
        base_url = _env("LLM_OPENAI_BASE_URL")
        return OpenAIChatCompletionsProvider(
            client=AsyncOpenAI(api_key=api_key, base_url=base_url or None),
            model_id=model_override or _env("LLM_OPENAI_MODEL") or DEFAULT_OPENAI_MODEL,
        )

    if provider == "openai_responses":
        api_key = _required_env("LLM_OPENAI_API_KEY")
        base_url = _env("LLM_OPENAI_BASE_URL")
        return OpenAIResponsesProvider(
            client=AsyncOpenAI(api_key=api_key, base_url=base_url or None),
            model_id=model_override or _env("LLM_OPENAI_MODEL") or DEFAULT_OPENAI_MODEL,
        )

    if provider == "deepseek":
        api_key = _required_env("LLM_DEEPSEEK_API_KEY")
        return DeepSeekProvider(
            client=AsyncOpenAI(
                api_key=api_key,
                base_url=_env("LLM_DEEPSEEK_BASE_URL") or DEFAULT_DEEPSEEK_BASE_URL,
            ),
            model_id=model_override
            or _env("LLM_DEEPSEEK_MODEL")
            or DEFAULT_DEEPSEEK_MODEL,
            reasoning_effort=_env("LLM_DEEPSEEK_REASONING_EFFORT"),
            thinking_enabled=_optional_bool("LLM_DEEPSEEK_THINKING_ENABLED"),
        )

    if provider == "anthropic":
        return AnthropicProvider(
            api_key=_required_env("LLM_ANTHROPIC_API_KEY"),
            model_id=model_override
            or _env("LLM_ANTHROPIC_MODEL")
            or DEFAULT_ANTHROPIC_MODEL,
        )

    if provider == "google":
        return GoogleGeminiProvider(
            api_key=_required_env("LLM_GOOGLE_API_KEY"),
            model_id=model_override or _env("LLM_GOOGLE_MODEL") or DEFAULT_GOOGLE_MODEL,
        )

    raise RuntimeError(f"Unsupported LLM_PROVIDER: {provider}")


def _provider_name() -> LLMProviderName:
    raw = (_env("LLM_PROVIDER") or "openai_chat").lower()
    if raw in {"openai_chat", "openai_responses", "deepseek", "anthropic", "google"}:
        return raw  # type: ignore[return-value]
    raise RuntimeError(f"Unsupported LLM_PROVIDER: {raw}")


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _required_env(name: str) -> str:
    value = _env(name)
    if not value:
        raise RuntimeError(f"Missing {name}")
    return value


def _optional_bool(name: str) -> bool | None:
    value = _env(name).lower()
    if not value:
        return None
    if value in {"1", "true", "yes", "on", "enabled"}:
        return True
    if value in {"0", "false", "no", "off", "disabled"}:
        return False
    raise RuntimeError(f"{name} must be a boolean value")
