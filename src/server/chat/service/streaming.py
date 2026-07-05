# -*- coding: utf-8 -*-
"""Streaming chat service operations."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.server.auth.models import User

from ..dao import ChatDAO
from ..models import ChatMessage, ChatRun, ChatSession
from ..schemas import ChatImageReference
from .events import sse_event
from .images import append_image_markers, escape_image_markers, extract_image_urls
from .serializers import serialize_message, serialize_session
from .runs import build_session_factory, manager, stream_run_events
from .sessions import resolve_or_create_session
from .streaming_support import (
    resolve_model,
    resolve_request_images,
)


@dataclass(frozen=True)
class ChatRunIntent:
    session: ChatSession
    user_message: ChatMessage
    assistant_message: ChatMessage
    initial_events: list[tuple[str, dict[str, Any]]]


async def stream_chat(
    db: Session,
    *,
    current_user: User,
    message: str,
    session_id: str | None,
    model_id: str | None = None,
    thinking_effort: str | None = None,
    images: list[ChatImageReference] | None = None,
) -> AsyncIterator[str]:
    dao = ChatDAO(db)
    prompt = message.strip()
    try:
        request_images = resolve_request_images(current_user=current_user, images=images or [])
    except HTTPException as exc:
        yield sse_event("error", {"message": str(exc.detail)})
        return
    if not prompt and not request_images:
        yield sse_event("error", {"message": "消息不能为空"})
        return
    model_config, normalized_effort, error = resolve_model(model_id, thinking_effort)
    if error:
        yield sse_event("error", {"message": error})
        return
    assert model_config is not None
    if request_images and not model_config.visual:
        yield sse_event("error", {"message": "当前模型不支持图片"})
        return

    async for event in _prepare_start_and_stream_run(
        db,
        dao=dao,
        current_user=current_user,
        prepare=lambda: _prepare_new_message_run(
            dao,
            current_user=current_user,
            session_id=session_id,
            prompt=prompt,
            request_images=request_images,
            model_id=model_config.id,
            thinking_effort=normalized_effort,
        ),
    ):
        yield event


def _prepare_new_message_run(
    dao: ChatDAO,
    *,
    current_user: User,
    session_id: str | None,
    prompt: str,
    request_images: list[Any],
    model_id: str,
    thinking_effort: str | None,
) -> ChatRunIntent:
    session = resolve_or_create_session(
        dao,
        current_user=current_user,
        session_id=session_id,
        first_message=prompt,
        commit=False,
    )
    user_message = dao.append_message(
        session_id=session.id,
        user_id=current_user.id,
        role="user",
        content=append_image_markers(prompt, request_images),
        model_id=model_id,
        thinking_effort=thinking_effort,
        parent_message_id=session.active_leaf_message_id,
        commit=False,
    )
    assistant_message = _append_assistant_placeholder(
        dao,
        current_user=current_user,
        session=session,
        user_message=user_message,
        model_id=model_id,
        thinking_effort=thinking_effort,
    )
    return ChatRunIntent(
        session=session,
        user_message=user_message,
        assistant_message=assistant_message,
        initial_events=[
            ("user_message", {"message": serialize_message(user_message, dao)}),
        ],
    )


def _prepare_edit_message_run(
    dao: ChatDAO,
    *,
    current_user: User,
    session: ChatSession,
    original: ChatMessage,
    prompt: str,
    model_id: str,
    thinking_effort: str | None,
) -> ChatRunIntent:
    source_message_id = original.source_message_id or original.id
    user_message = dao.append_message(
        session_id=session.id,
        user_id=current_user.id,
        role="user",
        content=escape_image_markers(prompt),
        model_id=model_id,
        thinking_effort=thinking_effort,
        parent_message_id=original.parent_message_id,
        source_message_id=source_message_id,
        version_index=dao.next_version_index(source_message_id=source_message_id),
        commit=False,
    )
    assistant_message = _append_assistant_placeholder(
        dao,
        current_user=current_user,
        session=session,
        user_message=user_message,
        model_id=model_id,
        thinking_effort=thinking_effort,
    )
    return ChatRunIntent(
        session=session,
        user_message=user_message,
        assistant_message=assistant_message,
        initial_events=[
            (
                "branch_reset",
                {"parent_message_id": original.parent_message_id, "message_id": original.id},
            ),
            ("user_message", {"message": serialize_message(user_message, dao)}),
        ],
    )


def _prepare_regenerate_run(
    dao: ChatDAO,
    *,
    current_user: User,
    session: ChatSession,
    user_message: ChatMessage,
    model_id: str,
    thinking_effort: str | None,
) -> ChatRunIntent:
    source_message_id = _regenerate_source_message_id(
        dao,
        current_user=current_user,
        session=session,
        user_message=user_message,
    )
    assistant_message = _append_assistant_placeholder(
        dao,
        current_user=current_user,
        session=session,
        user_message=user_message,
        model_id=model_id,
        thinking_effort=thinking_effort,
        source_message_id=source_message_id,
        version_index=(
            dao.next_version_index(source_message_id=source_message_id)
            if source_message_id is not None
            else 1
        ),
    )
    return ChatRunIntent(
        session=session,
        user_message=user_message,
        assistant_message=assistant_message,
        initial_events=[
            ("branch_reset", {"parent_message_id": user_message.id}),
        ],
    )


def _append_assistant_placeholder(
    dao: ChatDAO,
    *,
    current_user: User,
    session: ChatSession,
    user_message: ChatMessage,
    model_id: str,
    thinking_effort: str | None,
    source_message_id: int | None = None,
    version_index: int = 1,
) -> ChatMessage:
    return dao.append_message(
        session_id=session.id,
        user_id=current_user.id,
        role="assistant",
        content="",
        model_id=model_id,
        thinking_effort=thinking_effort,
        parent_message_id=user_message.id,
        source_message_id=source_message_id,
        version_index=version_index,
        commit=False,
    )


def _regenerate_source_message_id(
    dao: ChatDAO,
    *,
    current_user: User,
    session: ChatSession,
    user_message: ChatMessage,
) -> int | None:
    source_message_id = session.active_leaf_message_id
    if source_message_id is None:
        return None

    source_message = dao.get_message(message_id=source_message_id, user_id=current_user.id)
    if (
        source_message is None
        or source_message.role != "assistant"
        or source_message.parent_message_id != user_message.id
    ):
        return None
    return source_message.source_message_id or source_message.id


def _create_run_for_intent(
    dao: ChatDAO,
    *,
    current_user: User,
    intent: ChatRunIntent,
) -> ChatRun:
    run = dao.create_run(
        session_id=intent.session.id,
        user_id=current_user.id,
        user_message_id=intent.user_message.id,
        assistant_message_id=intent.assistant_message.id,
        model_id=intent.assistant_message.model_id,
        thinking_effort=intent.assistant_message.thinking_effort,
        commit=False,
    )
    session = (
        dao.get_session(session_id=intent.session.id, user_id=current_user.id)
        or intent.session
    )
    dao.append_run_event(
        run_id=run.id,
        session_id=session.id,
        user_id=current_user.id,
        event_type="session_ready",
        data={"session": serialize_session(session), "run": {"id": run.id}},
        commit=False,
    )
    for event_type, data in intent.initial_events:
        dao.append_run_event(
            run_id=run.id,
            session_id=session.id,
            user_id=current_user.id,
            event_type=event_type,
            data=data,
            commit=False,
        )
    return run


async def _prepare_start_and_stream_run(
    db: Session,
    *,
    dao: ChatDAO,
    current_user: User,
    prepare: Callable[[], ChatRunIntent],
) -> AsyncIterator[str]:
    try:
        intent = prepare()
        run = _create_run_for_intent(dao, current_user=current_user, intent=intent)
        run_id = run.id
        db.commit()
    except Exception:
        db.rollback()
        raise

    manager.start(run_id, build_session_factory(db))
    async for event in stream_run_events(db, run_id=run_id, user_id=current_user.id):
        yield event


async def stream_edit_message(
    db: Session,
    *,
    current_user: User,
    message_id: int,
    message: str,
    model_id: str | None = None,
    thinking_effort: str | None = None,
    images: list[ChatImageReference] | None = None,
) -> AsyncIterator[str]:
    dao = ChatDAO(db)
    prompt = message.strip()
    if images:
        yield sse_event("error", {"message": "编辑消息暂不支持图片"})
        return
    if not prompt:
        yield sse_event("error", {"message": "消息不能为空"})
        return
    model_config, normalized_effort, error = resolve_model(model_id, thinking_effort)
    if error:
        yield sse_event("error", {"message": error})
        return
    assert model_config is not None

    result = dao.get_session_by_message_id(message_id=message_id, user_id=current_user.id)
    if not result:
        yield sse_event("error", {"message": "消息不存在"})
        return
    session, original = result
    if original.role != "user":
        yield sse_event("error", {"message": "只能编辑用户消息"})
        return
    if extract_image_urls(original.content):
        yield sse_event("error", {"message": "含图片的消息暂不支持编辑"})
        return

    async for event in _prepare_start_and_stream_run(
        db,
        dao=dao,
        current_user=current_user,
        prepare=lambda: _prepare_edit_message_run(
            dao,
            current_user=current_user,
            session=session,
            original=original,
            prompt=prompt,
            model_id=model_config.id,
            thinking_effort=normalized_effort,
        ),
    ):
        yield event


async def stream_regenerate(
    db: Session,
    *,
    current_user: User,
    session_id: str,
    model_id: str | None = None,
    thinking_effort: str | None = None,
) -> AsyncIterator[str]:
    dao = ChatDAO(db)
    model_config, normalized_effort, error = resolve_model(model_id, thinking_effort)
    if error:
        yield sse_event("error", {"message": error})
        return
    assert model_config is not None

    session = dao.get_session(session_id=session_id, user_id=current_user.id)
    if not session:
        yield sse_event("error", {"message": "聊天会话不存在"})
        return

    user_message = dao.get_latest_user_message(session=session)
    if not user_message:
        yield sse_event("error", {"message": "没有可重新生成的用户消息"})
        return

    async for event in _prepare_start_and_stream_run(
        db,
        dao=dao,
        current_user=current_user,
        prepare=lambda: _prepare_regenerate_run(
            dao,
            current_user=current_user,
            session=session,
            user_message=user_message,
            model_id=model_config.id,
            thinking_effort=normalized_effort,
        ),
    ):
        yield event
