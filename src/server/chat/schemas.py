# -*- coding: utf-8 -*-
"""ChatWeb schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

CHAT_SESSION_ID_PATTERN = r"^[A-Za-z0-9]{32}$"
ChatRole = Literal["user", "assistant"]
ToolCallStatus = Literal["running", "completed", "failed"]
AssistantPartType = Literal["reasoning", "output", "tool"]


class ChatStreamRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = Field(default=None, pattern=CHAT_SESSION_ID_PATTERN)


class ChatSessionUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)


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
    id: int
    session_id: str = Field(..., pattern=CHAT_SESSION_ID_PATTERN)
    role: ChatRole
    content: str
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


class ChatSessionDetailOut(ChatSessionOut):
    messages: list[ChatMessageOut]


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
