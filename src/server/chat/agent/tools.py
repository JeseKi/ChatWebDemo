# -*- coding: utf-8 -*-
"""Async Agent tool contracts."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

ToolHandler = Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class AgentTool:
    name: str
    display_name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler
    strict: bool = True

    @property
    def spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
                "strict": self.strict,
            },
        }

    async def arun(self, **arguments: Any) -> Any:
        result = self.handler(**arguments)
        if inspect.isawaitable(result):
            return await result
        raise TypeError(f"Tool handler for {self.name} must be async")


def get_tool_display_name(name: str, tools: list[AgentTool] | None = None) -> str:
    if tools:
        for tool in tools:
            if tool.name == name:
                return tool.display_name
    return name

