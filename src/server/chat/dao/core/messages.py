# -*- coding: utf-8 -*-
"""Chat message tree and version DAO operations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.server.dao.dao_base import BaseDAO
from src.server.chat.models import ChatMessage, ChatSession
from .json_utils import dump_json_list, dump_tool_calls


class _MessageSessionLookup(Protocol):
    db_session: Session

    def get_session(self, *, session_id: str, user_id: int) -> ChatSession | None:
        ...

    def get_message(self, *, message_id: int, user_id: int) -> ChatMessage | None:
        ...


class _MessageTreeContext(_MessageSessionLookup, Protocol):
    def latest_leaf_from_message(self, message: ChatMessage) -> ChatMessage:
        ...

    def set_active_leaf(
        self,
        *,
        session_id: str,
        user_id: int,
        message_id: int | None,
        commit: bool = True,
    ) -> ChatSession | None:
        ...


class ChatMessageDAO(BaseDAO):
    def list_messages(self, *, session_id: str, user_id: int) -> list[ChatMessage]:
        return (
            self.db_session.query(ChatMessage)
            .filter(
                ChatMessage.session_id == session_id,
                ChatMessage.user_id == user_id,
                ChatMessage.deleted_at.is_(None),
            )
            .order_by(ChatMessage.sequence.asc(), ChatMessage.id.asc())
            .all()
        )

    def list_active_path(self, *, session: ChatSession) -> list[ChatMessage]:
        if session.active_leaf_message_id is None:
            return []
        message = self.get_message(
            message_id=session.active_leaf_message_id,
            user_id=session.user_id,
        )
        if message is None:
            return []
        return self.list_path_to_message(message=message)

    def list_path_to_message(self, *, message: ChatMessage) -> list[ChatMessage]:
        messages = self.list_messages(session_id=message.session_id, user_id=message.user_id)
        by_id = {item.id: item for item in messages}
        path: list[ChatMessage] = []
        current = by_id.get(message.id)
        while current is not None:
            path.append(current)
            current = (
                by_id.get(current.parent_message_id)
                if current.parent_message_id is not None
                else None
            )
        return list(reversed(path))

    def get_message(self, *, message_id: int, user_id: int) -> ChatMessage | None:
        return (
            self.db_session.query(ChatMessage)
            .filter(
                ChatMessage.id == message_id,
                ChatMessage.user_id == user_id,
                ChatMessage.deleted_at.is_(None),
            )
            .first()
        )

    def get_latest_user_message(self, *, session: ChatSession) -> ChatMessage | None:
        for message in reversed(self.list_active_path(session=session)):
            if message.role == "user":
                return message
        return None

    def list_versions_for_message(self, message: ChatMessage) -> list[ChatMessage]:
        source_message_id = message.source_message_id or message.id
        return (
            self.db_session.query(ChatMessage)
            .filter(
                ChatMessage.session_id == message.session_id,
                ChatMessage.user_id == message.user_id,
                ChatMessage.role == message.role,
                ChatMessage.deleted_at.is_(None),
                (
                    (ChatMessage.id == source_message_id)
                    | (ChatMessage.source_message_id == source_message_id)
                ),
            )
            .order_by(ChatMessage.version_index.asc(), ChatMessage.id.asc())
            .all()
        )

    def latest_leaf_from_message(self, message: ChatMessage) -> ChatMessage:
        messages = self.list_messages(session_id=message.session_id, user_id=message.user_id)
        children_by_parent: dict[int, list[ChatMessage]] = {}
        for item in messages:
            if item.parent_message_id is None:
                continue
            children_by_parent.setdefault(item.parent_message_id, []).append(item)

        current = message
        while True:
            children = children_by_parent.get(current.id, [])
            if not children:
                return current
            current = sorted(children, key=lambda item: (item.sequence, item.id))[-1]

    def activate_message_version(
        self: _MessageTreeContext,
        *,
        message_id: int,
        target_message_id: int,
        user_id: int,
        commit: bool = True,
    ) -> ChatSession | None:
        current_message = self.get_message(message_id=message_id, user_id=user_id)
        target_message = self.get_message(message_id=target_message_id, user_id=user_id)
        if not current_message or not target_message:
            return None
        if current_message.session_id != target_message.session_id:
            return None
        current_source_id = current_message.source_message_id or current_message.id
        target_source_id = target_message.source_message_id or target_message.id
        if current_source_id != target_source_id:
            return None

        leaf = self.latest_leaf_from_message(target_message)
        return self.set_active_leaf(
            session_id=target_message.session_id,
            user_id=user_id,
            message_id=leaf.id,
            commit=commit,
        )

    def next_version_index(self, *, source_message_id: int) -> int:
        count = (
            self.db_session.query(func.count(ChatMessage.id))
            .filter(ChatMessage.source_message_id == source_message_id)
            .scalar()
        )
        return int(count or 0) + 2

    def append_message(
        self: _MessageTreeContext,
        *,
        session_id: str,
        user_id: int,
        role: str,
        content: str,
        model_id: str | None = None,
        thinking_effort: str | None = None,
        parent_message_id: int | None = None,
        source_message_id: int | None = None,
        version_index: int = 1,
        tool_calls: list[dict[str, Any]] | None = None,
        parts: list[dict[str, Any]] | None = None,
        make_active_leaf: bool = True,
        commit: bool = True,
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
            parent_message_id=parent_message_id,
            source_message_id=source_message_id,
            version_index=version_index,
            role=role,
            content=content,
            model_id=model_id,
            thinking_effort=thinking_effort,
            tool_calls_json=dump_tool_calls(tool_calls),
            parts_json=dump_json_list(parts),
        )
        self.db_session.add(message)
        session = self.get_session(session_id=session_id, user_id=user_id)
        if session:
            session.updated_at = datetime.now(timezone.utc)
        self.db_session.flush()
        if make_active_leaf:
            self.set_active_leaf(
                session_id=session_id,
                user_id=user_id,
                message_id=message.id,
                commit=False,
            )
        if commit:
            self.db_session.commit()
            self.db_session.refresh(message)
        return message

    def update_message_payload(
        self: _MessageSessionLookup,
        *,
        message_id: int,
        user_id: int,
        content: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        parts: list[dict[str, Any]] | None = None,
        commit: bool = True,
    ) -> ChatMessage | None:
        message = self.get_message(message_id=message_id, user_id=user_id)
        if not message:
            return None
        if content is not None:
            message.content = content
        if tool_calls is not None:
            message.tool_calls_json = dump_tool_calls(tool_calls)
        if parts is not None:
            message.parts_json = dump_json_list(parts)
        session = self.get_session(session_id=message.session_id, user_id=user_id)
        if session:
            session.updated_at = datetime.now(timezone.utc)
        self.db_session.flush()
        if commit:
            self.db_session.commit()
            self.db_session.refresh(message)
        return message

    def set_active_leaf(
        self: _MessageSessionLookup,
        *,
        session_id: str,
        user_id: int,
        message_id: int | None,
        commit: bool = True,
    ) -> ChatSession | None:
        session = self.get_session(session_id=session_id, user_id=user_id)
        if not session:
            return None
        session.active_leaf_message_id = message_id
        session.updated_at = datetime.now(timezone.utc)
        self.db_session.flush()
        if commit:
            self.db_session.commit()
            self.db_session.refresh(session)
        return session
