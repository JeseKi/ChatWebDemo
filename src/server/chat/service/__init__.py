# -*- coding: utf-8 -*-
"""ChatWeb service layer."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.orm import Session

from src.server.auth.models import User

from ..dao import ChatDAO
from ..models import ChatMessage, ChatSession
from .agent import build_agent_input, build_chat_agent, stream_agent_events
from .constants import DEFAULT_MODEL_ID, MAX_HISTORY_MESSAGES
from .events import (
    append_output_part,
    append_reasoning_part,
    is_content_event,
    is_event,
    is_reasoning_event,
    normalize_event_name,
    sse_event,
    tool_call_from_event,
    merge_completed_tool_call,
    merge_completed_tool_part,
)
from .serializers import (
    build_fallback_parts,
    build_version_info,
    serialize_message,
    serialize_session,
)
from .sessions import activate_message_version, get_session_detail, resolve_or_create_session
from .share import create_session_share, get_shared_session

__all__ = [
    "DEFAULT_MODEL_ID",
    "MAX_HISTORY_MESSAGES",
    "activate_message_version",
    "append_output_part",
    "append_reasoning_part",
    "build_agent_input",
    "build_chat_agent",
    "build_fallback_parts",
    "build_version_info",
    "create_session_share",
    "get_shared_session",
    "get_session_detail",
    "is_content_event",
    "is_event",
    "is_reasoning_event",
    "normalize_event_name",
    "serialize_message",
    "serialize_session",
    "sse_event",
    "stream_agent_events",
    "stream_chat",
    "stream_edit_message",
    "stream_regenerate",
]


async def stream_chat(
    db: Session,
    *,
    current_user: User,
    message: str,
    session_id: str | None,
) -> AsyncIterator[str]:
    dao = ChatDAO(db)
    prompt = message.strip()
    if not prompt:
        yield sse_event("error", {"message": "消息不能为空"})
        return

    session = resolve_or_create_session(
        dao,
        current_user=current_user,
        session_id=session_id,
        first_message=prompt,
    )
    user_message = dao.append_message(
        session_id=session.id,
        user_id=current_user.id,
        role="user",
        content=prompt,
        parent_message_id=session.active_leaf_message_id,
    )

    yield sse_event("session_ready", {"session": serialize_session(session)})
    yield sse_event("user_message", {"message": serialize_message(user_message, dao)})
    async for event in _stream_assistant_for_user(
        dao,
        current_user=current_user,
        session=session,
        user_message=user_message,
    ):
        yield event


async def stream_edit_message(
    db: Session,
    *,
    current_user: User,
    message_id: int,
    message: str,
) -> AsyncIterator[str]:
    dao = ChatDAO(db)
    prompt = message.strip()
    if not prompt:
        yield sse_event("error", {"message": "消息不能为空"})
        return

    result = dao.get_session_by_message_id(message_id=message_id, user_id=current_user.id)
    if not result:
        yield sse_event("error", {"message": "消息不存在"})
        return
    session, original = result
    if original.role != "user":
        yield sse_event("error", {"message": "只能编辑用户消息"})
        return

    source_message_id = original.source_message_id or original.id
    user_message = dao.append_message(
        session_id=session.id,
        user_id=current_user.id,
        role="user",
        content=prompt,
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
    async for event in _stream_assistant_for_user(
        dao,
        current_user=current_user,
        session=session,
        user_message=user_message,
    ):
        yield event


async def stream_regenerate(
    db: Session,
    *,
    current_user: User,
    session_id: str,
) -> AsyncIterator[str]:
    dao = ChatDAO(db)
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
    async for event in _stream_assistant_for_user(
        dao,
        current_user=current_user,
        session=session,
        user_message=user_message,
        regenerate_source_message_id=previous_leaf_message_id,
    ):
        yield event


async def _stream_assistant_for_user(
    dao: ChatDAO,
    *,
    current_user: User,
    session: ChatSession,
    user_message: ChatMessage,
    regenerate_source_message_id: int | None = None,
) -> AsyncIterator[str]:
    history = dao.list_active_path(session=session)
    agent_input = build_agent_input(history)
    content_chunks: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    parts: list[dict[str, Any]] = []

    try:
        async for run_event in stream_agent_events(
            agent_input,
            user_id=str(current_user.id),
        ):
            event_name = normalize_event_name(getattr(run_event, "event", ""))
            if is_event(event_name, "tool_call_started"):
                tool_call = tool_call_from_event(
                    run_event,
                    status_value="running",
                    fallback_id=f"tool-{len(tool_calls) + 1}",
                )
                tool_calls.append(tool_call)
                parts.append({"id": tool_call["id"], "type": "tool", "tool_call": tool_call})
                yield sse_event("tool_call_started", {"tool_call": tool_call})
                continue

            if is_event(event_name, "tool_call_completed"):
                completed = tool_call_from_event(
                    run_event,
                    status_value="completed",
                    fallback_id=f"tool-{len(tool_calls) + 1}",
                )
                merge_completed_tool_call(tool_calls, completed)
                merge_completed_tool_part(parts, completed)
                yield sse_event("tool_call_completed", {"tool_call": completed})
                continue

            content = getattr(run_event, "content", None)
            if content and is_content_event(event_name):
                text = str(content)
                content_chunks.append(text)
                part_id = append_output_part(parts, text)
                yield sse_event("content_delta", {"part_id": part_id, "delta": text})
                continue

            reasoning_content = getattr(run_event, "reasoning_content", None)
            if reasoning_content and is_reasoning_event(event_name):
                text = str(reasoning_content)
                part_id = append_reasoning_part(parts, text)
                yield sse_event("reasoning_delta", {"part_id": part_id, "delta": text})
    except Exception as exc:
        yield sse_event("error", {"message": f"Agent 请求失败: {exc}"})
        return

    assistant_content = "".join(content_chunks).strip()
    if not assistant_content:
        assistant_content = "模型没有返回内容。"

    assistant_message = dao.append_message(
        session_id=session.id,
        user_id=current_user.id,
        role="assistant",
        content=assistant_content,
        parent_message_id=user_message.id,
        source_message_id=regenerate_source_message_id,
        version_index=(
            dao.next_version_index(source_message_id=regenerate_source_message_id)
            if regenerate_source_message_id is not None
            else 1
        ),
        tool_calls=tool_calls,
        parts=parts,
    )
    yield sse_event(
        "done",
        {
            "message": serialize_message(assistant_message, dao),
            "session": serialize_session(session),
        },
    )
