# -*- coding: utf-8 -*-

from src.server.chat.agent.factory import build_llm_provider
from src.server.chat.agent.providers.deepseek import DeepSeekProvider
from src.server.chat.agent.providers.openai_chat import (
    OpenAIChatCompletionsProvider,
)
from src.server.chat.agent.providers.openai_responses import OpenAIResponsesProvider


def test_build_llm_provider_selects_openai_chat(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai_chat")
    monkeypatch.setenv("LLM_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_OPENAI_MODEL", "openai-model")
    monkeypatch.delenv("LLM_MODEL", raising=False)

    provider = build_llm_provider()

    assert isinstance(provider, OpenAIChatCompletionsProvider)
    assert provider.model_id == "openai-model"


def test_build_llm_provider_selects_openai_responses(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai_responses")
    monkeypatch.setenv("LLM_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_OPENAI_MODEL", "openai-model")
    monkeypatch.delenv("LLM_MODEL", raising=False)

    provider = build_llm_provider()

    assert isinstance(provider, OpenAIResponsesProvider)
    assert provider.model_id == "openai-model"


def test_build_llm_provider_selects_deepseek(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("LLM_DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("LLM_DEEPSEEK_MODEL", "deepseek-model")
    monkeypatch.setenv("LLM_DEEPSEEK_THINKING_ENABLED", "true")
    monkeypatch.delenv("LLM_MODEL", raising=False)

    provider = build_llm_provider()

    assert isinstance(provider, DeepSeekProvider)
    assert provider.model_id == "deepseek-model"
    assert provider.thinking_enabled is True


def test_llm_model_overrides_provider_model(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai_chat")
    monkeypatch.setenv("LLM_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_OPENAI_MODEL", "openai-model")
    monkeypatch.setenv("LLM_MODEL", "override-model")

    provider = build_llm_provider()

    assert provider.model_id == "override-model"
