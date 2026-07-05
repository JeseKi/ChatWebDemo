# -*- coding: utf-8 -*-
"""Token usage aggregate queries."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..dao import TokenUsageAuditDAO
from ..schemas import (
    TokenAuditBreakdownOut,
    TokenAuditSummaryOut,
    TokenAuditTimeseriesPointOut,
)
from .utils import (
    add_event,
    breakdown_out,
    bucket_start,
    dimension_key_getter,
    empty_aggregate,
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
        current_bucket_start = bucket_start(event.created_at, group_by)
        bucket = buckets.setdefault(current_bucket_start, empty_aggregate())
        add_event(bucket, event)

    return [
        TokenAuditTimeseriesPointOut(bucket_start=current_bucket_start, **values)
        for current_bucket_start, values in sorted(
            buckets.items(),
            key=lambda item: item[0],
        )
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

    key_getter = dimension_key_getter(dimension)
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
        bucket = aggregates.setdefault(key, empty_aggregate())
        add_event(bucket, event)

    aggregate_rows = sorted(
        aggregates.items(),
        key=lambda item: (item[1]["total_tokens"], item[1]["request_count"], item[0]),
        reverse=True,
    )
    return [
        breakdown_out(key=key, label=key, values=values)
        for key, values in aggregate_rows[:limit]
    ]
