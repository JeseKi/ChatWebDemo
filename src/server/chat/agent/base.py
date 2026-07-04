# -*- coding: utf-8 -*-
"""Base async Agent loop."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from .contracts import LLMMessage, LLMProvider, LLMToolCall
from .tools import AgentTool


@dataclass
class ChatToolEventPayload:
    tool_name: str
    tool_args: dict[str, Any]
    result: Any = None
    tool_call_id: str | None = None


@dataclass
class ChatRunEvent:
    event: str
    content: str | None = None
    reasoning_content: str | None = None
    tool: ChatToolEventPayload | None = None


@dataclass
class ToolExecutionResult:
    id: str
    name: str
    arguments: dict[str, Any]
    output: Any


class BaseAgent:
    """Provider-neutral async tool loop for a single ChatWeb agent."""

    def __init__(
        self,
        *,
        provider: LLMProvider,
        instructions: str,
        tools: list[AgentTool] | None = None,
        max_tool_calls: int = 4,
    ):
        self.provider = provider
        self.instructions = instructions
        self.tools = tools or []
        self.max_tool_calls = max_tool_calls
        self.tool_specs = [tool.spec for tool in self.tools]
        self._tool_map = {tool.name: tool for tool in self.tools}

    async def arun(
        self,
        prompt: str,
        *,
        user_id: str,
    ) -> AsyncIterator[ChatRunEvent]:
        messages = self.provider.build_initial_messages(
            instructions=self.instructions,
            prompt=prompt,
        )
        tool_calls_used = 0

        while True:
            content_chunks: list[str] = []
            reasoning_chunks: list[str] = []
            tool_calls: list[LLMToolCall] = []
            provider_metadata: dict[str, Any] = {}
            allow_tools = bool(self.tools) and tool_calls_used < self.max_tool_calls

            async for event in self.provider.stream_turn(
                messages,
                tools=self.tools,
                user_id=user_id,
                allow_tools=allow_tools,
            ):
                if event.type == "content_delta" and event.content:
                    content_chunks.append(event.content)
                    yield ChatRunEvent(event="RunContent", content=event.content)
                    continue

                if event.type == "reasoning_delta" and event.reasoning_content:
                    reasoning_chunks.append(event.reasoning_content)
                    yield ChatRunEvent(
                        event="RunReasoningContent",
                        reasoning_content=event.reasoning_content,
                    )
                    continue

                if event.type == "tool_call" and event.tool_call:
                    tool_calls.append(event.tool_call)
                    continue

                if event.type == "metadata":
                    provider_metadata.update(event.provider_metadata)

            if not tool_calls:
                return

            assistant_content = "".join(content_chunks) or None
            reasoning_content = "".join(reasoning_chunks) or None
            messages.append(
                self.provider.build_assistant_message(
                    content=assistant_content,
                    reasoning_content=reasoning_content,
                    tool_calls=tool_calls,
                    provider_metadata=provider_metadata,
                )
            )

            for tool_call in tool_calls:
                tool_calls_used += 1
                result = await self._execute_tool_call(
                    tool_call,
                    allowed=tool_calls_used <= self.max_tool_calls,
                )
                yield ChatRunEvent(
                    event="ToolCallStarted",
                    tool=ChatToolEventPayload(
                        tool_name=result.name,
                        tool_args=result.arguments,
                        tool_call_id=result.id,
                    ),
                )
                yield ChatRunEvent(
                    event="ToolCallCompleted",
                    tool=ChatToolEventPayload(
                        tool_name=result.name,
                        tool_args=result.arguments,
                        result=result.output,
                        tool_call_id=result.id,
                    ),
                )
                messages.append(self.provider.build_tool_message(tool_call, result.output))

            if tool_calls_used >= self.max_tool_calls:
                messages.append(
                    LLMMessage(
                        role="user",
                        content=(
                            "Tool call limit reached. Use the available tool results "
                            "to provide the final answer."
                        ),
                    )
                )

    async def _execute_tool_call(
        self,
        tool_call: LLMToolCall,
        *,
        allowed: bool,
    ) -> ToolExecutionResult:
        if not allowed:
            return ToolExecutionResult(
                id=tool_call.id,
                name=tool_call.name,
                arguments=tool_call.arguments,
                output={"error": "Tool call limit reached."},
            )

        tool = self._tool_map.get(tool_call.name)
        if tool is None:
            return ToolExecutionResult(
                id=tool_call.id,
                name=tool_call.name,
                arguments=tool_call.arguments,
                output={"error": f"Unknown tool: {tool_call.name}"},
            )

        try:
            output = await tool.arun(**tool_call.arguments)
        except TypeError as exc:
            output = {"error": f"Invalid tool arguments: {exc}"}
        except Exception as exc:  # pragma: no cover - defensive tool isolation
            output = {"error": f"Tool execution failed: {exc}"}

        return ToolExecutionResult(
            id=tool_call.id,
            name=tool_call.name,
            arguments=tool_call.arguments,
            output=output,
        )

