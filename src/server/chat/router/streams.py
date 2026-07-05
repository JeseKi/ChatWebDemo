# -*- coding: utf-8 -*-
"""Chat streaming and message version routes."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Query, Security, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from src.server.auth.dependencies import get_current_user
from src.server.auth.models import User
from src.server.auth.service.scopes import SCOPE_CHAT_LLM_INVOKE
from src.server.dao.dao_base import run_in_thread
from src.server.database import get_db

from .. import service
from ..dao import ChatDAO
from ..schemas import ChatRegenerateRequest, ChatSessionDetailOut, ChatStreamRequest
from .base import router

STREAM_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@router.post("/messages/{message_id}/edit-stream", summary="编辑用户消息并重新生成")
async def edit_message_stream(
    message_id: int,
    payload: ChatStreamRequest,
    db: Session = Depends(get_db),
    current_user: User = Security(get_current_user, scopes=[SCOPE_CHAT_LLM_INVOKE]),
):
    return StreamingResponse(
        service.stream_edit_message(
            db,
            current_user=current_user,
            message_id=message_id,
            message=payload.message,
            model_id=payload.model,
            thinking_effort=payload.variant,
            images=payload.images,
        ),
        media_type="text/event-stream",
        headers=STREAM_HEADERS,
    )


@router.post("/sessions/{session_id}/regenerate-stream", summary="重新生成最新回复")
async def regenerate_stream(
    session_id: str,
    payload: ChatRegenerateRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Security(get_current_user, scopes=[SCOPE_CHAT_LLM_INVOKE]),
):
    return StreamingResponse(
        service.stream_regenerate(
            db,
            current_user=current_user,
            session_id=session_id,
            model_id=payload.model if payload else None,
            thinking_effort=payload.variant if payload else None,
        ),
        media_type="text/event-stream",
        headers=STREAM_HEADERS,
    )


@router.post(
    "/messages/{message_id}/versions/{target_message_id}/activate",
    response_model=ChatSessionDetailOut,
    summary="切换消息版本",
)
async def activate_message_version(
    message_id: int,
    target_message_id: int,
    db: Session = Depends(get_db),
    current_user: User = Security(get_current_user, scopes=[SCOPE_CHAT_LLM_INVOKE]),
):
    def _activate():
        return service.activate_message_version(
            db,
            current_user=current_user,
            message_id=message_id,
            target_message_id=target_message_id,
        )

    return await run_in_thread(_activate)


@router.get("/runs/{run_id}/stream", summary="恢复订阅聊天任务事件")
async def stream_run(
    run_id: str,
    after: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Security(get_current_user, scopes=[SCOPE_CHAT_LLM_INVOKE]),
):
    return StreamingResponse(
        service.stream_run_events(
            db,
            run_id=run_id,
            user_id=current_user.id,
            after=after,
        ),
        media_type="text/event-stream",
        headers=STREAM_HEADERS,
    )


@router.post("/stream", summary="流式发送聊天消息")
async def stream_message(
    payload: ChatStreamRequest,
    db: Session = Depends(get_db),
    current_user: User = Security(get_current_user, scopes=[SCOPE_CHAT_LLM_INVOKE]),
):
    if payload.session_id and not ChatDAO(db).get_session(
        session_id=payload.session_id,
        user_id=current_user.id,
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="聊天会话不存在")

    return StreamingResponse(
        service.stream_chat(
            db,
            current_user=current_user,
            message=payload.message,
            session_id=payload.session_id,
            model_id=payload.model,
            thinking_effort=payload.variant,
            images=payload.images,
        ),
        media_type="text/event-stream",
        headers=STREAM_HEADERS,
    )
