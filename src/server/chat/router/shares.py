# -*- coding: utf-8 -*-
"""Chat share routes."""

from __future__ import annotations

from fastapi import Depends, Security
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from src.server.auth.dependencies import get_current_user
from src.server.auth.models import User
from src.server.auth.service.scopes import SCOPE_CHAT_LLM_INVOKE
from src.server.dao.dao_base import run_in_thread
from src.server.database import get_db

from .. import service
from ..schemas import ChatSessionShareOut, SharedChatSessionOut
from .base import router


@router.get(
    "/shares/{token}",
    response_model=SharedChatSessionOut,
    summary="预览分享的聊天会话快照",
)
async def get_shared_session(
    token: str,
    db: Session = Depends(get_db),
):
    def _get():
        return service.get_shared_session(db, token=token)

    return await run_in_thread(_get)


@router.get("/shares/{token}/images/{image_id}", summary="读取分享中的聊天图片")
async def get_shared_image(
    token: str,
    image_id: str,
    db: Session = Depends(get_db),
):
    def _get():
        return service.get_shared_image(db, token=token, image_id=image_id)

    stored = await run_in_thread(_get)
    return FileResponse(stored.path, media_type=stored.mime_type)


@router.post(
    "/sessions/{session_id}/shares",
    response_model=ChatSessionShareOut,
    summary="创建聊天会话分享快照",
)
async def create_session_share(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Security(get_current_user, scopes=[SCOPE_CHAT_LLM_INVOKE]),
):
    def _create():
        return service.create_session_share(
            db,
            current_user=current_user,
            session_id=session_id,
        )

    return await run_in_thread(_create)
