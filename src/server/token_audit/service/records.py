# -*- coding: utf-8 -*-
"""Token usage audit record creation."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..dao import TokenUsageAuditDAO
from ..models import TokenUsageAudit
from .utils import positive_int


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
    normalized_input = positive_int(input_tokens)
    normalized_output = positive_int(output_tokens)
    normalized_total = positive_int(total_tokens)
    if normalized_total == 0:
        normalized_total = (
            normalized_input
            + normalized_output
            + positive_int(reasoning_tokens)
            + positive_int(tool_tokens)
        )
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
        reasoning_tokens=positive_int(reasoning_tokens),
        cached_input_tokens=positive_int(cached_input_tokens),
        tool_tokens=positive_int(tool_tokens),
        raw_usage=raw_usage,
        commit=commit,
    )
