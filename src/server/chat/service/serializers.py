# -*- coding: utf-8 -*-
"""Serializers for ChatWeb service objects."""

from __future__ import annotations

from typing import Any

from ..dao import ChatDAO, parse_message_parts, parse_tool_calls
from ..models import ChatMessage, ChatSession
from ..tools import get_tool_display_name


def serialize_session(session: ChatSession) -> dict[str, Any]:
    return {
        "id": session.id,
        "title": session.title,
        "active_leaf_message_id": session.active_leaf_message_id,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
    }


def serialize_message(message: ChatMessage, dao: ChatDAO | None = None) -> dict[str, Any]:
    tool_calls = enrich_tool_calls(parse_tool_calls(message.tool_calls_json))
    parts = enrich_message_parts(parse_message_parts(message.parts_json))
    version_info = build_version_info(message, dao)
    return {
        "id": message.id,
        "session_id": message.session_id,
        "role": message.role,
        "content": message.content,
        "model_id": message.model_id,
        "thinking_effort": message.thinking_effort,
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


def enrich_tool_calls(tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [enrich_tool_call(tool_call) for tool_call in tool_calls]


def enrich_message_parts(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched_parts: list[dict[str, Any]] = []
    for part in parts:
        enriched = dict(part)
        tool_call = enriched.get("tool_call")
        if enriched.get("type") == "tool":
            if not isinstance(tool_call, dict):
                continue
            enriched["tool_call"] = enrich_tool_call(tool_call)
        enriched_parts.append(enriched)
    return enriched_parts


def enrich_tool_call(tool_call: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(tool_call)
    name = str(enriched.get("name") or "unknown_tool")
    if not enriched.get("display_name"):
        enriched["display_name"] = get_tool_display_name(name)
    return enriched


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
