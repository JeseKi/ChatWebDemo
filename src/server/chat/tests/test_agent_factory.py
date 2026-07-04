# -*- coding: utf-8 -*-

from types import SimpleNamespace

from src.server.chat.agent.factory import build_llm_provider
from src.server.chat.agent.providers.deepseek import DeepSeekProvider
from src.server.chat.agent.providers.openai_chat import (
    OpenAIChatCompletionsProvider,
)
from src.server.chat.agent.providers.openai_responses import OpenAIResponsesProvider


def _model_config(provider: str, model_id: str = "catalog-model"):
    return SimpleNamespace(
        provider=provider,
        id=model_id,
        max_output=1024,
        keep_thinking_content=False,
    )


def test_build_llm_provider_selects_openai_chat(monkeypatch):
    monkeypatch.setenv("LLM_OPENAI_API_KEY", "test-key")

    provider = build_llm_provider(_model_config("openai_chat", "openai-model"))

    assert isinstance(provider, OpenAIChatCompletionsProvider)
    assert provider.model_id == "openai-model"
    assert provider.max_output == 1024


def test_build_llm_provider_selects_openai_responses(monkeypatch):
    monkeypatch.setenv("LLM_OPENAI_API_KEY", "test-key")

    provider = build_llm_provider(_model_config("openai_responses", "openai-model"))

    assert isinstance(provider, OpenAIResponsesProvider)
    assert provider.model_id == "openai-model"
    assert provider.max_output == 1024


def test_build_llm_provider_selects_deepseek(monkeypatch):
    monkeypatch.setenv("LLM_DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("LLM_DEEPSEEK_BASE_URL", "https://api.deepseek.example")

    provider = build_llm_provider(
        _model_config("deepseek", "deepseek-model"),
        thinking_effort="low",
    )

    assert isinstance(provider, DeepSeekProvider)
    assert provider.model_id == "deepseek-model"
    assert provider.thinking_enabled is True
    assert provider.max_output == 1024
    assert provider.reasoning_effort == "low"


def test_env_model_names_do_not_override_catalog_model(monkeypatch):
    monkeypatch.setenv("LLM_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_" + "MODEL", "override-model")
    monkeypatch.setenv("LLM_OPENAI_" + "MODEL", "env-model")

    provider = build_llm_provider(_model_config("openai_chat", "catalog-model"))

    assert provider.model_id == "catalog-model"
