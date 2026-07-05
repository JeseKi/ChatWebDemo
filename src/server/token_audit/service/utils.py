# -*- coding: utf-8 -*-
"""Token audit service helpers."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable

from ..models import TokenUsageAudit
from ..schemas import TokenAuditBreakdownOut


def positive_int(value: int | None) -> int:
    if value is None:
        return 0
    return max(int(value), 0)


def load_raw_usage(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def bucket_start(value: datetime, group_by: str) -> datetime:
    if group_by == "hour":
        return value.replace(minute=0, second=0, microsecond=0)
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def empty_aggregate() -> dict[str, int]:
    return {
        "request_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "reasoning_tokens": 0,
        "cached_input_tokens": 0,
        "tool_tokens": 0,
    }


def add_event(target: dict[str, int], event: TokenUsageAudit) -> None:
    target["request_count"] += 1
    target["input_tokens"] += event.input_tokens
    target["output_tokens"] += event.output_tokens
    target["total_tokens"] += event.total_tokens
    target["reasoning_tokens"] += event.reasoning_tokens
    target["cached_input_tokens"] += event.cached_input_tokens
    target["tool_tokens"] += event.tool_tokens


def dimension_key_getter(dimension: str) -> Callable[[TokenUsageAudit], str]:
    if dimension == "provider":
        return lambda event: event.provider
    if dimension == "model":
        return lambda event: event.model_id
    raise ValueError(f"Unsupported token audit breakdown dimension: {dimension}")


def breakdown_out(
    *,
    key: str,
    label: str,
    values: dict[str, int],
) -> TokenAuditBreakdownOut:
    return TokenAuditBreakdownOut(
        key=key,
        label=label,
        request_count=values["request_count"],
        input_tokens=values["input_tokens"],
        output_tokens=values["output_tokens"],
        total_tokens=values["total_tokens"],
        reasoning_tokens=values["reasoning_tokens"],
        cached_input_tokens=values["cached_input_tokens"],
        tool_tokens=values["tool_tokens"],
    )
