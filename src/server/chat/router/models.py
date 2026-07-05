# -*- coding: utf-8 -*-
"""Chat model catalog routes."""

from __future__ import annotations

from fastapi import Security

from src.server.auth.dependencies import get_current_user
from src.server.auth.models import User
from src.server.auth.service.scopes import SCOPE_CHAT_LLM_INVOKE

from ..schemas import ChatModelOut, ChatModelsResponse
from ..service import model_catalog
from .base import router


@router.get("/models", response_model=ChatModelsResponse, summary="列出可用模型")
async def list_models(
    _: User = Security(get_current_user, scopes=[SCOPE_CHAT_LLM_INVOKE]),
):
    snapshot = model_catalog.snapshot()
    return ChatModelsResponse(
        models=[ChatModelOut.model_validate(model.model_dump()) for model in snapshot.models],
        last_error=snapshot.last_error,
    )
