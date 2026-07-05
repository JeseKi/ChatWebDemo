# -*- coding: utf-8 -*-
"""Chat image routes."""

from __future__ import annotations

from fastapi import File, HTTPException, Security, UploadFile, status
from fastapi.responses import FileResponse

from src.server.auth.dependencies import get_current_user
from src.server.auth.models import User
from src.server.auth.service.scopes import SCOPE_CHAT_LLM_INVOKE

from ..schemas import ChatImageOut
from ..service import images as image_service
from .base import router


@router.post("/images", response_model=ChatImageOut, summary="上传聊天图片")
async def upload_image(
    file: UploadFile = File(...),
    current_user: User = Security(get_current_user, scopes=[SCOPE_CHAT_LLM_INVOKE]),
):
    stored = await image_service.store_upload(current_user.id, file)
    return ChatImageOut(
        image_id=stored.image_id,
        url=stored.url,
        mime_type=stored.mime_type,
        width=stored.width,
        height=stored.height,
    )


@router.get("/images/{image_id}", summary="读取聊天图片")
async def get_image(
    image_id: str,
    current_user: User = Security(get_current_user, scopes=[SCOPE_CHAT_LLM_INVOKE]),
):
    stored = image_service.get_user_image(current_user.id, image_id)
    if stored is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="图片不存在")
    return FileResponse(stored.path, media_type=stored.mime_type)
