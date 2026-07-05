# -*- coding: utf-8 -*-
"""Chat session DAO operations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from src.server.dao.dao_base import BaseDAO
from src.server.chat.models import ChatMessage, ChatSession
from .json_utils import MAX_SESSION_ID_GENERATION_ATTEMPTS, generate_chat_id


class _SessionMessageLookup(Protocol):
    def get_message(self, *, message_id: int, user_id: int) -> ChatMessage | None:
        ...

    def get_session(self, *, session_id: str, user_id: int) -> ChatSession | None:
        ...


class ChatSessionDAO(BaseDAO):
    def create_session(self, *, user_id: int, title: str, commit: bool = True) -> ChatSession:
        for _ in range(MAX_SESSION_ID_GENERATION_ATTEMPTS):
            session_id = generate_chat_id()
            if self.get_session(session_id=session_id, user_id=user_id):
                continue

            session = ChatSession(id=session_id, user_id=user_id, title=title)
            self.db_session.add(session)
            self.db_session.flush()
            if commit:
                self.db_session.commit()
                self.db_session.refresh(session)
            return session

        raise RuntimeError("聊天会话ID生成失败，请重试")

    def get_session(self, *, session_id: str, user_id: int) -> ChatSession | None:
        return (
            self.db_session.query(ChatSession)
            .filter(
                ChatSession.id == session_id,
                ChatSession.user_id == user_id,
                ChatSession.deleted_at.is_(None),
            )
            .first()
        )

    def get_session_by_message_id(
        self: _SessionMessageLookup, *, message_id: int, user_id: int
    ) -> tuple[ChatSession, ChatMessage] | None:
        message = self.get_message(message_id=message_id, user_id=user_id)
        if not message:
            return None
        session = self.get_session(session_id=message.session_id, user_id=user_id)
        if not session:
            return None
        return session, message

    def list_sessions(self, *, user_id: int, limit: int = 50) -> list[ChatSession]:
        return (
            self.db_session.query(ChatSession)
            .filter(ChatSession.user_id == user_id, ChatSession.deleted_at.is_(None))
            .order_by(ChatSession.updated_at.desc(), ChatSession.created_at.desc())
            .limit(limit)
            .all()
        )

    def update_session_title(
        self, *, session_id: str, user_id: int, title: str, commit: bool = True
    ) -> ChatSession | None:
        session = self.get_session(session_id=session_id, user_id=user_id)
        if not session:
            return None
        session.title = title
        session.updated_at = datetime.now(timezone.utc)
        self.db_session.flush()
        if commit:
            self.db_session.commit()
            self.db_session.refresh(session)
        return session

    def delete_session(self, *, session_id: str, user_id: int, commit: bool = True) -> bool:
        session = self.get_session(session_id=session_id, user_id=user_id)
        if not session:
            return False
        now = datetime.now(timezone.utc)
        session.deleted_at = now
        session.updated_at = now
        self.db_session.flush()
        if commit:
            self.db_session.commit()
        return True

    def touch_session(self, *, session_id: str, user_id: int) -> None:
        session = self.get_session(session_id=session_id, user_id=user_id)
        if session:
            session.updated_at = datetime.now(timezone.utc)
