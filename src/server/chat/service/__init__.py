# -*- coding: utf-8 -*-
"""ChatWeb service layer."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.server.auth.models import User

from ..dao import ChatDAO
from ..models import ChatMessage, ChatSession
from .agent import (
    build_agent_input,
    build_agent_messages,
    build_chat_agent,
    reset_agent_model_context,
    set_agent_model_context,
    stream_agent_events,
)
from .constants import MAX_HISTORY_MESSAGES
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
from .share import create_session_share, get_shared_image, get_shared_session
from .images import (
    MAX_IMAGES_PER_MESSAGE,
    append_image_markers,
    content_without_image_markers,
    escape_image_markers,
    estimate_image_tokens,
    estimate_text_tokens,
    extract_image_urls,
    get_user_image,
    image_id_from_url,
)
from .model_catalog import ModelConfig, get_model, normalize_thinking_effort
from ..schemas import ChatImageReference

__all__ = [
    "MAX_HISTORY_MESSAGES",
    "activate_message_version",
    "append_output_part",
    "append_reasoning_part",
    "build_agent_input",
    "build_agent_messages",
    "build_chat_agent",
    "build_fallback_parts",
    "build_version_info",
    "create_session_share",
    "get_shared_session",
    "get_shared_image",
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
    model_id: str | None = None,
    thinking_effort: str | None = None,
    images: list[ChatImageReference] | None = None,
) -> AsyncIterator[str]:
    dao = ChatDAO(db)
    prompt = message.strip()
    try:
        request_images = _resolve_request_images(current_user=current_user, images=images or [])
    except HTTPException as exc:
        yield sse_event("error", {"message": str(exc.detail)})
        return
    if not prompt and not request_images:
        yield sse_event("error", {"message": "消息不能为空"})
        return
    model_config, normalized_effort, error = _resolve_model(model_id, thinking_effort)
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
    history_before = dao.list_active_path(session=session)
    projected_history = [
        *history_before,
        _TransientMessage(
            role="user",
            content=content,
            user_id=current_user.id,
        ),
    ]
    budget_error = _context_budget_error(projected_history, model_config)
    if budget_error:
        yield sse_event("error", {"message": budget_error})
        return
    user_message = dao.append_message(
        session_id=session.id,
        user_id=current_user.id,
        role="user",
        content=content,
        model_id=model_config.id,
        thinking_effort=normalized_effort,
        parent_message_id=session.active_leaf_message_id,
    )

    yield sse_event("session_ready", {"session": serialize_session(session)})
    yield sse_event("user_message", {"message": serialize_message(user_message, dao)})
    async for event in _stream_assistant_for_user(
        dao,
        current_user=current_user,
        session=session,
        user_message=user_message,
        model_config=model_config,
        thinking_effort=normalized_effort,
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
    model_config, normalized_effort, error = _resolve_model(model_id, thinking_effort)
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
    branch_messages = []
    for active_message in dao.list_active_path(session=session):
        if active_message.id == original.id:
            break
        branch_messages.append(active_message)
    projected_history = [
        *branch_messages,
        _TransientMessage(
            role="user",
            content=content,
            user_id=current_user.id,
        ),
    ]
    budget_error = _context_budget_error(projected_history, model_config)
    if budget_error:
        yield sse_event("error", {"message": budget_error})
        return
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
    async for event in _stream_assistant_for_user(
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
    model_config, normalized_effort, error = _resolve_model(model_id, thinking_effort)
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
    budget_error = _context_budget_error(dao.list_active_path(session=session), model_config)
    if budget_error:
        yield sse_event("error", {"message": budget_error})
        return

    yield sse_event("session_ready", {"session": serialize_session(session)})
    yield sse_event("branch_reset", {"parent_message_id": user_message.id})
    async for event in _stream_assistant_for_user(
        dao,
        current_user=current_user,
        session=session,
        user_message=user_message,
        regenerate_source_message_id=previous_leaf_message_id,
        model_config=model_config,
        thinking_effort=normalized_effort,
    ):
        yield event


async def _stream_assistant_for_user(
    dao: ChatDAO,
    *,
    current_user: User,
    session: ChatSession,
    user_message: ChatMessage,
    model_config: ModelConfig,
    thinking_effort: str | None,
    regenerate_source_message_id: int | None = None,
) -> AsyncIterator[str]:
    history = dao.list_active_path(session=session)
    agent_input = build_agent_messages(history)
    content_chunks: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    parts: list[dict[str, Any]] = []

    try:
        tokens = set_agent_model_context(model_config, thinking_effort)
        try:
            run_events = stream_agent_events(agent_input, user_id=str(current_user.id))
            async for run_event in run_events:
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
                    text = escape_image_markers(str(content))
                    content_chunks.append(text)
                    part_id = append_output_part(parts, text)
                    yield sse_event("content_delta", {"part_id": part_id, "delta": text})
                    continue

                reasoning_content = getattr(run_event, "reasoning_content", None)
                if reasoning_content and is_reasoning_event(event_name):
                    text = escape_image_markers(str(reasoning_content))
                    part_id = append_reasoning_part(parts, text)
                    yield sse_event("reasoning_delta", {"part_id": part_id, "delta": text})
        finally:
            reset_agent_model_context(tokens)
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
        model_id=model_config.id,
        thinking_effort=thinking_effort,
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


class _TransientMessage:
    def __init__(self, *, role: str, content: str, user_id: int):
        self.role = role
        self.content = content
        self.user_id = user_id


def _resolve_model(
    model_id: str | None,
    thinking_effort: str | None,
) -> tuple[ModelConfig | None, str | None, str | None]:
    model = get_model(model_id)
    if model is None:
        return None, None, "需要先配置模型才能发送消息"
    if model_id and model.id != model_id:
        return None, None, "选择的模型不存在，请重新选择"
    if thinking_effort and model.thinking and thinking_effort not in model.thinking:
        return None, None, "选择的思考模式不存在，请重新选择"
    return model, normalize_thinking_effort(model, thinking_effort), None


def _resolve_request_images(
    *,
    current_user: User,
    images: list[ChatImageReference],
) -> list[Any]:
    if len(images) > MAX_IMAGES_PER_MESSAGE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"每条消息最多上传 {MAX_IMAGES_PER_MESSAGE} 张图片",
        )
    resolved = []
    for image in images:
        stored = get_user_image(current_user.id, image.image_id)
        if stored is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="图片不存在",
            )
        resolved.append(stored)
    return resolved


def _context_budget_error(messages: list[Any], model: ModelConfig) -> str | None:
    total = 0
    has_images = False
    for message in messages[-MAX_HISTORY_MESSAGES:]:
        total += estimate_text_tokens(content_without_image_markers(message.content))
        for url in extract_image_urls(message.content):
            image_id = image_id_from_url(url)
            if not image_id:
                continue
            stored = get_user_image(message.user_id, image_id)
            if stored is None:
                continue
            has_images = True
            total += estimate_image_tokens(stored.width, stored.height)
    if has_images and not model.visual:
        return "当前会话包含图片，请选择支持视觉的模型"
    if total > model.context:
        return "当前会话上下文预计超出模型限制，请新开会话"
    return None
