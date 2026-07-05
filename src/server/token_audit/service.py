# -*- coding: utf-8 -*-
"""Token usage audit service."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from src.server.auth.models import User

from .dao import TokenUsageAuditDAO
from .models import TokenUsageAudit
from .schemas import (
    TokenAuditBreakdownOut,
    TokenAuditEventOut,
    TokenAuditEventsResponse,
    TokenAuditSummaryOut,
    TokenAuditTimeseriesPointOut,
)


def create_usage_audit(
    db: Session,
    *,
    user_id: int,
    session_id: str,
    run_id: str,
    request_index: int,
    provider: str,
    model_id: str,
    input_tokens: int | None,
    output_tokens: int | None,
    total_tokens: int | None,
    reasoning_tokens: int | None,
    cached_input_tokens: int | None,
    tool_tokens: int | None,
    raw_usage: dict[str, Any] | None,
    commit: bool = True,
) -> TokenUsageAudit:
    normalized_input = _positive_int(input_tokens)
    normalized_output = _positive_int(output_tokens)
    normalized_total = _positive_int(total_tokens)
    if normalized_total == 0:
        normalized_total = normalized_input + normalized_output + _positive_int(
            reasoning_tokens
        ) + _positive_int(tool_tokens)
    return TokenUsageAuditDAO(db).create(
        user_id=user_id,
        session_id=session_id,
        run_id=run_id,
        request_index=request_index,
        provider=provider,
        model_id=model_id,
        input_tokens=normalized_input,
        output_tokens=normalized_output,
        total_tokens=normalized_total,
        reasoning_tokens=_positive_int(reasoning_tokens),
        cached_input_tokens=_positive_int(cached_input_tokens),
        tool_tokens=_positive_int(tool_tokens),
        raw_usage=raw_usage,
        commit=commit,
    )


def list_summary(
    db: Session,
    *,
    user_id: int | None = None,
    provider: str | None = None,
    model_id: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> list[TokenAuditSummaryOut]:
    rows = TokenUsageAuditDAO(db).list_user_summary(
        user_id=user_id,
        provider=provider,
        model_id=model_id,
        start_at=start_at,
        end_at=end_at,
    )
    output: list[TokenAuditSummaryOut] = []
    for (
        row_user_id,
        username,
        email,
        name,
        request_count,
        input_tokens,
        output_tokens,
        total_tokens,
        reasoning_tokens,
        cached_input_tokens,
        tool_tokens,
    ) in rows:
        output.append(
            TokenAuditSummaryOut(
                user_id=int(row_user_id),
                username=str(username),
                email=str(email),
                name=name,
                request_count=int(request_count or 0),
                input_tokens=int(input_tokens or 0),
                output_tokens=int(output_tokens or 0),
                total_tokens=int(total_tokens or 0),
                reasoning_tokens=int(reasoning_tokens or 0),
                cached_input_tokens=int(cached_input_tokens or 0),
                tool_tokens=int(tool_tokens or 0),
            )
        )
    return output


def list_timeseries(
    db: Session,
    *,
    user_id: int | None = None,
    provider: str | None = None,
    model_id: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    group_by: str = "day",
) -> list[TokenAuditTimeseriesPointOut]:
    events = TokenUsageAuditDAO(db).list_events_for_aggregation(
        user_id=user_id,
        provider=provider,
        model_id=model_id,
        start_at=start_at,
        end_at=end_at,
    )
    buckets: dict[datetime, dict[str, int]] = {}
    for event in events:
        bucket_start = _bucket_start(event.created_at, group_by)
        bucket = buckets.setdefault(bucket_start, _empty_aggregate())
        _add_event(bucket, event)

    return [
        TokenAuditTimeseriesPointOut(bucket_start=bucket_start, **values)
        for bucket_start, values in sorted(buckets.items(), key=lambda item: item[0])
    ]


def list_breakdown(
    db: Session,
    *,
    dimension: str,
    user_id: int | None = None,
    provider: str | None = None,
    model_id: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    limit: int = 20,
) -> list[TokenAuditBreakdownOut]:
    if dimension == "user":
        user_rows = list_summary(
            db,
            user_id=user_id,
            provider=provider,
            model_id=model_id,
            start_at=start_at,
            end_at=end_at,
        )
        return [
            TokenAuditBreakdownOut(
                key=str(row.user_id),
                label=row.name or row.username,
                user_id=row.user_id,
                username=row.username,
                email=row.email,
                request_count=row.request_count,
                input_tokens=row.input_tokens,
                output_tokens=row.output_tokens,
                total_tokens=row.total_tokens,
                reasoning_tokens=row.reasoning_tokens,
                cached_input_tokens=row.cached_input_tokens,
                tool_tokens=row.tool_tokens,
            )
            for row in user_rows[:limit]
        ]

    key_getter = _dimension_key_getter(dimension)
    events = TokenUsageAuditDAO(db).list_events_for_aggregation(
        user_id=user_id,
        provider=provider,
        model_id=model_id,
        start_at=start_at,
        end_at=end_at,
    )
    aggregates: dict[str, dict[str, int]] = {}
    for event in events:
        key = key_getter(event)
        bucket = aggregates.setdefault(key, _empty_aggregate())
        _add_event(bucket, event)

    aggregate_rows = sorted(
        aggregates.items(),
        key=lambda item: (item[1]["total_tokens"], item[1]["request_count"], item[0]),
        reverse=True,
    )
    return [
        _breakdown_out(key=key, label=key, values=values)
        for key, values in aggregate_rows[:limit]
    ]


def list_events(
    db: Session,
    *,
    user_id: int | None = None,
    provider: str | None = None,
    model_id: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> TokenAuditEventsResponse:
    dao = TokenUsageAuditDAO(db)
    events = dao.list_events(
        user_id=user_id,
        provider=provider,
        model_id=model_id,
        start_at=start_at,
        end_at=end_at,
        limit=limit,
        offset=offset,
    )
    users_by_id = {
        user.id: user.username
        for user in db.query(User).filter(User.id.in_({event.user_id for event in events}))
    } if events else {}
    return TokenAuditEventsResponse(
        items=[
            TokenAuditEventOut(
                id=event.id,
                user_id=event.user_id,
                username=users_by_id.get(event.user_id),
                session_id=event.session_id,
                run_id=event.run_id,
                request_index=event.request_index,
                provider=event.provider,
                model_id=event.model_id,
                input_tokens=event.input_tokens,
                output_tokens=event.output_tokens,
                total_tokens=event.total_tokens,
                reasoning_tokens=event.reasoning_tokens,
                cached_input_tokens=event.cached_input_tokens,
                tool_tokens=event.tool_tokens,
                raw_usage=_load_raw_usage(event.raw_usage_json),
                created_at=event.created_at,
            )
            for event in events
        ],
        total=dao.count_events(
            user_id=user_id,
            provider=provider,
            model_id=model_id,
            start_at=start_at,
            end_at=end_at,
        ),
        limit=limit,
        offset=offset,
    )


def _positive_int(value: int | None) -> int:
    if value is None:
        return 0
    return max(int(value), 0)


def _load_raw_usage(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _bucket_start(value: datetime, group_by: str) -> datetime:
    if group_by == "hour":
        return value.replace(minute=0, second=0, microsecond=0)
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def _empty_aggregate() -> dict[str, int]:
    return {
        "request_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "reasoning_tokens": 0,
        "cached_input_tokens": 0,
        "tool_tokens": 0,
    }


def _add_event(target: dict[str, int], event: TokenUsageAudit) -> None:
    target["request_count"] += 1
    target["input_tokens"] += event.input_tokens
    target["output_tokens"] += event.output_tokens
    target["total_tokens"] += event.total_tokens
    target["reasoning_tokens"] += event.reasoning_tokens
    target["cached_input_tokens"] += event.cached_input_tokens
    target["tool_tokens"] += event.tool_tokens


def _dimension_key_getter(dimension: str):
    if dimension == "provider":
        return lambda event: event.provider
    if dimension == "model":
        return lambda event: event.model_id
    raise ValueError(f"Unsupported token audit breakdown dimension: {dimension}")


def _breakdown_out(
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
