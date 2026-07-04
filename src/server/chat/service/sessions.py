# -*- coding: utf-8 -*-
"""Session-level ChatWeb service operations."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.server.auth.models import User

from ..dao import ChatDAO
from ..models import ChatSession
from ..schemas import ChatMessageOut, ChatSessionDetailOut
from .serializers import serialize_message, serialize_session


def get_session_detail(
    db: Session, *, session_id: str, current_user: User
) -> ChatSessionDetailOut:
    dao = ChatDAO(db)
    session = dao.get_session(session_id=session_id, user_id=current_user.id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="聊天会话不存在")

    messages = [
        ChatMessageOut.model_validate(serialize_message(message, dao))
        for message in dao.list_active_path(session=session)
    ]
    return ChatSessionDetailOut.model_validate({**serialize_session(session), "messages": messages})


def activate_message_version(
    db: Session,
    *,
    current_user: User,
    message_id: int,
    target_message_id: int,
) -> ChatSessionDetailOut:
    dao = ChatDAO(db)
    session = dao.activate_message_version(
        message_id=message_id,
        target_message_id=target_message_id,
        user_id=current_user.id,
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="消息版本不存在")
    return get_session_detail(db, session_id=session.id, current_user=current_user)


def resolve_or_create_session(
    dao: ChatDAO,
    *,
    current_user: User,
    session_id: str | None,
    first_message: str,
) -> ChatSession:
    if session_id:
        session = dao.get_session(session_id=session_id, user_id=current_user.id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="聊天会话不存在",
            )
        return session

    title = first_message.replace("\n", " ").strip()[:60] or "新对话"
    return dao.create_session(user_id=current_user.id, title=title)
