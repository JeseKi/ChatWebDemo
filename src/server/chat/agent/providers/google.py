# -*- coding: utf-8 -*-
"""Google Gemini provider adapter."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from ..contracts import (
    LLMMessage,
    LLMProvider,
    LLMProviderEvent,
    LLMToolCall,
)
from ..tools import AgentTool
from .usage import google_usage


class GoogleGeminiProvider(LLMProvider):
    name = "google"

    def __init__(
        self,
        *,
        api_key: str,
        model_id: str,
        max_output: int | None = None,
        base_url: str | None = None,
    ):
        self.api_key = api_key
        self.model_id = model_id
        self.max_output = max_output
        self.base_url = base_url
        self._client: Any | None = None
        self._types: Any | None = None

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                from google import genai
                from google.genai import types
            except ModuleNotFoundError as exc:  # pragma: no cover - environment setup
                raise RuntimeError(
                    "google-genai package is required for Google chat models"
                ) from exc
            self._types = types
            http_options = (
                types.HttpOptions(base_url=self.base_url) if self.base_url else None
            )
            self._client = genai.Client(
                api_key=self.api_key,
                http_options=http_options,
            )
        return self._client

    @property
    def types(self) -> Any:
        _ = self.client
        return self._types

    async def stream_turn(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[AgentTool],
        user_id: str,
        allow_tools: bool,
    ) -> AsyncIterator[LLMProviderEvent]:
        contents, system_instruction = _to_google_contents(messages, self.types)
        config_kwargs: dict[str, Any] = {
            "system_instruction": system_instruction,
        }
        if self.max_output is not None:
            config_kwargs["max_output_tokens"] = self.max_output
        if allow_tools:
            config_kwargs["tools"] = [_google_tool_config(tools, self.types)]

        config = self.types.GenerateContentConfig(**config_kwargs)
        stream = await self.client.aio.models.generate_content_stream(
            model=self.model_id,
            contents=contents,
            config=config,
        )

        tool_calls: list[LLMToolCall] = []
        token_usage = None
        async for chunk in stream:
            usage = google_usage(
                self.name,
                self.model_id,
                getattr(chunk, "usage_metadata", None)
                or getattr(chunk, "usageMetadata", None),
            )
            if usage is not None:
                token_usage = usage

            text = getattr(chunk, "text", None)
            if text:
                yield LLMProviderEvent(type="content_delta", content=str(text))

            for function_call in _extract_google_function_calls(chunk):
                call_id = str(
                    getattr(function_call, "id", None)
                    or getattr(function_call, "name", "call")
                )
                name = str(getattr(function_call, "name", ""))
                args = getattr(function_call, "args", None)
                if name:
                    tool_calls.append(
                        LLMToolCall(
                            id=call_id,
                            name=name,
                            arguments=args if isinstance(args, dict) else {},
                            raw={"args": args or {}},
                        )
                    )

        for tool_call in tool_calls:
            yield LLMProviderEvent(type="tool_call", tool_call=tool_call)
        if token_usage is not None:
            yield LLMProviderEvent(type="usage", usage=token_usage)

    def build_tool_message(self, tool_call: LLMToolCall, output: Any) -> LLMMessage:
        return LLMMessage(
            role="tool",
            name=tool_call.name,
            tool_call_id=tool_call.id,
            content=json.dumps(output, ensure_ascii=False, default=str),
            provider_metadata={
                "google_function_response": {
                    "name": tool_call.name,
                    "response": output if isinstance(output, dict) else {"result": output},
                }
            },
        )


def _to_google_contents(
    messages: list[LLMMessage],
    types: Any,
) -> tuple[list[Any], str | None]:
    system_instruction = None
    contents: list[Any] = []
    for message in messages:
        if message.role == "system":
            system_instruction = message.content or ""
            continue
        if message.role == "assistant":
            parts = []
            if message.content:
                parts.append(types.Part.from_text(text=message.content))
            for tool_call in message.tool_calls:
                parts.append(
                    types.Part.from_function_call(
                        name=tool_call.name,
                        args=tool_call.arguments,
                    )
                )
            if parts:
                contents.append(types.Content(role="model", parts=parts))
            continue
        if message.role == "tool":
            response = message.provider_metadata.get("google_function_response")
            if isinstance(response, dict):
                contents.append(
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_function_response(
                                name=str(response.get("name") or message.name or ""),
                                response=response.get("response") or {},
                            )
                        ],
                    )
                )
            continue
        parts = []
        if message.content:
            parts.append(types.Part.from_text(text=message.content))
        for image in message.images:
            parts.append(types.Part.from_bytes(data=image.data_bytes, mime_type=image.mime_type))
        if not parts:
            parts.append(types.Part.from_text(text=""))
        contents.append(types.Content(role="user", parts=parts))
    return contents, system_instruction


def _google_tool_config(tools: list[AgentTool], types: Any) -> Any:
    declarations = [
        types.FunctionDeclaration(
            name=tool.name,
            description=tool.description,
            parameters=tool.parameters,
        )
        for tool in tools
    ]
    return types.Tool(function_declarations=declarations)


def _extract_google_function_calls(chunk: Any) -> list[Any]:
    calls: list[Any] = []
    for candidate in getattr(chunk, "candidates", []) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", []) or []:
            function_call = getattr(part, "function_call", None)
            if function_call is not None:
                calls.append(function_call)
    return calls
