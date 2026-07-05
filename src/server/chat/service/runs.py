# -*- coding: utf-8 -*-
"""Durable in-process chat run execution and replay."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from typing import Any, Protocol

from sqlalchemy.orm import Session, sessionmaker

from src.server.chat.agent.base import ChatRunEvent as AgentRunEvent
from src.server.chat.agent.contracts import LLMMessage
from src.server.token_audit import service as token_audit_service

from ..dao import ChatDAO
from ..models import ChatRun, ChatRunEvent
from .context_compression import ContextCompressionError, prepare_agent_context
from .events import (
    append_output_part,
    append_reasoning_part,
    is_content_event,
    is_event,
    is_reasoning_event,
    merge_completed_tool_call,
    merge_completed_tool_part,
    normalize_event_name,
    sse_event,
    tool_call_from_event,
)
from .images import escape_image_markers
from .model_catalog import ModelConfig, get_model
from .serializers import serialize_message, serialize_session

TERMINAL_RUN_STATUSES = {"succeeded", "failed", "canceled"}


class AgentRunner(Protocol):
    def __call__(
        self,
        messages: list[LLMMessage],
        *,
        model_config: ModelConfig,
        thinking_effort: str | None,
        user_id: str,
    ) -> AsyncIterator[AgentRunEvent]:
        ...


class ChatRunManager:
    def __init__(self, agent_runner: AgentRunner | None = None) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._agent_runner = agent_runner

    def start(self, run_id: str, session_factory: Callable[[], Session]) -> None:
        if run_id in self._tasks:
            return
        task = asyncio.create_task(self._run(run_id, session_factory))
        self._tasks[run_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(run_id, None))

    async def _run(self, run_id: str, session_factory: Callable[[], Session]) -> None:
        with session_factory() as db:
            dao = ChatDAO(db)
            run = dao.get_run_by_id(run_id=run_id)
            if run is None:
                return
            lock = self._locks.setdefault(run.session_id, asyncio.Lock())

        async with lock:
            with session_factory() as db:
                await _execute_run(
                    db,
                    run_id=run_id,
                    agent_runner=self._agent_runner or _default_agent_runner,
                )


manager = ChatRunManager()


def build_session_factory(db: Session) -> Callable[[], Session]:
    return sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False)


def event_payload(event: ChatRunEvent) -> dict[str, Any]:
    try:
        data = json.loads(event.data_json)
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {"value": data}
    return {**data, "seq": event.sequence, "run_id": event.run_id}


async def stream_run_events(
    db: Session,
    *,
    run_id: str,
    user_id: int,
    after: int = 0,
    poll_interval: float = 0.2,
) -> AsyncIterator[str]:
    dao = ChatDAO(db)
    run = dao.get_run(run_id=run_id, user_id=user_id)
    if not run:
        yield sse_event("error", {"message": "任务不存在"})
        return

    cursor = max(after, 0)
    while True:
        events = dao.list_run_events_after(
            run_id=run_id,
            user_id=user_id,
            after=cursor,
            limit=100,
        )
        for event in events:
            cursor = event.sequence
            yield sse_event(event.type, event_payload(event))
        if len(events) >= 100:
            continue

        db.expire_all()
        run = dao.get_run(run_id=run_id, user_id=user_id)
        if not run or run.status in TERMINAL_RUN_STATUSES:
            while True:
                remaining = dao.list_run_events_after(
                    run_id=run_id,
                    user_id=user_id,
                    after=cursor,
                    limit=100,
                )
                if not remaining:
                    break
                for event in remaining:
                    cursor = event.sequence
                    yield sse_event(event.type, event_payload(event))
            return

        await asyncio.sleep(poll_interval)


async def _execute_run(
    db: Session,
    *,
    run_id: str,
    agent_runner: AgentRunner | None = None,
) -> None:
    dao = ChatDAO(db)
    run = dao.get_run_by_id(run_id=run_id)
    if run is None or run.status in TERMINAL_RUN_STATUSES:
        return

    model_config = get_model(run.model_id)
    if model_config is None:
        _fail_run(dao, run, "选择的模型不存在，请重新选择")
        return

    dao.update_run_status(run_id=run.id, status="running")
    user_message = dao.get_message(message_id=run.user_message_id, user_id=run.user_id)
    assistant_message = dao.get_message(
        message_id=run.assistant_message_id,
        user_id=run.user_id,
    )
    if user_message is None or assistant_message is None:
        _fail_run(dao, run, "任务消息不存在")
        return

    try:
        prepared_context = await prepare_agent_context(
            dao,
            user_message=user_message,
            model_config=model_config,
            thinking_effort=run.thinking_effort,
            trigger="auto",
            event_sink=lambda event_type, data: _append_event(dao, run, event_type, data),
        )
    except ContextCompressionError as exc:
        _fail_run(dao, run, str(exc))
        return
    agent_input = prepared_context.messages
    content_chunks: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    parts: list[dict[str, Any]] = []
    usage_request_index = 0

    try:
        runner = agent_runner or _default_agent_runner
        run_events = runner(
            agent_input,
            model_config=model_config,
            thinking_effort=run.thinking_effort,
            user_id=str(run.user_id),
        )
        async for run_event in run_events:
            event_name = normalize_event_name(getattr(run_event, "event", ""))
            usage = getattr(run_event, "usage", None)
            if usage is not None and is_event(event_name, "run_usage"):
                usage_request_index += 1
                token_audit_service.create_usage_audit(
                    db,
                    user_id=run.user_id,
                    session_id=run.session_id,
                    run_id=run.id,
                    request_index=usage_request_index,
                    provider=usage.provider,
                    model_id=usage.model_id,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    total_tokens=usage.total_tokens,
                    reasoning_tokens=usage.reasoning_tokens,
                    cached_input_tokens=usage.cached_input_tokens,
                    tool_tokens=usage.tool_tokens,
                    raw_usage=usage.raw_usage,
                )
                continue

            if is_event(event_name, "tool_call_started"):
                tool_call = tool_call_from_event(
                    run_event,
                    status_value="running",
                    fallback_id=f"tool-{len(tool_calls) + 1}",
                )
                tool_calls.append(tool_call)
                parts.append({"id": tool_call["id"], "type": "tool", "tool_call": tool_call})
                dao.update_message_payload(
                    message_id=assistant_message.id,
                    user_id=run.user_id,
                    tool_calls=tool_calls,
                    parts=parts,
                )
                _append_event(dao, run, "tool_call_started", {"tool_call": tool_call})
                continue

            if is_event(event_name, "tool_call_completed"):
                completed = tool_call_from_event(
                    run_event,
                    status_value="completed",
                    fallback_id=f"tool-{len(tool_calls) + 1}",
                )
                merge_completed_tool_call(tool_calls, completed)
                merge_completed_tool_part(parts, completed)
                dao.update_message_payload(
                    message_id=assistant_message.id,
                    user_id=run.user_id,
                    tool_calls=tool_calls,
                    parts=parts,
                )
                _append_event(dao, run, "tool_call_completed", {"tool_call": completed})
                continue

            content = getattr(run_event, "content", None)
            if content and is_content_event(event_name):
                text = escape_image_markers(str(content))
                content_chunks.append(text)
                part_id = append_output_part(parts, text)
                dao.update_message_payload(
                    message_id=assistant_message.id,
                    user_id=run.user_id,
                    content="".join(content_chunks),
                    tool_calls=tool_calls,
                    parts=parts,
                )
                _append_event(
                    dao,
                    run,
                    "content_delta",
                    {"part_id": part_id, "delta": text},
                )
                continue

            reasoning_content = getattr(run_event, "reasoning_content", None)
            if reasoning_content and is_reasoning_event(event_name):
                text = escape_image_markers(str(reasoning_content))
                part_id = append_reasoning_part(parts, text)
                dao.update_message_payload(
                    message_id=assistant_message.id,
                    user_id=run.user_id,
                    content="".join(content_chunks),
                    tool_calls=tool_calls,
                    parts=parts,
                )
                _append_event(
                    dao,
                    run,
                    "reasoning_delta",
                    {"part_id": part_id, "delta": text},
                )
    except Exception as exc:
        _fail_run(dao, run, f"Agent 请求失败: {exc}", content_chunks=content_chunks, parts=parts)
        return

    assistant_content = "".join(content_chunks).strip() or "模型没有返回内容。"
    assistant_message = dao.update_message_payload(
        message_id=assistant_message.id,
        user_id=run.user_id,
        content=assistant_content,
        tool_calls=tool_calls,
        parts=parts or [{"id": "output-1", "type": "output", "content": assistant_content}],
    )
    dao.update_run_status(run_id=run.id, status="succeeded")
    session = dao.get_session(session_id=run.session_id, user_id=run.user_id)
    if assistant_message is not None and session is not None:
        _append_event(
            dao,
            run,
            "done",
            {
                "message": serialize_message(assistant_message, dao),
                "session": serialize_session(session),
            },
        )


def _append_event(
    dao: ChatDAO,
    run: ChatRun,
    event_type: str,
    data: dict[str, Any],
) -> None:
    dao.append_run_event(
        run_id=run.id,
        session_id=run.session_id,
        user_id=run.user_id,
        event_type=event_type,
        data=data,
    )


def _fail_run(
    dao: ChatDAO,
    run: ChatRun,
    message: str,
    *,
    content_chunks: list[str] | None = None,
    parts: list[dict[str, Any]] | None = None,
) -> None:
    content = "".join(content_chunks or []).strip()
    if not content:
        content = message
        parts = [{"id": "output-1", "type": "output", "content": message}]
    dao.update_message_payload(
        message_id=run.assistant_message_id,
        user_id=run.user_id,
        content=content,
        parts=parts,
    )
    _append_event(dao, run, "error", {"message": message})
    dao.update_run_status(run_id=run.id, status="failed", error=message)


def _default_agent_runner(
    messages: list[LLMMessage],
    *,
    model_config: ModelConfig,
    thinking_effort: str | None,
    user_id: str,
) -> AsyncIterator[AgentRunEvent]:
    from src.server.chat import service

    return service.stream_agent_events(
        messages,
        model_config=model_config,
        thinking_effort=thinking_effort,
        user_id=user_id,
    )
