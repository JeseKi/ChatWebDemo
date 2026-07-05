# -*- coding: utf-8 -*-
"""Token usage audit admin routes."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.server.auth.dependencies import get_current_admin
from src.server.auth.models import User
from src.server.dao.dao_base import run_in_thread
from src.server.database import get_db

from . import service
from .schemas import (
    TokenAuditBreakdownOut,
    TokenAuditEventsResponse,
    TokenAuditSummaryOut,
    TokenAuditTimeseriesPointOut,
)

router = APIRouter(prefix="/api/admin/token-audit", tags=["Token 审计"])


@router.get(
    "/summary",
    response_model=list[TokenAuditSummaryOut],
    summary="获取用户 token 消耗汇总",
)
async def get_token_audit_summary(
    user_id: int | None = None,
    provider: str | None = None,
    model_id: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    def _list():
        return service.list_summary(
            db,
            user_id=user_id,
            provider=provider,
            model_id=model_id,
            start_at=start_at,
            end_at=end_at,
        )

    return await run_in_thread(_list)


@router.get(
    "/timeseries",
    response_model=list[TokenAuditTimeseriesPointOut],
    summary="获取 token 消耗时间趋势",
)
async def get_token_audit_timeseries(
    user_id: int | None = None,
    provider: str | None = None,
    model_id: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    group_by: Literal["hour", "day"] = "day",
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    def _list():
        return service.list_timeseries(
            db,
            user_id=user_id,
            provider=provider,
            model_id=model_id,
            start_at=start_at,
            end_at=end_at,
            group_by=group_by,
        )

    return await run_in_thread(_list)


@router.get(
    "/breakdown",
    response_model=list[TokenAuditBreakdownOut],
    summary="获取 token 消耗维度分布",
)
async def get_token_audit_breakdown(
    dimension: Literal["user", "provider", "model"],
    user_id: int | None = None,
    provider: str | None = None,
    model_id: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    def _list():
        return service.list_breakdown(
            db,
            dimension=dimension,
            user_id=user_id,
            provider=provider,
            model_id=model_id,
            start_at=start_at,
            end_at=end_at,
            limit=limit,
        )

    return await run_in_thread(_list)


@router.get(
    "/events",
    response_model=TokenAuditEventsResponse,
    summary="获取 token 消耗请求明细",
)
async def get_token_audit_events(
    user_id: int | None = None,
    provider: str | None = None,
    model_id: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    def _list():
        return service.list_events(
            db,
            user_id=user_id,
            provider=provider,
            model_id=model_id,
            start_at=start_at,
            end_at=end_at,
            limit=limit,
            offset=offset,
        )

    return await run_in_thread(_list)
