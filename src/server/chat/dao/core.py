# -*- coding: utf-8 -*-
"""ChatWeb conversation DAO."""

from __future__ import annotations

import json
import secrets
import string
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.server.dao.dao_base import BaseDAO

from ..models import ChatContextCompression, ChatMessage, ChatRun, ChatRunEvent, ChatSession

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
            .filter(
                ChatSession.id == session_id,
                ChatSession.user_id == user_id,
                ChatSession.deleted_at.is_(None),
            )
            .first()
        )

    def get_session_by_message_id(
        self, *, message_id: int, user_id: int
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
        self,
        *,
        message_id: int,
        target_message_id: int,
        user_id: int,
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
        )

    def next_version_index(self, *, source_message_id: int) -> int:
        count = (
            self.db_session.query(func.count(ChatMessage.id))
            .filter(ChatMessage.source_message_id == source_message_id)
            .scalar()
        )
        return int(count or 0) + 2

    def update_session_title(
        self, *, session_id: str, user_id: int, title: str
    ) -> ChatSession | None:
        session = self.get_session(session_id=session_id, user_id=user_id)
        if not session:
            return None
        session.title = title
        session.updated_at = datetime.now(timezone.utc)
        self.db_session.commit()
        self.db_session.refresh(session)
        return session

    def delete_session(self, *, session_id: str, user_id: int) -> bool:
        session = self.get_session(session_id=session_id, user_id=user_id)
        if not session:
            return False
        now = datetime.now(timezone.utc)
        session.deleted_at = now
        session.updated_at = now
        self.db_session.commit()
        return True

    def append_message(
        self,
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
            tool_calls_json=_dump_tool_calls(tool_calls),
            parts_json=_dump_json_list(parts),
        )
        self.db_session.add(message)
        session = self.get_session(session_id=session_id, user_id=user_id)
        if session:
            session.updated_at = datetime.now(timezone.utc)
        self.db_session.commit()
        self.db_session.refresh(message)
        if make_active_leaf:
            self.set_active_leaf(session_id=session_id, user_id=user_id, message_id=message.id)
        return message

    def update_message_payload(
        self,
        *,
        message_id: int,
        user_id: int,
        content: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        parts: list[dict[str, Any]] | None = None,
    ) -> ChatMessage | None:
        message = self.get_message(message_id=message_id, user_id=user_id)
        if not message:
            return None
        if content is not None:
            message.content = content
        if tool_calls is not None:
            message.tool_calls_json = _dump_tool_calls(tool_calls)
        if parts is not None:
            message.parts_json = _dump_json_list(parts)
        session = self.get_session(session_id=message.session_id, user_id=user_id)
        if session:
            session.updated_at = datetime.now(timezone.utc)
        self.db_session.commit()
        self.db_session.refresh(message)
        return message

    def create_run(
        self,
        *,
        session_id: str,
        user_id: int,
        user_message_id: int,
        assistant_message_id: int,
        model_id: str | None,
        thinking_effort: str | None,
    ) -> ChatRun:
        run = ChatRun(
            id=_generate_session_id(),
            session_id=session_id,
            user_id=user_id,
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
            status="queued",
            model_id=model_id,
            thinking_effort=thinking_effort,
        )
        self.db_session.add(run)
        self.db_session.commit()
        self.db_session.refresh(run)
        return run

    def get_run(self, *, run_id: str, user_id: int) -> ChatRun | None:
        return (
            self.db_session.query(ChatRun)
            .filter(ChatRun.id == run_id, ChatRun.user_id == user_id)
            .first()
        )

    def get_run_by_id(self, *, run_id: str) -> ChatRun | None:
        return self.db_session.query(ChatRun).filter(ChatRun.id == run_id).first()

    def get_active_run_for_session(
        self, *, session_id: str, user_id: int
    ) -> ChatRun | None:
        return (
            self.db_session.query(ChatRun)
            .filter(
                ChatRun.session_id == session_id,
                ChatRun.user_id == user_id,
                ChatRun.status.in_(("queued", "running")),
            )
            .order_by(ChatRun.created_at.desc())
            .first()
        )

    def update_run_status(
        self,
        *,
        run_id: str,
        status: str,
        error: str | None = None,
    ) -> ChatRun | None:
        run = self.get_run_by_id(run_id=run_id)
        if not run:
            return None
        now = datetime.now(timezone.utc)
        run.status = status
        if status == "running" and run.started_at is None:
            run.started_at = now
        if status in {"succeeded", "failed", "canceled"}:
            run.finished_at = now
        if error is not None:
            run.error = error
        self.db_session.commit()
        self.db_session.refresh(run)
        return run

    def append_run_event(
        self,
        *,
        run_id: str,
        session_id: str,
        user_id: int,
        event_type: str,
        data: dict[str, Any],
    ) -> ChatRunEvent:
        current_max = (
            self.db_session.query(func.max(ChatRunEvent.sequence))
            .filter(ChatRunEvent.run_id == run_id)
            .scalar()
        )
        event = ChatRunEvent(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            sequence=(current_max or 0) + 1,
            type=event_type,
            data_json=json.dumps(data, ensure_ascii=False, default=str),
        )
        self.db_session.add(event)
        self.db_session.commit()
        self.db_session.refresh(event)
        return event

    def list_run_events_after(
        self,
        *,
        run_id: str,
        user_id: int,
        after: int = 0,
        limit: int = 100,
    ) -> list[ChatRunEvent]:
        return (
            self.db_session.query(ChatRunEvent)
            .filter(
                ChatRunEvent.run_id == run_id,
                ChatRunEvent.user_id == user_id,
                ChatRunEvent.sequence > after,
            )
            .order_by(ChatRunEvent.sequence.asc())
            .limit(limit)
            .all()
        )

    def latest_run_event_sequence(self, *, run_id: str, user_id: int) -> int:
        value = (
            self.db_session.query(func.max(ChatRunEvent.sequence))
            .filter(ChatRunEvent.run_id == run_id, ChatRunEvent.user_id == user_id)
            .scalar()
        )
        return int(value or 0)

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

    def touch_session(self, *, session_id: str, user_id: int) -> None:
        session = self.get_session(session_id=session_id, user_id=user_id)
        if session:
            session.updated_at = datetime.now(timezone.utc)

    def set_active_leaf(
        self, *, session_id: str, user_id: int, message_id: int | None
    ) -> ChatSession | None:
        session = self.get_session(session_id=session_id, user_id=user_id)
        if not session:
            return None
        session.active_leaf_message_id = message_id
        session.updated_at = datetime.now(timezone.utc)
        self.db_session.commit()
        self.db_session.refresh(session)
        return session


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
