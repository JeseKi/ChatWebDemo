# -*- coding: utf-8 -*-
"""ChatWeb service exports."""

from .agent import (
    build_agent_input,
    build_agent_messages,
    build_chat_agent,
    stream_agent_events,
)
from .constants import MAX_HISTORY_MESSAGES
from .events import (
    append_output_part,
    append_reasoning_part,
    is_content_event,
    is_event,
    is_reasoning_event,
    normalize_event_name,
    sse_event,
)
from .serializers import (
    build_fallback_parts,
    build_version_info,
    serialize_context_compression,
    serialize_message,
    serialize_run,
    serialize_session,
)
from .runs import stream_run_events
from .sessions import activate_message_version, get_session_detail
from .share import create_session_share, get_shared_image, get_shared_session
from .streaming import stream_chat, stream_edit_message, stream_regenerate

__all__ = [
    "MAX_HISTORY_MESSAGES",
    "activate_message_version",
    "append_output_part",
    "append_reasoning_part",
    "build_agent_input",
    "build_agent_messages",
    "build_chat_agent",
    "build_fallback_parts",
    "build_version_info",
    "create_session_share",
    "get_shared_image",
    "get_shared_session",
    "get_session_detail",
    "is_content_event",
    "is_event",
    "is_reasoning_event",
    "normalize_event_name",
    "serialize_message",
    "serialize_context_compression",
    "serialize_run",
    "serialize_session",
    "sse_event",
    "stream_agent_events",
    "stream_chat",
    "stream_edit_message",
    "stream_regenerate",
    "stream_run_events",
]
