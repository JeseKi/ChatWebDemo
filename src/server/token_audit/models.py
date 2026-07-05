# -*- coding: utf-8 -*-
"""Token usage audit persistence models."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.server.database import Base


class TokenUsageAudit(Base):
    __tablename__ = "token_usage_audits"
    __table_args__ = (
        UniqueConstraint("run_id", "request_index", name="uq_token_usage_run_request"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    request_index: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    model_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reasoning_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cached_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    raw_usage_json: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
