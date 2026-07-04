# -*- coding: utf-8 -*-

from src.server.chat.agent.contracts import LLMToolCall
from src.server.chat.agent.providers.deepseek import DeepSeekProvider
from src.server.chat.agent.providers.openai_chat import _to_chat_message


def test_deepseek_assistant_tool_message_preserves_reasoning_content():
    provider = DeepSeekProvider(
        client=object(),  # type: ignore[arg-type]
        model_id="deepseek-v4-pro",
        thinking_enabled=True,
    )

    message = provider.build_assistant_message(
        content=None,
        reasoning_content="need to call a tool",
        tool_calls=[
            LLMToolCall(
                id="call-1",
                name="lookup",
                arguments={"value": "abc"},
                raw={"arguments": '{"value":"abc"}'},
            )
        ],
        provider_metadata={},
    )

    payload = _to_chat_message(message)

    assert payload["content"] == ""
    assert payload["reasoning_content"] == "need to call a tool"
    assert payload["tool_calls"][0]["id"] == "call-1"
    assert payload["tool_calls"][0]["function"]["arguments"] == '{"value":"abc"}'


def test_deepseek_provider_stores_thinking_flag():
    provider = DeepSeekProvider(
        client=object(),  # type: ignore[arg-type]
        model_id="deepseek-v4-pro",
        thinking_enabled=False,
    )

    assert provider.thinking_enabled is False

