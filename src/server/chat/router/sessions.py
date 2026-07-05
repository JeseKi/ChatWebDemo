# -*- coding: utf-8 -*-
"""Chat session routes."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Security, status
from sqlalchemy.orm import Session

from src.server.auth.dependencies import get_current_user
from src.server.auth.models import User
from src.server.auth.service.scopes import SCOPE_CHAT_LLM_INVOKE
from src.server.dao.dao_base import run_in_thread
from src.server.database import get_db

from .. import service
from ..dao import ChatDAO
from ..schemas import ChatSessionDetailOut, ChatSessionOut, ChatSessionUpdate
from .base import router


@router.get("/sessions", response_model=list[ChatSessionOut], summary="列出聊天会话")
async def list_sessions(
    db: Session = Depends(get_db),
    current_user: User = Security(get_current_user, scopes=[SCOPE_CHAT_LLM_INVOKE]),
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
    current_user: User = Security(get_current_user, scopes=[SCOPE_CHAT_LLM_INVOKE]),
):
    def _get():
        return service.get_session_detail(db, session_id=session_id, current_user=current_user)

    return await run_in_thread(_get)


@router.patch(
    "/sessions/{session_id}",
    response_model=ChatSessionOut,
    summary="更新聊天会话名称",
)
async def update_session(
    session_id: str,
    payload: ChatSessionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Security(get_current_user, scopes=[SCOPE_CHAT_LLM_INVOKE]),
):
    def _update():
        title = payload.title.strip()
        if not title:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="会话名称不能为空",
            )
        session = ChatDAO(db).update_session_title(
            session_id=session_id,
            user_id=current_user.id,
            title=title,
        )
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="聊天会话不存在",
            )
        return session

    return await run_in_thread(_update)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除聊天会话",
)
async def delete_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Security(get_current_user, scopes=[SCOPE_CHAT_LLM_INVOKE]),
):
    def _delete():
        deleted = ChatDAO(db).delete_session(
            session_id=session_id,
            user_id=current_user.id,
        )
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="聊天会话不存在",
            )

    return await run_in_thread(_delete)
