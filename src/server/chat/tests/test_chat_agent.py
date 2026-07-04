# -*- coding: utf-8 -*-

from src.server.chat.service.agent import OpenAICompatibleChatAgent
from src.server.chat.tools import get_chat_tools


def test_openai_compatible_agent_has_no_default_tools():
    agent = OpenAICompatibleChatAgent(client=object(), model_id="test-model")  # type: ignore[arg-type]

    assert agent.tool_specs == []
    assert agent.tool_registry == {}


def test_openai_compatible_agent_uses_injected_tools():
    tools = get_chat_tools()
    agent = OpenAICompatibleChatAgent(
        client=object(),  # type: ignore[arg-type]
        model_id="test-model",
        tools=tools,
    )

    assert agent.tool_specs == [tools[0].spec]
    assert agent.tool_registry["get_order_status"] is tools[0].handler
