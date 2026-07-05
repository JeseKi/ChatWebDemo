# -*- coding: utf-8 -*-
"""Chat context compression DAO operations."""

from __future__ import annotations

from src.server.dao.dao_base import BaseDAO
from src.server.chat.models import ChatContextCompression


class ChatCompressionDAO(BaseDAO):
    def create_context_compression(
        self,
        *,
        session_id: str,
        user_id: int,
        head_end_message_id: int,
        tail_start_message_id: int,
        source_leaf_message_id: int,
        previous_compression_id: int | None,
        trigger: str,
        summary: str,
        summary_model_id: str | None,
        original_token_estimate: int,
        summary_token_estimate: int,
        message_count: int,
        commit: bool = True,
    ) -> ChatContextCompression:
        compression = ChatContextCompression(
            session_id=session_id,
            user_id=user_id,
            head_end_message_id=head_end_message_id,
            tail_start_message_id=tail_start_message_id,
            source_leaf_message_id=source_leaf_message_id,
            previous_compression_id=previous_compression_id,
            trigger=trigger,
            summary=summary,
            summary_model_id=summary_model_id,
            original_token_estimate=original_token_estimate,
            summary_token_estimate=summary_token_estimate,
            message_count=message_count,
        )
        self.db_session.add(compression)
        self.db_session.flush()
        if commit:
            self.db_session.commit()
            self.db_session.refresh(compression)
        return compression

    def list_context_compressions(
        self, *, session_id: str, user_id: int
    ) -> list[ChatContextCompression]:
        return (
            self.db_session.query(ChatContextCompression)
            .filter(
                ChatContextCompression.session_id == session_id,
                ChatContextCompression.user_id == user_id,
            )
            .order_by(ChatContextCompression.created_at.asc(), ChatContextCompression.id.asc())
            .all()
        )
