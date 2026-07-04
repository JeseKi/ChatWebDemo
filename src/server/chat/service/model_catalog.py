# -*- coding: utf-8 -*-
"""Hot-reloaded chat model catalog."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Literal

from loguru import logger
from pydantic import BaseModel, Field, ValidationError, field_validator

from src.server.config import global_config

ProviderName = Literal[
    "openai_chat",
    "openai_responses",
    "deepseek",
    "anthropic",
    "google",
]

MODEL_CONFIG_PATH = Path(global_config.project_root) / "data" / "models.json"
RELOAD_INTERVAL_SECONDS = 10
IconMode = Literal["auto", "mask", "image"]


class ModelIconConfig(BaseModel):
    light: str | None = Field(default=None, max_length=4000)
    dark: str | None = Field(default=None, max_length=4000)
    mode: IconMode = "auto"


class ModelConfig(BaseModel):
    provider: ProviderName
    id: str = Field(..., min_length=1, max_length=120)
    name: str = Field(..., min_length=1, max_length=120)
    icon: str | ModelIconConfig | None = None
    context: int = Field(..., ge=1)
    max_output: int = Field(..., ge=1)
    visual: bool = False
    thinking: dict[str, str] = Field(default_factory=dict)
    keep_thinking_content: bool = False

    @field_validator("thinking")
    @classmethod
    def validate_thinking(cls, value: dict[str, str]) -> dict[str, str]:
        for key, label in value.items():
            if not key.strip() or not label.strip():
                raise ValueError("thinking keys and labels must be non-empty")
        return value

    @field_validator("icon")
    @classmethod
    def validate_icon(cls, value: str | ModelIconConfig | None) -> str | ModelIconConfig | None:
        if isinstance(value, str) and len(value) > 4000:
            raise ValueError("icon must be at most 4000 characters")
        return value


@dataclass(frozen=True)
class CatalogSnapshot:
    models: list[ModelConfig]
    last_error: str | None = None


_lock = RLock()
_models: list[ModelConfig] = []
_last_error: str | None = None


def snapshot() -> CatalogSnapshot:
    with _lock:
        return CatalogSnapshot(models=list(_models), last_error=_last_error)


def list_models() -> list[ModelConfig]:
    return snapshot().models


def replace_models_for_tests(models: list[dict[str, Any]]) -> None:
    parsed = _parse_models(models)
    with _lock:
        global _models, _last_error
        _models = parsed
        _last_error = None


def get_model(model_id: str | None) -> ModelConfig | None:
    models = list_models()
    if model_id:
        for model in models:
            if model.id == model_id:
                return model
    return models[0] if models else None


def normalize_thinking_effort(model: ModelConfig, effort: str | None) -> str | None:
    if not model.thinking:
        return None
    if effort and effort in model.thinking:
        return effort
    return next(iter(model.thinking.keys()))


def load_once() -> CatalogSnapshot:
    global _models, _last_error

    MODEL_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not MODEL_CONFIG_PATH.exists():
        MODEL_CONFIG_PATH.write_text("[]\n", encoding="utf-8")

    try:
        raw = json.loads(MODEL_CONFIG_PATH.read_text(encoding="utf-8"))
        models = _parse_models(raw)
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        with _lock:
            _last_error = message
            current = CatalogSnapshot(models=list(_models), last_error=_last_error)
        logger.warning(f"模型配置加载失败，保留上次有效配置：{message}")
        return current

    with _lock:
        _models = models
        _last_error = None
        return CatalogSnapshot(models=list(_models), last_error=None)


async def reload_loop() -> None:
    while True:
        await asyncio.to_thread(load_once)
        await asyncio.sleep(RELOAD_INTERVAL_SECONDS)


def _parse_models(raw: Any) -> list[ModelConfig]:
    if not isinstance(raw, list):
        raise ValueError("models.json top-level value must be an array")
    models: list[ModelConfig] = []
    seen: set[str] = set()
    for item in raw:
        try:
            model = ModelConfig.model_validate(item)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc
        if model.id in seen:
            raise ValueError(f"duplicate model id: {model.id}")
        seen.add(model.id)
        models.append(model)
    return models
