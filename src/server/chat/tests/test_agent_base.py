# -*- coding: utf-8 -*-

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from src.server.chat.agent.base import BaseAgent
from src.server.chat.agent.contracts import (
    LLMMessage,
    LLMProvider,
    LLMProviderEvent,
    LLMToolCall,
)
from src.server.chat.agent.tools import AgentTool


class FakeProvider(LLMProvider):
    name = "fake"
    model_id = "fake-model"

    async def stream_turn(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[Any],
        user_id: str,
        allow_tools: bool,
    ) -> AsyncIterator[LLMProviderEvent]:
        if allow_tools and not any(message.role == "tool" for message in messages):
            yield LLMProviderEvent(
                type="reasoning_delta",
                reasoning_content="need lookup",
            )
            yield LLMProviderEvent(
                type="tool_call",
                tool_call=LLMToolCall(
                    id="call-1",
                    name="lookup",
                    arguments={"value": "abc"},
                ),
            )
            yield LLMProviderEvent(
                type="metadata",
                provider_metadata={"vendor_item": {"id": "item-1"}},
            )
            return

        tool_message = next(message for message in messages if message.role == "tool")
        yield LLMProviderEvent(
            type="content_delta",
            content=f"done: {tool_message.content}",
        )


class RepeatingToolProvider(LLMProvider):
    name = "repeating"
    model_id = "fake-model"

    async def stream_turn(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[Any],
        user_id: str,
        allow_tools: bool,
    ) -> AsyncIterator[LLMProviderEvent]:
        tool_count = sum(1 for message in messages if message.role == "tool")
        if allow_tools and tool_count < 6:
            yield LLMProviderEvent(
                type="tool_call",
                tool_call=LLMToolCall(
                    id=f"call-{tool_count + 1}",
                    name="lookup",
                    arguments={"value": str(tool_count + 1)},
                ),
            )
            return

        yield LLMProviderEvent(type="content_delta", content=f"calls: {tool_count}")


@pytest.mark.asyncio
async def test_base_agent_awaits_async_tools_and_streams_events():
    async def lookup(value: str) -> dict[str, str]:
        return {"value": value}

    agent = BaseAgent(
        provider=FakeProvider(),
        instructions="test",
        tools=[
            AgentTool(
                name="lookup",
                display_name="Lookup",
                description="Lookup a value",
                parameters={
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
                handler=lookup,
            )
        ],
    )

    events = [event async for event in agent.arun("hello", user_id="u1")]

    assert [event.event for event in events] == [
        "RunReasoningContent",
        "ToolCallStarted",
        "ToolCallCompleted",
        "RunContent",
    ]
    assert events[2].tool is not None
    assert events[2].tool.result == {"value": "abc"}
    assert events[3].content == 'done: {"value": "abc"}'


@pytest.mark.asyncio
async def test_base_agent_allows_unlimited_tool_calls_by_default():
    async def lookup(value: str) -> dict[str, str]:
        return {"value": value}

    agent = BaseAgent(
        provider=RepeatingToolProvider(),
        instructions="test",
        tools=[
            AgentTool(
                name="lookup",
                display_name="Lookup",
                description="Lookup a value",
                parameters={
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
                handler=lookup,
            )
        ],
    )

    events = [event async for event in agent.arun("hello", user_id="u1")]

    assert [event.event for event in events].count("ToolCallCompleted") == 6
    assert events[-1].event == "RunContent"
    assert events[-1].content == "calls: 6"


@pytest.mark.asyncio
async def test_base_agent_rejects_sync_tool_handlers():
    def sync_handler(value: str) -> dict[str, str]:
        return {"value": value}

    agent = BaseAgent(
        provider=FakeProvider(),
        instructions="test",
        tools=[
            AgentTool(
                name="lookup",
                display_name="Lookup",
                description="Lookup a value",
                parameters={"type": "object", "properties": {}},
                handler=sync_handler,  # type: ignore[arg-type]
            )
        ],
    )

    events = [event async for event in agent.arun("hello", user_id="u1")]

    assert events[2].tool is not None
    assert events[2].tool.result["error"].startswith("Invalid tool arguments:")
