# -*- coding: utf-8 -*-
"""Chat DAO JSON and ID helpers."""

from __future__ import annotations

import json
import secrets
import string

SESSION_ID_LENGTH = 32
SESSION_ID_ALPHABET = string.ascii_letters + string.digits
MAX_SESSION_ID_GENERATION_ATTEMPTS = 5


def parse_tool_calls(value: str | None) -> list[dict]:
    return _parse_json_list(value)


def parse_message_parts(value: str | None) -> list[dict]:
    return _parse_json_list(value)


def dump_tool_calls(tool_calls: list[dict] | None) -> str | None:
    return dump_json_list(tool_calls)


def dump_json_list(items: list[dict] | None) -> str | None:
    if not items:
        return None
    return json.dumps(items, ensure_ascii=False)


def dump_json_object(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def generate_chat_id() -> str:
    return "".join(secrets.choice(SESSION_ID_ALPHABET) for _ in range(SESSION_ID_LENGTH))


def _parse_json_list(value: str | None) -> list[dict]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]
