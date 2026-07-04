# -*- coding: utf-8 -*-
"""ChatWeb service layer."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.server.auth.models import User

from .dao import ChatDAO, parse_message_parts, parse_tool_calls
from .models import ChatMessage, ChatSession
from .schemas import ChatMessageOut, ChatSessionDetailOut, ToolCallTrace
from .tools import get_chat_tools

DEFAULT_MODEL_ID = "gpt-4o-mini"
MAX_HISTORY_MESSAGES = 20


def serialize_session(session: ChatSession) -> dict[str, Any]:
    return {
        "id": session.id,
        "title": session.title,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
    }


def serialize_message(message: ChatMessage) -> dict[str, Any]:
    tool_calls = parse_tool_calls(message.tool_calls_json)
    parts = parse_message_parts(message.parts_json)
    return {
        "id": message.id,
        "session_id": message.session_id,
        "role": message.role,
        "content": message.content,
        "tool_calls": tool_calls,
        "parts": parts or build_fallback_parts(message.content, tool_calls),
        "sequence": message.sequence,
        "created_at": message.created_at.isoformat(),
    }


def get_session_detail(
    db: Session, *, session_id: str, current_user: User
) -> ChatSessionDetailOut:
    dao = ChatDAO(db)
    session = dao.get_session(session_id=session_id, user_id=current_user.id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="聊天会话不存在")

    messages = [
        ChatMessageOut.model_validate(serialize_message(message))
        for message in dao.list_messages(session_id=session.id, user_id=current_user.id)
    ]
    return ChatSessionDetailOut.model_validate({**serialize_session(session), "messages": messages})


async def stream_chat(
    db: Session,
    *,
    current_user: User,
    message: str,
    session_id: str | None,
) -> AsyncIterator[str]:
    dao = ChatDAO(db)
    prompt = message.strip()
    if not prompt:
        yield sse_event("error", {"message": "消息不能为空"})
        return

    session = _resolve_or_create_session(
        dao,
        current_user=current_user,
        session_id=session_id,
        first_message=prompt,
    )
    user_message = dao.append_message(
        session_id=session.id,
        user_id=current_user.id,
        role="user",
        content=prompt,
    )

    yield sse_event("session_ready", {"session": serialize_session(session)})
    yield sse_event("user_message", {"message": serialize_message(user_message)})

    history = dao.list_messages(session_id=session.id, user_id=current_user.id)
    agent_input = build_agent_input(history)
    content_chunks: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    parts: list[dict[str, Any]] = []

    try:
        async for run_event in stream_agent_events(
            agent_input,
            user_id=str(current_user.id),
            session_id=session.id,
        ):
            event_name = normalize_event_name(getattr(run_event, "event", ""))
            if is_event(event_name, "tool_call_started"):
                tool_call = _tool_call_from_event(
                    run_event,
                    status_value="running",
                    fallback_id=f"tool-{len(tool_calls) + 1}",
                )
                tool_calls.append(tool_call)
                parts.append({"id": tool_call["id"], "type": "tool", "tool_call": tool_call})
                yield sse_event("tool_call_started", {"tool_call": tool_call})
                continue

            if is_event(event_name, "tool_call_completed"):
                completed = _tool_call_from_event(
                    run_event,
                    status_value="completed",
                    fallback_id=f"tool-{len(tool_calls) + 1}",
                )
                _merge_completed_tool_call(tool_calls, completed)
                _merge_completed_tool_part(parts, completed)
                yield sse_event("tool_call_completed", {"tool_call": completed})
                continue

            content = getattr(run_event, "content", None)
            if content and is_content_event(event_name):
                text = str(content)
                content_chunks.append(text)
                part_id = append_output_part(parts, text)
                yield sse_event("content_delta", {"part_id": part_id, "delta": text})
    except Exception as exc:
        yield sse_event("error", {"message": f"Agent 请求失败: {exc}"})
        return

    assistant_content = "".join(content_chunks).strip()
    if not assistant_content:
        assistant_content = "模型没有返回内容。"

    assistant_message = dao.append_message(
        session_id=session.id,
        user_id=current_user.id,
        role="assistant",
        content=assistant_content,
        tool_calls=tool_calls,
        parts=parts,
    )
    yield sse_event(
        "done",
        {
            "message": serialize_message(assistant_message),
            "session": serialize_session(session),
        },
    )


async def stream_agent_events(
    prompt: str,
    *,
    user_id: str,
    session_id: str,
) -> AsyncIterator[Any]:
    agent = build_chat_agent()
    async for event in agent.arun(
        prompt,
        stream=True,
        stream_events=True,
        user_id=user_id,
        session_id=session_id,
    ):
        yield event


def build_chat_agent() -> Any:
    from agno.agent import Agent
    from agno.models.openai.like import OpenAILike

    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    model_id = os.getenv("OPENAI_MODEL", DEFAULT_MODEL_ID)
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY")
    if not base_url:
        raise RuntimeError("Missing OPENAI_BASE_URL")

    return Agent(
        model=OpenAILike(id=model_id, api_key=api_key, base_url=base_url),
        tools=get_chat_tools(),
        instructions=(
            "You are a concise support assistant. Use available tools when they are "
            "needed to answer factual order questions. Answer in the user's language."
        ),
        markdown=True,
        tool_call_limit=4,
    )


def build_agent_input(messages: list[ChatMessage]) -> str:
    recent_messages = messages[-MAX_HISTORY_MESSAGES:]
    lines = [
        "Conversation history follows. Answer the latest user message.",
        "",
    ]
    for item in recent_messages:
        role = "User" if item.role == "user" else "Assistant"
        lines.append(f"{role}: {item.content}")
    return "\n".join(lines)


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


def _resolve_or_create_session(
    dao: ChatDAO,
    *,
    current_user: User,
    session_id: str | None,
    first_message: str,
) -> ChatSession:
    if session_id:
        session = dao.get_session(session_id=session_id, user_id=current_user.id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="聊天会话不存在",
            )
        return session

    title = first_message.replace("\n", " ").strip()[:60] or "新对话"
    return dao.create_session(user_id=current_user.id, title=title)


def _tool_call_from_event(
    run_event: Any,
    *,
    status_value: str,
    fallback_id: str,
) -> dict[str, Any]:
    tool = getattr(run_event, "tool", None)
    name = getattr(tool, "tool_name", None) or getattr(tool, "name", None) or "unknown_tool"
    arguments = getattr(tool, "tool_args", None) or getattr(tool, "args", None) or {}
    result = _json_safe(getattr(tool, "result", None))
    if not isinstance(arguments, dict):
        arguments = {"value": arguments}
    payload = ToolCallTrace(
        id=fallback_id,
        name=str(name),
        arguments=arguments,
        result=result,
        status=status_value,  # type: ignore[arg-type]
    )
    return payload.model_dump()


def _merge_completed_tool_call(
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


def _merge_completed_tool_part(
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


def _json_safe(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except TypeError:
        return str(value)
