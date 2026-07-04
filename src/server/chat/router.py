# -*- coding: utf-8 -*-
"""ChatWeb API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from src.server.auth.dependencies import get_current_user
from src.server.auth.models import User
from src.server.auth.service.scopes import SCOPE_PROFILE_READ
from src.server.dao.dao_base import run_in_thread
from src.server.database import get_db

from . import service
from .dao import ChatDAO
from .schemas import ChatSessionDetailOut, ChatSessionOut, ChatStreamRequest

router = APIRouter(prefix="/api/chat", tags=["ChatWeb"])


@router.get("/sessions", response_model=list[ChatSessionOut], summary="列出聊天会话")
async def list_sessions(
    db: Session = Depends(get_db),
    current_user: User = Security(get_current_user, scopes=[SCOPE_PROFILE_READ]),
):
    def _list():
        return ChatDAO(db).list_sessions(user_id=current_user.id)

    return await run_in_thread(_list)


@router.get(
    "/sessions/{session_id}",
    response_model=ChatSessionDetailOut,
    summary="获取聊天会话详情",
)
async def get_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Security(get_current_user, scopes=[SCOPE_PROFILE_READ]),
):
    def _get():
        return service.get_session_detail(db, session_id=session_id, current_user=current_user)

    return await run_in_thread(_get)


@router.post("/stream", summary="流式发送聊天消息")
async def stream_message(
    payload: ChatStreamRequest,
    db: Session = Depends(get_db),
    current_user: User = Security(get_current_user, scopes=[SCOPE_PROFILE_READ]),
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
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
