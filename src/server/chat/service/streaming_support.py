# -*- coding: utf-8 -*-
"""Internal helpers for ChatWeb streaming services."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from src.server.auth.models import User

from ..schemas import ChatImageReference
from .images import (
    MAX_IMAGES_PER_MESSAGE,
    get_user_image,
)
from .model_catalog import ModelConfig, get_model, normalize_thinking_effort


def resolve_model(
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


def resolve_request_images(
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
