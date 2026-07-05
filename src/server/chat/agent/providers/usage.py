# -*- coding: utf-8 -*-
"""Provider response usage normalization helpers."""

from __future__ import annotations

from typing import Any

from ..contracts import LLMTokenUsage


def openai_chat_usage(provider: str, model_id: str, value: Any) -> LLMTokenUsage | None:
    raw = to_plain_dict(value)
    if not raw:
        return None
    return LLMTokenUsage(
        provider=provider,
        model_id=model_id,
        input_tokens=_first_int(raw, ("prompt_tokens",)),
        output_tokens=_first_int(raw, ("completion_tokens",)),
        total_tokens=_first_int(raw, ("total_tokens",)),
        reasoning_tokens=_first_int(
            raw,
            ("completion_tokens_details", "reasoning_tokens"),
            ("output_tokens_details", "reasoning_tokens"),
        ),
        cached_input_tokens=_first_int(
            raw,
            ("prompt_tokens_details", "cached_tokens"),
            ("prompt_cache_hit_tokens",),
        ),
        raw_usage=raw,
    )


def openai_responses_usage(
    provider: str,
    model_id: str,
    value: Any,
) -> LLMTokenUsage | None:
    raw = to_plain_dict(value)
    if not raw:
        return None
    return LLMTokenUsage(
        provider=provider,
        model_id=model_id,
        input_tokens=_first_int(raw, ("input_tokens",)),
        output_tokens=_first_int(raw, ("output_tokens",)),
        total_tokens=_first_int(raw, ("total_tokens",)),
        reasoning_tokens=_first_int(raw, ("output_tokens_details", "reasoning_tokens")),
        cached_input_tokens=_first_int(raw, ("input_tokens_details", "cached_tokens")),
        raw_usage=raw,
    )


def anthropic_usage(provider: str, model_id: str, value: Any) -> LLMTokenUsage | None:
    raw = to_plain_dict(value)
    if not raw:
        return None
    cached = _sum_ints(
        _first_int(raw, ("cache_creation_input_tokens",)),
        _first_int(raw, ("cache_read_input_tokens",)),
    )
    return LLMTokenUsage(
        provider=provider,
        model_id=model_id,
        input_tokens=_first_int(raw, ("input_tokens",)),
        output_tokens=_first_int(raw, ("output_tokens",)),
        reasoning_tokens=_first_int(
            raw,
            ("output_tokens_details", "thinking_tokens"),
            ("thinking_tokens",),
        ),
        cached_input_tokens=cached,
        raw_usage=raw,
    )


def google_usage(provider: str, model_id: str, value: Any) -> LLMTokenUsage | None:
    raw = to_plain_dict(value)
    if not raw:
        return None
    return LLMTokenUsage(
        provider=provider,
        model_id=model_id,
        input_tokens=_first_int(raw, ("promptTokenCount",), ("prompt_token_count",)),
        output_tokens=_first_int(
            raw,
            ("candidatesTokenCount",),
            ("candidates_token_count",),
        ),
        total_tokens=_first_int(raw, ("totalTokenCount",), ("total_token_count",)),
        reasoning_tokens=_first_int(raw, ("thoughtsTokenCount",), ("thoughts_token_count",)),
        cached_input_tokens=_first_int(
            raw,
            ("cachedContentTokenCount",),
            ("cached_content_token_count",),
        ),
        tool_tokens=_first_int(
            raw,
            ("toolUsePromptTokenCount",),
            ("tool_use_prompt_token_count",),
        ),
        raw_usage=raw,
    )


def to_plain_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        return dumped if isinstance(dumped, dict) else {}
    if hasattr(value, "to_dict"):
        dumped = value.to_dict()
        return dumped if isinstance(dumped, dict) else {}
    output: dict[str, Any] = {}
    for key in (
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
        "promptTokenCount",
        "candidatesTokenCount",
        "totalTokenCount",
        "toolUsePromptTokenCount",
        "thoughtsTokenCount",
        "cachedContentTokenCount",
    ):
        if hasattr(value, key):
            output[key] = getattr(value, key)
    return output


def _first_int(raw: dict[str, Any], *paths: tuple[str, ...]) -> int | None:
    for path in paths:
        value: Any = raw
        for key in path:
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(key)
        parsed = _int_or_none(value)
        if parsed is not None:
            return parsed
    return None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sum_ints(*values: int | None) -> int | None:
    total = sum(value for value in values if value is not None)
    return total if total > 0 else None
