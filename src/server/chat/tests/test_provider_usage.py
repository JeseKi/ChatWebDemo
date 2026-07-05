# -*- coding: utf-8 -*-

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from src.server.chat.agent.contracts import LLMMessage
from src.server.chat.agent.providers.anthropic import AnthropicProvider
from src.server.chat.agent.providers.deepseek import DeepSeekProvider
from src.server.chat.agent.providers.usage import (
    anthropic_usage,
    google_usage,
    openai_chat_usage,
    openai_responses_usage,
)


def test_openai_chat_usage_extracts_completion_fields():
    usage = openai_chat_usage(
        "openai_chat",
        "gpt-test",
        {
            "prompt_tokens": 10,
            "completion_tokens": 7,
            "total_tokens": 17,
            "prompt_tokens_details": {"cached_tokens": 3},
            "completion_tokens_details": {"reasoning_tokens": 2},
        },
    )

    assert usage is not None
    assert usage.input_tokens == 10
    assert usage.output_tokens == 7
    assert usage.total_tokens == 17
    assert usage.cached_input_tokens == 3
    assert usage.reasoning_tokens == 2


def test_openai_chat_usage_extracts_deepseek_cache_hit_tokens():
    usage = openai_chat_usage(
        "deepseek",
        "deepseek-test",
        {
            "prompt_tokens": 10,
            "prompt_cache_hit_tokens": 6,
            "prompt_cache_miss_tokens": 4,
            "completion_tokens": 7,
            "completion_tokens_details": {"reasoning_tokens": 3},
            "total_tokens": 17,
        },
    )

    assert usage is not None
    assert usage.cached_input_tokens == 6
    assert usage.reasoning_tokens == 3


def test_openai_responses_usage_extracts_response_fields():
    usage = openai_responses_usage(
        "openai_responses",
        "gpt-test",
        {
            "input_tokens": 11,
            "output_tokens": 9,
            "total_tokens": 20,
            "input_tokens_details": {"cached_tokens": 4},
            "output_tokens_details": {"reasoning_tokens": 5},
        },
    )

    assert usage is not None
    assert usage.input_tokens == 11
    assert usage.output_tokens == 9
    assert usage.total_tokens == 20
    assert usage.cached_input_tokens == 4
    assert usage.reasoning_tokens == 5


def test_anthropic_usage_extracts_message_usage_objects():
    usage = anthropic_usage(
        "anthropic",
        "claude-test",
        {
            "input_tokens": 13,
            "output_tokens": 8,
            "cache_creation_input_tokens": 2,
            "cache_read_input_tokens": 3,
            "output_tokens_details": {"thinking_tokens": 5},
        },
    )

    assert usage is not None
    assert usage.input_tokens == 13
    assert usage.output_tokens == 8
    assert usage.total_tokens is None
    assert usage.cached_input_tokens == 5
    assert usage.reasoning_tokens == 5


def test_google_usage_extracts_usage_metadata():
    usage = google_usage(
        "google",
        "gemini-test",
        {
            "promptTokenCount": 21,
            "candidatesTokenCount": 12,
            "totalTokenCount": 40,
            "thoughtsTokenCount": 6,
            "toolUsePromptTokenCount": 1,
            "cachedContentTokenCount": 2,
        },
    )

    assert usage is not None
    assert usage.input_tokens == 21
    assert usage.output_tokens == 12
    assert usage.total_tokens == 40
    assert usage.reasoning_tokens == 6
    assert usage.tool_tokens == 1
    assert usage.cached_input_tokens == 2


@pytest.mark.asyncio
async def test_anthropic_provider_awaits_stream_create_coroutine():
    class FakeMessages:
        def __init__(self):
            self.request_params: dict[str, Any] | None = None

        async def create(self, **kwargs):
            self.request_params = kwargs

            async def stream():
                yield SimpleNamespace(
                    type="message_start",
                    message=SimpleNamespace(
                        usage=SimpleNamespace(input_tokens=3),
                    ),
                )
                yield SimpleNamespace(
                    type="content_block_delta",
                    delta=SimpleNamespace(type="text_delta", text="hello"),
                )
                yield SimpleNamespace(
                    type="message_delta",
                    usage=SimpleNamespace(output_tokens=4),
                )

            return stream()

    messages = FakeMessages()
    provider = AnthropicProvider(api_key="test", model_id="claude-test")
    provider._client = SimpleNamespace(messages=messages)

    events = [
        event
        async for event in provider.stream_turn(
            [LLMMessage(role="user", content="hi")],
            tools=[],
            user_id="1",
            allow_tools=False,
        )
    ]

    assert messages.request_params is not None
    assert messages.request_params["stream"] is True
    assert [event.type for event in events] == ["content_delta", "usage"]
    assert events[0].content == "hello"
    assert events[1].usage is not None
    assert events[1].usage.input_tokens == 3
    assert events[1].usage.output_tokens == 4


@pytest.mark.asyncio
async def test_deepseek_provider_requests_and_emits_streaming_usage():
    class FakeCompletions:
        def __init__(self):
            self.request_params: dict[str, Any] | None = None

        async def create(self, **kwargs):
            self.request_params = kwargs

            async def stream():
                yield SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(content="hello", tool_calls=None),
                        )
                    ],
                    usage=None,
                )
                yield SimpleNamespace(
                    choices=[],
                    usage={
                        "prompt_tokens": 4,
                        "completion_tokens": 5,
                        "total_tokens": 9,
                    },
                )

            return stream()

    completions = FakeCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    provider = DeepSeekProvider(client=cast(Any, client), model_id="deepseek-test")

    events = [
        event
        async for event in provider.stream_turn(
            [LLMMessage(role="user", content="hi")],
            tools=[],
            user_id="1",
            allow_tools=False,
        )
    ]

    assert completions.request_params is not None
    assert completions.request_params["stream_options"] == {"include_usage": True}
    assert [event.type for event in events] == ["content_delta", "usage"]
    assert events[-1].usage is not None
    assert events[-1].usage.provider == "deepseek"
    assert events[-1].usage.total_tokens == 9
