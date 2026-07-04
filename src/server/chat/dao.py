# -*- coding: utf-8 -*-
"""ChatWeb DAO."""

from __future__ import annotations

import json
import secrets
import string
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.server.dao.dao_base import BaseDAO

from .models import ChatMessage, ChatSession

SESSION_ID_LENGTH = 32
SESSION_ID_ALPHABET = string.ascii_letters + string.digits
MAX_SESSION_ID_GENERATION_ATTEMPTS = 5


class ChatDAO(BaseDAO):
    def __init__(self, db_session: Session):
        super().__init__(db_session)

    def create_session(self, *, user_id: int, title: str) -> ChatSession:
        for _ in range(MAX_SESSION_ID_GENERATION_ATTEMPTS):
            session_id = _generate_session_id()
            if self.get_session(session_id=session_id, user_id=user_id):
                continue

            session = ChatSession(id=session_id, user_id=user_id, title=title)
            self.db_session.add(session)
            self.db_session.commit()
            self.db_session.refresh(session)
            return session

        raise RuntimeError("聊天会话ID生成失败，请重试")

    def get_session(self, *, session_id: str, user_id: int) -> ChatSession | None:
        return (
            self.db_session.query(ChatSession)
            .filter(ChatSession.id == session_id, ChatSession.user_id == user_id)
            .first()
        )

    def list_sessions(self, *, user_id: int, limit: int = 50) -> list[ChatSession]:
        return (
            self.db_session.query(ChatSession)
            .filter(ChatSession.user_id == user_id)
            .order_by(ChatSession.updated_at.desc(), ChatSession.created_at.desc())
            .limit(limit)
            .all()
        )

    def list_messages(self, *, session_id: str, user_id: int) -> list[ChatMessage]:
        return (
            self.db_session.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id, ChatMessage.user_id == user_id)
            .order_by(ChatMessage.sequence.asc(), ChatMessage.id.asc())
            .all()
        )

    def append_message(
        self,
        *,
        session_id: str,
        user_id: int,
        role: str,
        content: str,
        tool_calls: list[dict[str, Any]] | None = None,
        parts: list[dict[str, Any]] | None = None,
    ) -> ChatMessage:
        current_max = (
            self.db_session.query(func.max(ChatMessage.sequence))
            .filter(ChatMessage.session_id == session_id, ChatMessage.user_id == user_id)
            .scalar()
        )
        message = ChatMessage(
            session_id=session_id,
            user_id=user_id,
            sequence=(current_max or 0) + 1,
            role=role,
            content=content,
            tool_calls_json=_dump_tool_calls(tool_calls),
            parts_json=_dump_json_list(parts),
        )
        self.db_session.add(message)
        self.touch_session(session_id=session_id, user_id=user_id)
        self.db_session.commit()
        self.db_session.refresh(message)
        return message

    def touch_session(self, *, session_id: str, user_id: int) -> None:
        session = self.get_session(session_id=session_id, user_id=user_id)
        if session:
            session.updated_at = datetime.now(timezone.utc)


def parse_tool_calls(value: str | None) -> list[dict[str, Any]]:
    return _parse_json_list(value)


def parse_message_parts(value: str | None) -> list[dict[str, Any]]:
    return _parse_json_list(value)


def _parse_json_list(value: str | None) -> list[dict[str, Any]]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _dump_tool_calls(tool_calls: list[dict[str, Any]] | None) -> str | None:
    return _dump_json_list(tool_calls)


def _dump_json_list(items: list[dict[str, Any]] | None) -> str | None:
    if not items:
        return None
    return json.dumps(items, ensure_ascii=False)



def _generate_session_id() -> str:
    return "".join(secrets.choice(SESSION_ID_ALPHABET) for _ in range(SESSION_ID_LENGTH))
