# -*- coding: utf-8 -*-
"""Context compression for ChatWeb message trees."""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from src.server.chat.agent.contracts import LLMMessage
from src.server.chat.agent.factory import build_llm_provider

from ..dao import ChatDAO, parse_message_parts, parse_tool_calls
from ..models import ChatContextCompression, ChatMessage
from .agent import build_agent_messages
from .constants import CHAT_AGENT_INSTRUCTIONS
from .images import (
    content_without_image_markers,
    estimate_image_tokens,
    estimate_text_tokens,
    extract_image_urls,
    get_user_image,
    image_id_from_url,
)
from .model_catalog import ModelConfig
from .serializers import serialize_context_compression

COMPRESSION_TRIGGER_RATIO = 0.85
TAIL_BUDGET_RATIO = 0.25
MIN_TAIL_TOKENS = 2_000
MAX_TAIL_TOKENS = 8_000
SUMMARY_MAX_OUTPUT_TOKENS = 4_096
SUMMARY_TOOL_OUTPUT_MAX_CHARS = 2_000

CONTEXT_COMPRESSION_SYSTEM_PROMPT = (
    "You are an anchored context summarization assistant for support chat sessions. "
    "Summarize only the conversation history you are given. Preserve exact identifiers, "
    "dates, order IDs, URLs, tool facts, errors, constraints, and user preferences. "
    "Do not answer the conversation itself. Respond in the same language as the conversation."
)

SUMMARY_TEMPLATE = """Output exactly this Markdown structure and keep the section order unchanged:

## Objective
- [one or two brief sentences describing what the user is trying to accomplish]

## Important Details
- [constraints, decisions, exact identifiers, relevant facts, or "(none)"]

## Work State
- Completed: [finished work or facts established; otherwise "(none)"]
- Active: [current unresolved work or latest state; otherwise "(none)"]
- Blocked: [blockers, failing commands, or unknowns; otherwise "(none)"]

## Next Move
1. [immediate concrete action, or "(none)"]
2. [next action if known, or "(none)"]

Rules:
- Keep every section, even when empty.
- Use terse bullets, not prose paragraphs.
- Preserve exact names, IDs, dates, error strings, URLs, and tool results when known.
- Do not mention summarization, compression, or context limits."""


class ContextCompressionError(Exception):
    """Raised when the prompt cannot be made safe for the selected model."""


@dataclass
class ContextCompressionEvent:
    type: str
    data: dict[str, Any]


@dataclass
class PreparedAgentContext:
    messages: list[LLMMessage]
    compression: ChatContextCompression | None = None
    events: list[ContextCompressionEvent] = field(default_factory=list)


EventSink = Callable[[str, dict[str, Any]], None]


async def prepare_agent_context(
    dao: ChatDAO,
    *,
    user_message: ChatMessage,
    model_config: ModelConfig,
    thinking_effort: str | None,
    trigger: str = "auto",
    event_sink: EventSink | None = None,
) -> PreparedAgentContext:
    path = dao.list_path_to_message(message=user_message)
    if not path:
        raise ContextCompressionError("任务消息不存在")

    events: list[ContextCompressionEvent] = []

    def emit(event_type: str, data: dict[str, Any]) -> None:
        events.append(ContextCompressionEvent(event_type, data))
        if event_sink is not None:
            event_sink(event_type, data)

    usable = _usable_input_tokens(model_config)
    compression = select_applicable_compression(dao, path=path, target_message=user_message)
    prepared_messages = _build_messages_for_path(path, compression)
    estimate = estimate_agent_context(path, compression)

    if _context_is_usable(estimate, model_config):
        return PreparedAgentContext(messages=prepared_messages, compression=compression, events=events)

    new_compression = await _create_compression_if_possible(
        dao,
        path=path,
        current=compression,
        model_config=model_config,
        thinking_effort=thinking_effort,
        trigger=trigger,
        usable_tokens=usable,
        emit=emit,
    )
    if new_compression is not None:
        compression = new_compression
        prepared_messages = _build_messages_for_path(path, compression)
        estimate = estimate_agent_context(path, compression)
        if _context_is_usable(estimate, model_config) or _context_fits_hard_limit(
            estimate,
            model_config,
        ):
            return PreparedAgentContext(
                messages=prepared_messages,
                compression=compression,
                events=events,
            )

    raw_estimate = estimate_agent_context(path, None)
    if _context_fits_hard_limit(raw_estimate, model_config):
        emit(
            "context_compaction_warning",
            {"message": "上下文压缩失败，已暂时使用原始上下文。"},
        )
        return PreparedAgentContext(messages=build_agent_messages(path), events=events)

    if estimate.has_images and not model_config.visual:
        raise ContextCompressionError("当前会话包含图片，请选择支持视觉的模型")
    raise ContextCompressionError("当前会话上下文预计超出模型限制，且自动压缩失败")


def select_applicable_compression(
    dao: ChatDAO,
    *,
    path: list[ChatMessage],
    target_message: ChatMessage,
) -> ChatContextCompression | None:
    if not path:
        return None
    positions = {message.id: index for index, message in enumerate(path)}
    target_index = positions.get(target_message.id)
    if target_index is None:
        return None

    candidates = []
    for compression in dao.list_context_compressions(
        session_id=target_message.session_id,
        user_id=target_message.user_id,
    ):
        head_index = positions.get(compression.head_end_message_id)
        tail_index = positions.get(compression.tail_start_message_id)
        if head_index is None or tail_index is None:
            continue
        if head_index >= tail_index or head_index >= target_index:
            continue
        candidates.append((head_index, compression.id, compression))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (item[0], item[1]))[-1][2]


def compression_applies_to_path(
    compression: ChatContextCompression,
    *,
    path: list[ChatMessage],
) -> bool:
    positions = {message.id: index for index, message in enumerate(path)}
    head_index = positions.get(compression.head_end_message_id)
    tail_index = positions.get(compression.tail_start_message_id)
    return head_index is not None and tail_index is not None and head_index < tail_index


def estimate_agent_context(
    path: list[ChatMessage],
    compression: ChatContextCompression | None,
) -> "ContextEstimate":
    messages = _messages_after_compression(path, compression)
    total = estimate_text_tokens(CHAT_AGENT_INSTRUCTIONS)
    has_images = False
    if compression is not None:
        total += estimate_text_tokens(compression.summary)
    for message in messages:
        message_estimate = estimate_message_tokens(message)
        total += message_estimate.tokens
        has_images = has_images or message_estimate.has_images
    return ContextEstimate(tokens=total, has_images=has_images)


@dataclass(frozen=True)
class ContextEstimate:
    tokens: int
    has_images: bool = False


@dataclass(frozen=True)
class MessageEstimate:
    tokens: int
    has_images: bool = False


def estimate_message_tokens(message: ChatMessage) -> MessageEstimate:
    total = estimate_text_tokens(content_without_image_markers(message.content))
    has_images = False
    for url in extract_image_urls(message.content):
        image_id = image_id_from_url(url)
        if not image_id:
            continue
        stored = get_user_image(message.user_id, image_id)
        if stored is None:
            continue
        has_images = True
        total += estimate_image_tokens(stored.width, stored.height)
    return MessageEstimate(tokens=total, has_images=has_images)


async def summarize_messages(
    *,
    messages: list[ChatMessage],
    previous_summary: str | None,
    model_config: ModelConfig,
    thinking_effort: str | None,
    user_id: int,
) -> str:
    prompt = _build_summary_prompt(messages, previous_summary)
    summary_model = model_config.model_copy(
        update={"max_output": min(SUMMARY_MAX_OUTPUT_TOKENS, model_config.max_output)}
    )
    provider = build_llm_provider(summary_model, thinking_effort)
    chunks: list[str] = []
    async for event in provider.stream_turn(
        [
            LLMMessage(role="system", content=CONTEXT_COMPRESSION_SYSTEM_PROMPT),
            LLMMessage(role="user", content=prompt),
        ],
        tools=[],
        user_id=str(user_id),
        allow_tools=False,
    ):
        if event.type == "content_delta" and event.content:
            chunks.append(event.content)
    return "".join(chunks).strip()


async def _create_compression_if_possible(
    dao: ChatDAO,
    *,
    path: list[ChatMessage],
    current: ChatContextCompression | None,
    model_config: ModelConfig,
    thinking_effort: str | None,
    trigger: str,
    usable_tokens: int,
    emit: EventSink,
) -> ChatContextCompression | None:
    tail_start_index = _select_tail_start_index(path, usable_tokens)
    if tail_start_index <= 0:
        return None

    head_end_index = tail_start_index - 1
    head_end = path[head_end_index]
    tail_start = path[tail_start_index]
    if current and current.head_end_message_id == head_end.id:
        return current

    previous_summary = current.summary if current else None
    summarize_start = 0
    if current is not None:
        current_head_index = _index_of(path, current.head_end_message_id)
        if current_head_index is not None:
            summarize_start = current_head_index + 1
    messages_to_summarize = path[summarize_start : head_end_index + 1]
    if not messages_to_summarize and not previous_summary:
        return None

    emit(
        "context_compaction_started",
        {
            "trigger": trigger,
            "head_end_message_id": head_end.id,
            "tail_start_message_id": tail_start.id,
        },
    )
    try:
        summary = await summarize_messages(
            messages=messages_to_summarize,
            previous_summary=previous_summary,
            model_config=model_config,
            thinking_effort=thinking_effort,
            user_id=head_end.user_id,
        )
    except Exception as exc:
        emit("context_compaction_warning", {"message": f"上下文压缩失败: {exc}"})
        return None
    if not summary:
        emit("context_compaction_warning", {"message": "上下文压缩失败: 摘要为空"})
        return None

    compression = dao.create_context_compression(
        session_id=head_end.session_id,
        user_id=head_end.user_id,
        head_end_message_id=head_end.id,
        tail_start_message_id=tail_start.id,
        source_leaf_message_id=path[-1].id,
        previous_compression_id=current.id if current else None,
        trigger=trigger,
        summary=summary,
        summary_model_id=model_config.id,
        original_token_estimate=estimate_agent_context(path, None).tokens,
        summary_token_estimate=estimate_text_tokens(summary),
        message_count=head_end_index + 1,
    )
    emit(
        "context_compaction_done",
        {
            "compression": serialize_context_compression(
                compression,
                applies_to_active_path=True,
            )
        },
    )
    return compression


def _build_messages_for_path(
    path: list[ChatMessage],
    compression: ChatContextCompression | None,
) -> list[LLMMessage]:
    return build_agent_messages(
        _messages_after_compression(path, compression),
        context_summary=compression.summary if compression else None,
    )


def _messages_after_compression(
    path: list[ChatMessage],
    compression: ChatContextCompression | None,
) -> list[ChatMessage]:
    if compression is None:
        return path
    head_index = _index_of(path, compression.head_end_message_id)
    if head_index is None:
        return path
    return path[head_index + 1 :]


def _context_is_usable(
    estimate: ContextEstimate,
    model_config: ModelConfig,
) -> bool:
    if estimate.has_images and not model_config.visual:
        return False
    threshold = _compression_trigger_tokens(model_config)
    return estimate.tokens < threshold


def _context_fits_hard_limit(
    estimate: ContextEstimate,
    model_config: ModelConfig,
) -> bool:
    if estimate.has_images and not model_config.visual:
        return False
    return estimate.tokens <= model_config.context


def _compression_trigger_tokens(model_config: ModelConfig) -> int:
    return math.ceil(model_config.context * COMPRESSION_TRIGGER_RATIO)


def _usable_input_tokens(model_config: ModelConfig) -> int:
    return max(1, model_config.context)


def _select_tail_start_index(path: list[ChatMessage], usable_tokens: int) -> int:
    if len(path) <= 1:
        return 0
    user_indices = [index for index, message in enumerate(path) if message.role == "user"]
    if not user_indices:
        return max(0, len(path) - 1)

    current_user_pos = len(user_indices) - 1
    tail_start_index = user_indices[max(0, current_user_pos - 1)]
    budget = min(
        MAX_TAIL_TOKENS,
        max(MIN_TAIL_TOKENS, int(usable_tokens * TAIL_BUDGET_RATIO)),
    )
    while tail_start_index < len(path) - 1:
        tail_estimate = sum(estimate_message_tokens(message).tokens for message in path[tail_start_index:])
        if tail_estimate <= budget:
            break
        tail_start_index += 1
    return tail_start_index


def _index_of(path: list[ChatMessage], message_id: int) -> int | None:
    for index, message in enumerate(path):
        if message.id == message_id:
            return index
    return None


def _build_summary_prompt(
    messages: list[ChatMessage],
    previous_summary: str | None,
) -> str:
    sections = []
    if previous_summary:
        sections.append(
            "Update the anchored summary below using the conversation history after it. "
            "Preserve still-true details, remove stale details, and merge in new facts.\n"
            f"<previous-summary>\n{previous_summary}\n</previous-summary>"
        )
    else:
        sections.append("Create a new anchored summary from the conversation history below.")
    sections.append(SUMMARY_TEMPLATE)
    if messages:
        sections.append("<conversation>\n" + "\n\n".join(_serialize_for_summary(messages)) + "\n</conversation>")
    return "\n\n".join(sections)


def _serialize_for_summary(messages: list[ChatMessage]) -> list[str]:
    return [_serialize_message_for_summary(message) for message in messages]


def _serialize_message_for_summary(message: ChatMessage) -> str:
    role = "User" if message.role == "user" else "Assistant"
    content = content_without_image_markers(message.content).strip()
    image_descriptions = []
    for url in extract_image_urls(message.content):
        image_id = image_id_from_url(url)
        if not image_id:
            continue
        stored = get_user_image(message.user_id, image_id)
        if stored is None:
            image_descriptions.append(f"[image: {image_id}]")
            continue
        image_descriptions.append(
            f"[image: {image_id}, {stored.mime_type}, {stored.width}x{stored.height}]"
        )
    lines = [f"[{role} #{message.id}]"]
    if content:
        lines.append(content)
    lines.extend(image_descriptions)
    tool_calls = parse_tool_calls(message.tool_calls_json)
    for tool_call in tool_calls:
        lines.append(
            "[Assistant tool call]: "
            + json.dumps(_truncate_tool_call(tool_call), ensure_ascii=False, default=str)
        )
    for part in parse_message_parts(message.parts_json):
        if part.get("type") != "tool":
            continue
        part_tool_call = part.get("tool_call")
        if isinstance(part_tool_call, dict):
            lines.append(
                "[Assistant tool part]: "
                + json.dumps(_truncate_tool_call(part_tool_call), ensure_ascii=False, default=str)
            )
    return "\n".join(lines)


def _truncate_tool_call(tool_call: dict[str, Any]) -> dict[str, Any]:
    result = dict(tool_call)
    value = result.get("result")
    if isinstance(value, str) and len(value) > SUMMARY_TOOL_OUTPUT_MAX_CHARS:
        result["result"] = value[:SUMMARY_TOOL_OUTPUT_MAX_CHARS] + "\n[truncated]"
    return result
