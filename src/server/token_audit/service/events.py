# -*- coding: utf-8 -*-
"""Token usage event queries."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from src.server.auth.models import User

from ..dao import TokenUsageAuditDAO
from ..schemas import TokenAuditEventOut, TokenAuditEventsResponse
from .utils import load_raw_usage


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
    users_by_id = (
        {
            user.id: user.username
            for user in db.query(User).filter(
                User.id.in_({event.user_id for event in events})
            )
        }
        if events
        else {}
    )
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
                raw_usage=load_raw_usage(event.raw_usage_json),
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
