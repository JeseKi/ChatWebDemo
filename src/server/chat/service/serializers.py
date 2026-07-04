# -*- coding: utf-8 -*-
"""Serializers for ChatWeb service objects."""

from __future__ import annotations

from typing import Any

from ..dao import ChatDAO, parse_message_parts, parse_tool_calls
from ..models import ChatMessage, ChatSession


def serialize_session(session: ChatSession) -> dict[str, Any]:
    return {
        "id": session.id,
        "title": session.title,
        "active_leaf_message_id": session.active_leaf_message_id,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
    }


def serialize_message(message: ChatMessage, dao: ChatDAO | None = None) -> dict[str, Any]:
    tool_calls = parse_tool_calls(message.tool_calls_json)
    parts = parse_message_parts(message.parts_json)
    version_info = build_version_info(message, dao)
    return {
        "id": message.id,
        "session_id": message.session_id,
        "role": message.role,
        "content": message.content,
        "parent_message_id": message.parent_message_id,
        "source_message_id": message.source_message_id,
        "version_index": message.version_index,
        **version_info,
        "tool_calls": tool_calls,
        "parts": parts or build_fallback_parts(message.content, tool_calls),
        "sequence": message.sequence,
        "created_at": message.created_at.isoformat(),
    }


def build_fallback_parts(
    content: str, tool_calls: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    if content:
        parts.append({"id": "output-1", "type": "output", "content": content})
    for index, tool_call in enumerate(tool_calls, start=1):
        parts.append(
            {
                "id": str(tool_call.get("id") or f"tool-{index}"),
                "type": "tool",
                "tool_call": tool_call,
            }
        )
    return parts


def build_version_info(message: ChatMessage, dao: ChatDAO | None) -> dict[str, int | None]:
    if dao is None:
        return {
            "version_count": 1,
            "version_position": 1,
            "previous_version_message_id": None,
            "next_version_message_id": None,
        }

    versions = dao.list_versions_for_message(message)
    version_ids = [item.id for item in versions]
    try:
        index = version_ids.index(message.id)
    except ValueError:
        index = 0
    return {
        "version_count": len(versions),
        "version_position": index + 1,
        "previous_version_message_id": version_ids[index - 1] if index > 0 else None,
        "next_version_message_id": (
            version_ids[index + 1] if index + 1 < len(version_ids) else None
        ),
    }
