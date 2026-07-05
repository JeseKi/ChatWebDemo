# -*- coding: utf-8 -*-
"""ChatWeb schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CHAT_SESSION_ID_PATTERN = r"^[A-Za-z0-9]{32}$"
ChatRole = Literal["user", "assistant"]
ToolCallStatus = Literal["running", "completed", "failed"]
AssistantPartType = Literal["reasoning", "output", "tool"]
ChatRunStatus = Literal["queued", "running", "succeeded", "failed", "canceled"]


class ChatStreamRequest(BaseModel):
    message: str = Field(default="", max_length=4000)
    session_id: str | None = Field(default=None, pattern=CHAT_SESSION_ID_PATTERN)
    model: str | None = Field(default=None, min_length=1, max_length=120)
    variant: str | None = Field(default=None, min_length=1, max_length=80)
    images: list["ChatImageReference"] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def validate_content(self) -> "ChatStreamRequest":
        if not self.message.strip() and not self.images:
            raise ValueError("消息不能为空")
        return self


class ChatSessionUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)


class ChatRegenerateRequest(BaseModel):
    model: str | None = Field(default=None, min_length=1, max_length=120)
    variant: str | None = Field(default=None, min_length=1, max_length=80)


class ToolCallTrace(BaseModel):
    id: str
    name: str
    display_name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: Any = None
    status: ToolCallStatus


class AssistantMessagePart(BaseModel):
    id: str
    type: AssistantPartType
    content: str | None = None
    tool_call: ToolCallTrace | None = None


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int
    session_id: str = Field(..., pattern=CHAT_SESSION_ID_PATTERN)
    role: ChatRole
    content: str
    model_id: str | None = None
    thinking_effort: str | None = None
    parent_message_id: int | None = None
    source_message_id: int | None = None
    version_index: int = 1
    version_count: int = 1
    version_position: int = 1
    previous_version_message_id: int | None = None
    next_version_message_id: int | None = None
    tool_calls: list[ToolCallTrace] = Field(default_factory=list)
    parts: list[AssistantMessagePart] = Field(default_factory=list)
    sequence: int
    created_at: datetime


class ChatSessionOut(BaseModel):
    id: str = Field(..., pattern=CHAT_SESSION_ID_PATTERN)
    title: str
    active_leaf_message_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatRunOut(BaseModel):
    id: str = Field(..., min_length=1, max_length=32)
    session_id: str = Field(..., pattern=CHAT_SESSION_ID_PATTERN)
    status: ChatRunStatus
    assistant_message_id: int
    latest_seq: int = 0
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ChatSessionDetailOut(ChatSessionOut):
    messages: list[ChatMessageOut]
    active_run: ChatRunOut | None = None


class ChatSessionShareOut(BaseModel):
    token: str
    share_url: str
    title: str
    message_count: int
    created_at: datetime


class SharedChatSessionOut(BaseModel):
    token: str
    title: str
    source_session_id: str = Field(..., pattern=CHAT_SESSION_ID_PATTERN)
    source_active_leaf_message_id: int | None = None
    message_count: int
    created_at: datetime
    messages: list[ChatMessageOut]


class ChatModelIconOut(BaseModel):
    light: str | None = None
    dark: str | None = None
    mode: Literal["auto", "mask", "image"] = "auto"


class ChatModelOut(BaseModel):
    provider: str
    id: str
    name: str
    icon: str | ChatModelIconOut | None = None
    context: int
    max_output: int
    visual: bool
    thinking: dict[str, str] = Field(default_factory=dict)
    keep_thinking_content: bool = False


class ChatModelsResponse(BaseModel):
    models: list[ChatModelOut]
    last_error: str | None = None


class ChatImageReference(BaseModel):
    image_id: str = Field(..., min_length=1, max_length=80)
    url: str | None = Field(default=None, max_length=300)
    mime_type: str | None = Field(default=None, max_length=80)
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)


class ChatImageOut(BaseModel):
    image_id: str
    url: str
    mime_type: str
    width: int
    height: int
