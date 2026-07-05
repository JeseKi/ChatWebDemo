# -*- coding: utf-8 -*-
"""Streaming chat service operations."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.server.auth.models import User

from ..dao import ChatDAO
from ..schemas import ChatImageReference
from .events import sse_event
from .images import append_image_markers, escape_image_markers, extract_image_urls
from .serializers import serialize_message, serialize_session
from .runs import build_session_factory, manager, stream_run_events
from .sessions import resolve_or_create_session
from .streaming_support import (
    resolve_model,
    resolve_request_images,
    stream_assistant_for_user,
)


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

    session = resolve_or_create_session(
        dao,
        current_user=current_user,
        session_id=session_id,
        first_message=prompt,
    )
    content = append_image_markers(prompt, request_images)
    user_message = dao.append_message(
        session_id=session.id,
        user_id=current_user.id,
        role="user",
        content=content,
        model_id=model_config.id,
        thinking_effort=normalized_effort,
        parent_message_id=session.active_leaf_message_id,
    )
    assistant_message = dao.append_message(
        session_id=session.id,
        user_id=current_user.id,
        role="assistant",
        content="",
        model_id=model_config.id,
        thinking_effort=normalized_effort,
        parent_message_id=user_message.id,
    )
    run = dao.create_run(
        session_id=session.id,
        user_id=current_user.id,
        user_message_id=user_message.id,
        assistant_message_id=assistant_message.id,
        model_id=model_config.id,
        thinking_effort=normalized_effort,
    )
    session = dao.get_session(session_id=session.id, user_id=current_user.id) or session
    dao.append_run_event(
        run_id=run.id,
        session_id=session.id,
        user_id=current_user.id,
        event_type="session_ready",
        data={"session": serialize_session(session), "run": {"id": run.id}},
    )
    dao.append_run_event(
        run_id=run.id,
        session_id=session.id,
        user_id=current_user.id,
        event_type="user_message",
        data={"message": serialize_message(user_message, dao)},
    )

    manager.start(run.id, build_session_factory(db))
    async for event in stream_run_events(
        db,
        run_id=run.id,
        user_id=current_user.id,
    ):
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

    source_message_id = original.source_message_id or original.id
    content = escape_image_markers(prompt)
    user_message = dao.append_message(
        session_id=session.id,
        user_id=current_user.id,
        role="user",
        content=content,
        model_id=model_config.id,
        thinking_effort=normalized_effort,
        parent_message_id=original.parent_message_id,
        source_message_id=source_message_id,
        version_index=dao.next_version_index(source_message_id=source_message_id),
    )
    yield sse_event("session_ready", {"session": serialize_session(session)})
    yield sse_event(
        "branch_reset",
        {"parent_message_id": original.parent_message_id, "message_id": original.id},
    )
    yield sse_event("user_message", {"message": serialize_message(user_message, dao)})
    async for event in stream_assistant_for_user(
        dao,
        current_user=current_user,
        session=session,
        user_message=user_message,
        model_config=model_config,
        thinking_effort=normalized_effort,
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

    previous_leaf_message_id = session.active_leaf_message_id
    session = (
        dao.set_active_leaf(
            session_id=session.id,
            user_id=current_user.id,
            message_id=user_message.id,
        )
        or session
    )
    yield sse_event("session_ready", {"session": serialize_session(session)})
    yield sse_event("branch_reset", {"parent_message_id": user_message.id})
    async for event in stream_assistant_for_user(
        dao,
        current_user=current_user,
        session=session,
        user_message=user_message,
        regenerate_source_message_id=previous_leaf_message_id,
        model_config=model_config,
        thinking_effort=normalized_effort,
    ):
        yield event
