# -*- coding: utf-8 -*-
"""Agent provider factory driven by model catalog settings and provider credentials."""

from __future__ import annotations

import os
from typing import Any

from openai import AsyncOpenAI

from .contracts import LLMProvider
from .providers.anthropic import AnthropicProvider
from .providers.deepseek import DeepSeekProvider
from .providers.google import GoogleGeminiProvider
from .providers.openai_chat import OpenAIChatCompletionsProvider
from .providers.openai_responses import OpenAIResponsesProvider


def build_llm_provider(
    model_config: Any,
    thinking_effort: str | None = None,
) -> LLMProvider:
    provider = model_config.provider
    if provider == "openai_chat":
        api_key = _required_env("LLM_OPENAI_API_KEY")
        base_url = _env("LLM_OPENAI_BASE_URL")
        return OpenAIChatCompletionsProvider(
            client=AsyncOpenAI(api_key=api_key, base_url=base_url or None),
            model_id=model_config.id,
            max_output=model_config.max_output,
            reasoning_effort=thinking_effort,
        )

    if provider == "openai_responses":
        api_key = _required_env("LLM_OPENAI_API_KEY")
        base_url = _env("LLM_OPENAI_BASE_URL")
        return OpenAIResponsesProvider(
            client=AsyncOpenAI(api_key=api_key, base_url=base_url or None),
            model_id=model_config.id,
            max_output=model_config.max_output,
            reasoning_effort=thinking_effort,
        )

    if provider == "deepseek":
        api_key = _required_env("LLM_DEEPSEEK_API_KEY")
        return DeepSeekProvider(
            client=AsyncOpenAI(
                api_key=api_key,
                base_url=_required_env("LLM_DEEPSEEK_BASE_URL"),
            ),
            model_id=model_config.id,
            max_output=model_config.max_output,
            reasoning_effort=thinking_effort,
            thinking_enabled=True if thinking_effort else None,
        )

    if provider == "anthropic":
        return AnthropicProvider(
            api_key=_required_env("LLM_ANTHROPIC_API_KEY"),
            base_url=_env("LLM_ANTHROPIC_BASE_URL") or None,
            model_id=model_config.id,
            max_output=model_config.max_output,
        )

    if provider == "google":
        return GoogleGeminiProvider(
            api_key=_required_env("LLM_GOOGLE_API_KEY"),
            base_url=_env("LLM_GOOGLE_BASE_URL") or None,
            model_id=model_config.id,
            max_output=model_config.max_output,
        )

    raise RuntimeError(f"Unsupported chat model provider: {provider}")


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _required_env(name: str) -> str:
    value = _env(name)
    if not value:
        raise RuntimeError(f"Missing {name}")
    return value
