# -*- coding: utf-8 -*-
"""SSE and agent event helpers for ChatWeb."""

from __future__ import annotations

import json
from typing import Any

from ..schemas import ToolCallTrace
from ..tools import get_tool_display_name


def sse_event(event: str, payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {data}\n\n"


def normalize_event_name(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw).replace(".", "_").replace("-", "_").lower()


def is_event(event_name: str, expected: str) -> bool:
    return event_name == expected or event_name == expected.replace("_", "")


def is_content_event(event_name: str) -> bool:
    return event_name in {
        "run_content",
        "runcontent",
        "run_intermediate_content",
        "runintermediatecontent",
    }


def tool_call_from_event(
    run_event: Any,
    *,
    status_value: str,
    fallback_id: str,
) -> dict[str, Any]:
    tool = getattr(run_event, "tool", None)
    name = getattr(tool, "tool_name", None) or getattr(tool, "name", None) or "unknown_tool"
    arguments = getattr(tool, "tool_args", None) or getattr(tool, "args", None) or {}
    result = json_safe(getattr(tool, "result", None))
    if not isinstance(arguments, dict):
        arguments = {"value": arguments}
    payload = ToolCallTrace(
        id=fallback_id,
        name=str(name),
        display_name=get_tool_display_name(str(name)),
        arguments=arguments,
        result=result,
        status=status_value,  # type: ignore[arg-type]
    )
    return payload.model_dump()


def merge_completed_tool_call(
    tool_calls: list[dict[str, Any]],
    completed: dict[str, Any],
) -> None:
    for existing in reversed(tool_calls):
        if existing.get("status") == "running" and existing.get("name") == completed.get("name"):
            completed["id"] = existing["id"]
            existing.update(completed)
            return
    tool_calls.append(completed)


def append_output_part(parts: list[dict[str, Any]], delta: str) -> str:
    if parts and parts[-1].get("type") == "output":
        parts[-1]["content"] = f"{parts[-1].get('content', '')}{delta}"
        return str(parts[-1]["id"])

    part_id = f"output-{len(parts) + 1}"
    parts.append({"id": part_id, "type": "output", "content": delta})
    return part_id


def merge_completed_tool_part(
    parts: list[dict[str, Any]],
    completed: dict[str, Any],
) -> None:
    for existing in reversed(parts):
        tool_call = existing.get("tool_call")
        if (
            existing.get("type") == "tool"
            and isinstance(tool_call, dict)
            and tool_call.get("id") == completed.get("id")
        ):
            existing["tool_call"] = completed
            return

    parts.append(
        {
            "id": str(completed.get("id") or f"tool-{len(parts) + 1}"),
            "type": "tool",
            "tool_call": completed,
        }
    )


def json_safe(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except TypeError:
        return str(value)
