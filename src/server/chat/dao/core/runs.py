# -*- coding: utf-8 -*-
"""Chat run and run event DAO operations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func

from src.server.dao.dao_base import BaseDAO
from src.server.chat.models import ChatRun, ChatRunEvent
from .json_utils import dump_json_object, generate_chat_id


class ChatRunDAO(BaseDAO):
    def create_run(
        self,
        *,
        session_id: str,
        user_id: int,
        user_message_id: int,
        assistant_message_id: int,
        model_id: str | None,
        thinking_effort: str | None,
        commit: bool = True,
    ) -> ChatRun:
        run = ChatRun(
            id=generate_chat_id(),
            session_id=session_id,
            user_id=user_id,
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
            status="queued",
            model_id=model_id,
            thinking_effort=thinking_effort,
        )
        self.db_session.add(run)
        self.db_session.flush()
        if commit:
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
        commit: bool = True,
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
        self.db_session.flush()
        if commit:
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
        commit: bool = True,
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
            data_json=dump_json_object(data),
        )
        self.db_session.add(event)
        self.db_session.flush()
        if commit:
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
