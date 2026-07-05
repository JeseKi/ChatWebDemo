# -*- coding: utf-8 -*-
"""ChatWeb API routes."""

from __future__ import annotations

from .base import router
from .images import get_image, upload_image
from .models import list_models
from .sessions import delete_session, get_session, list_sessions, update_session
from .shares import create_session_share, get_shared_image, get_shared_session
from .streams import (
    activate_message_version,
    edit_message_stream,
    regenerate_stream,
    stream_message,
    stream_run,
)

__all__ = [
    "activate_message_version",
    "create_session_share",
    "delete_session",
    "edit_message_stream",
    "get_image",
    "get_session",
    "get_shared_image",
    "get_shared_session",
    "list_models",
    "list_sessions",
    "regenerate_stream",
    "router",
    "stream_message",
    "stream_run",
    "update_session",
    "upload_image",
]
