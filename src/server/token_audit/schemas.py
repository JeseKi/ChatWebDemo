# -*- coding: utf-8 -*-
"""Token usage audit API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TokenAuditSummaryOut(BaseModel):
    user_id: int
    username: str
    email: str
    name: str | None = None
    request_count: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    reasoning_tokens: int
    cached_input_tokens: int
    tool_tokens: int


class TokenAuditEventOut(BaseModel):
    id: int
    user_id: int
    username: str | None = None
    session_id: str
    run_id: str
    request_index: int
    provider: str
    model_id: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    reasoning_tokens: int
    cached_input_tokens: int
    tool_tokens: int
    raw_usage: dict[str, Any] | None = None
    created_at: datetime

    model_config = ConfigDict(protected_namespaces=())


class TokenAuditEventsResponse(BaseModel):
    items: list[TokenAuditEventOut]
    total: int
    limit: int = Field(..., ge=1)
    offset: int = Field(..., ge=0)
