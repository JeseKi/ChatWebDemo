# -*- coding: utf-8 -*-
"""Chat session share DAO."""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.server.dao.dao_base import BaseDAO

from ..models import ChatSessionShare


class ChatShareDAO(BaseDAO):
    def __init__(self, db_session: Session):
        super().__init__(db_session)

    def create_session_share(
        self,
        *,
        owner_user_id: int,
        source_session_id: str,
        source_active_leaf_message_id: int | None,
        title: str,
        snapshot_json: str,
        message_count: int,
    ) -> ChatSessionShare:
        share = ChatSessionShare(
            owner_user_id=owner_user_id,
            source_session_id=source_session_id,
            source_active_leaf_message_id=source_active_leaf_message_id,
            title=title,
            snapshot_json=snapshot_json,
            message_count=message_count,
        )
        self.db_session.add(share)
        self.db_session.flush()
        return share

    def get_session_share_by_id(self, share_id: int) -> ChatSessionShare | None:
        return (
            self.db_session.query(ChatSessionShare)
            .filter(ChatSessionShare.id == share_id)
            .first()
        )

    def get_session_share_by_snapshot(
        self,
        *,
        owner_user_id: int,
        source_session_id: str,
        source_active_leaf_message_id: int | None,
        snapshot_json: str,
    ) -> ChatSessionShare | None:
        return (
            self.db_session.query(ChatSessionShare)
            .filter(
                ChatSessionShare.owner_user_id == owner_user_id,
                ChatSessionShare.source_session_id == source_session_id,
                ChatSessionShare.source_active_leaf_message_id
                == source_active_leaf_message_id,
                ChatSessionShare.snapshot_json == snapshot_json,
            )
            .order_by(ChatSessionShare.id.desc())
            .first()
        )
