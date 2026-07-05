# -*- coding: utf-8 -*-
"""ChatWeb conversation DAO facade."""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.server.dao.dao_base import BaseDAO

from .compressions import ChatCompressionDAO
from .json_utils import parse_message_parts, parse_tool_calls
from .messages import ChatMessageDAO
from .runs import ChatRunDAO
from .sessions import ChatSessionDAO


class ChatDAO(
    ChatSessionDAO,
    ChatMessageDAO,
    ChatRunDAO,
    ChatCompressionDAO,
    BaseDAO,
):
    def __init__(self, db_session: Session):
        super().__init__(db_session)


__all__ = [
    "ChatDAO",
    "parse_message_parts",
    "parse_tool_calls",
]
