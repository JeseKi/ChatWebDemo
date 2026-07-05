# -*- coding: utf-8 -*-
"""Token usage audit DAO."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.server.auth.models import User
from src.server.dao.dao_base import BaseDAO

from .models import TokenUsageAudit


class TokenUsageAuditDAO(BaseDAO):
    def __init__(self, db_session: Session):
        super().__init__(db_session)

    def create(
        self,
        *,
        user_id: int,
        session_id: str,
        run_id: str,
        request_index: int,
        provider: str,
        model_id: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
        reasoning_tokens: int = 0,
        cached_input_tokens: int = 0,
        tool_tokens: int = 0,
        raw_usage: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> TokenUsageAudit:
        audit = TokenUsageAudit(
            user_id=user_id,
            session_id=session_id,
            run_id=run_id,
            request_index=request_index,
            provider=provider,
            model_id=model_id,
            input_tokens=max(input_tokens, 0),
            output_tokens=max(output_tokens, 0),
            total_tokens=max(total_tokens, 0),
            reasoning_tokens=max(reasoning_tokens, 0),
            cached_input_tokens=max(cached_input_tokens, 0),
            tool_tokens=max(tool_tokens, 0),
            raw_usage_json=(
                json.dumps(raw_usage, ensure_ascii=False, default=str)
                if raw_usage
                else None
            ),
        )
        self.db_session.add(audit)
        self.db_session.flush()
        if commit:
            self.db_session.commit()
            self.db_session.refresh(audit)
        return audit

    def list_events(
        self,
        *,
        user_id: int | None = None,
        provider: str | None = None,
        model_id: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TokenUsageAudit]:
        query = self._filtered_query(
            user_id=user_id,
            provider=provider,
            model_id=model_id,
            start_at=start_at,
            end_at=end_at,
        )
        return (
            query.order_by(TokenUsageAudit.created_at.desc(), TokenUsageAudit.id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def list_events_for_aggregation(
        self,
        *,
        user_id: int | None = None,
        provider: str | None = None,
        model_id: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> list[TokenUsageAudit]:
        return (
            self._filtered_query(
                user_id=user_id,
                provider=provider,
                model_id=model_id,
                start_at=start_at,
                end_at=end_at,
            )
            .order_by(TokenUsageAudit.created_at.asc(), TokenUsageAudit.id.asc())
            .all()
        )

    def count_events(
        self,
        *,
        user_id: int | None = None,
        provider: str | None = None,
        model_id: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> int:
        return int(
            self._filtered_query(
                user_id=user_id,
                provider=provider,
                model_id=model_id,
                start_at=start_at,
                end_at=end_at,
            ).count()
            or 0
        )

    def list_user_summary(
        self,
        *,
        user_id: int | None = None,
        provider: str | None = None,
        model_id: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> list[tuple[Any, ...]]:
        query = (
            self._filtered_query(
                user_id=user_id,
                provider=provider,
                model_id=model_id,
                start_at=start_at,
                end_at=end_at,
            )
            .join(User, User.id == TokenUsageAudit.user_id)
            .with_entities(
                TokenUsageAudit.user_id,
                User.username,
                User.email,
                User.name,
                func.count(TokenUsageAudit.id).label("request_count"),
                func.coalesce(func.sum(TokenUsageAudit.input_tokens), 0).label(
                    "input_tokens"
                ),
                func.coalesce(func.sum(TokenUsageAudit.output_tokens), 0).label(
                    "output_tokens"
                ),
                func.coalesce(func.sum(TokenUsageAudit.total_tokens), 0).label(
                    "total_tokens"
                ),
                func.coalesce(func.sum(TokenUsageAudit.reasoning_tokens), 0).label(
                    "reasoning_tokens"
                ),
                func.coalesce(func.sum(TokenUsageAudit.cached_input_tokens), 0).label(
                    "cached_input_tokens"
                ),
                func.coalesce(func.sum(TokenUsageAudit.tool_tokens), 0).label(
                    "tool_tokens"
                ),
            )
            .group_by(TokenUsageAudit.user_id, User.username, User.email, User.name)
            .order_by(func.sum(TokenUsageAudit.total_tokens).desc())
        )
        return query.all()

    def _filtered_query(
        self,
        *,
        user_id: int | None,
        provider: str | None,
        model_id: str | None,
        start_at: datetime | None,
        end_at: datetime | None,
    ):
        query = self.db_session.query(TokenUsageAudit)
        if user_id is not None:
            query = query.filter(TokenUsageAudit.user_id == user_id)
        if provider:
            query = query.filter(TokenUsageAudit.provider == provider)
        if model_id:
            query = query.filter(TokenUsageAudit.model_id == model_id)
        if start_at is not None:
            query = query.filter(TokenUsageAudit.created_at >= start_at)
        if end_at is not None:
            query = query.filter(TokenUsageAudit.created_at <= end_at)
        return query
