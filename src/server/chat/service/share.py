# -*- coding: utf-8 -*-
"""Chat session sharing service."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.server.auth.models import User
from src.server.config import global_config

from ..dao import ChatDAO, ChatShareDAO
from ..models import ChatSessionShare
from ..schemas import ChatMessageOut, ChatSessionShareOut, SharedChatSessionOut
from .images import (
    IMAGE_CLOSE,
    IMAGE_OPEN,
    StoredImage,
    extract_image_urls,
    get_user_image,
    image_id_from_url,
    share_image_url,
)
from .serializers import serialize_message

SHARE_TOKEN_SIGNATURE_LENGTH = 16
SHARE_TOKEN_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
VOLATILE_SHARE_MESSAGE_FIELDS = {
    "version_count",
    "version_position",
    "previous_version_message_id",
    "next_version_message_id",
}


def create_session_share(
    db: Session,
    *,
    current_user: User,
    session_id: str,
) -> ChatSessionShareOut:
    dao = ChatDAO(db)
    share_dao = ChatShareDAO(db)
    session = dao.get_session(session_id=session_id, user_id=current_user.id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="聊天会话不存在")

    messages = dao.list_active_path(session=session)
    snapshot = {
        "messages": [serialize_message(message, dao) for message in messages],
    }
    snapshot_json = _dump_snapshot(snapshot)
    existing_share = _find_existing_share(
        share_dao,
        owner_user_id=current_user.id,
        source_session_id=session.id,
        source_active_leaf_message_id=session.active_leaf_message_id,
        snapshot_json=snapshot_json,
    )
    if existing_share:
        token = _create_share_token(
            share_id=existing_share.id,
            source_session_id=existing_share.source_session_id,
            snapshot_json=existing_share.snapshot_json,
        )
        return _share_out(existing_share, token=token)

    share = share_dao.create_session_share(
        owner_user_id=current_user.id,
        source_session_id=session.id,
        source_active_leaf_message_id=session.active_leaf_message_id,
        title=session.title,
        snapshot_json=snapshot_json,
        message_count=len(messages),
    )
    token = _create_share_token(
        share_id=share.id,
        source_session_id=session.id,
        snapshot_json=snapshot_json,
    )
    db.commit()
    db.refresh(share)
    return _share_out(share, token=token)


def get_shared_session(db: Session, *, token: str) -> SharedChatSessionOut:
    share_id = _share_id_from_token(token)
    if share_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分享不存在")

    share = ChatShareDAO(db).get_session_share_by_id(share_id)
    if not share:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分享不存在")
    source_session = ChatDAO(db).get_session(
        session_id=share.source_session_id,
        user_id=share.owner_user_id,
    )
    if not source_session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分享不存在")
    expected_token = _create_share_token(
        share_id=share.id,
        source_session_id=share.source_session_id,
        snapshot_json=share.snapshot_json,
    )
    if not hmac.compare_digest(expected_token, token):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分享不存在")
    snapshot = _load_snapshot(share.snapshot_json)
    messages = [
        ChatMessageOut.model_validate(_rewrite_message_images_for_share(message, token))
        for message in snapshot.get("messages", [])
        if isinstance(message, dict)
    ]
    return SharedChatSessionOut.model_validate(
        {
            "token": token,
            "title": share.title,
            "source_session_id": share.source_session_id,
            "source_active_leaf_message_id": share.source_active_leaf_message_id,
            "message_count": share.message_count,
            "created_at": share.created_at,
            "messages": messages,
        }
    )


def get_shared_image(db: Session, *, token: str, image_id: str) -> StoredImage:
    share = _validated_share(db, token)
    snapshot = _load_snapshot(share.snapshot_json)
    allowed = False
    for message in snapshot.get("messages", []):
        if not isinstance(message, dict):
            continue
        content = str(message.get("content") or "")
        for url in extract_image_urls(content):
            if image_id_from_url(url) == image_id:
                allowed = True
                break
        if allowed:
            break
    if not allowed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="图片不存在")
    stored = get_user_image(share.owner_user_id, image_id)
    if stored is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="图片不存在")
    return stored


def _validated_share(db: Session, token: str) -> ChatSessionShare:
    share_id = _share_id_from_token(token)
    if share_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分享不存在")

    share = ChatShareDAO(db).get_session_share_by_id(share_id)
    if not share:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分享不存在")
    source_session = ChatDAO(db).get_session(
        session_id=share.source_session_id,
        user_id=share.owner_user_id,
    )
    if not source_session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分享不存在")
    expected_token = _create_share_token(
        share_id=share.id,
        source_session_id=share.source_session_id,
        snapshot_json=share.snapshot_json,
    )
    if not hmac.compare_digest(expected_token, token):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分享不存在")
    return share


def _rewrite_message_images_for_share(message: dict[str, Any], token: str) -> dict[str, Any]:
    rewritten = dict(message)
    content = str(rewritten.get("content") or "")
    for url in extract_image_urls(content):
        image_id = image_id_from_url(url)
        if not image_id:
            continue
        content = content.replace(
            f"{IMAGE_OPEN}{url}{IMAGE_CLOSE}",
            f"{IMAGE_OPEN}{share_image_url(token, image_id)}{IMAGE_CLOSE}",
        )
    rewritten["content"] = content
    return rewritten


def _share_out(share: ChatSessionShare, *, token: str) -> ChatSessionShareOut:
    return ChatSessionShareOut.model_validate(
        {
            "token": token,
            "share_url": _build_share_url(token),
            "title": share.title,
            "message_count": share.message_count,
            "created_at": share.created_at,
        }
    )


def _find_existing_share(
    share_dao: ChatShareDAO,
    *,
    owner_user_id: int,
    source_session_id: str,
    source_active_leaf_message_id: int | None,
    snapshot_json: str,
) -> ChatSessionShare | None:
    existing_share = share_dao.get_session_share_by_snapshot(
        owner_user_id=owner_user_id,
        source_session_id=source_session_id,
        source_active_leaf_message_id=source_active_leaf_message_id,
        snapshot_json=snapshot_json,
    )
    if existing_share:
        return existing_share

    stable_snapshot_json = _stable_snapshot_json(snapshot_json)
    for share in share_dao.list_session_shares_by_leaf(
        owner_user_id=owner_user_id,
        source_session_id=source_session_id,
        source_active_leaf_message_id=source_active_leaf_message_id,
    ):
        if _stable_snapshot_json(share.snapshot_json) == stable_snapshot_json:
            return share
    return None


def _stable_snapshot_json(snapshot_json: str) -> str:
    snapshot = _load_snapshot(snapshot_json)
    stable_messages = []
    for message in snapshot.get("messages", []):
        if not isinstance(message, dict):
            continue
        stable_messages.append(
            {
                key: value
                for key, value in message.items()
                if key not in VOLATILE_SHARE_MESSAGE_FIELDS
            }
        )
    return _dump_snapshot({"messages": stable_messages})


def _create_share_token(
    *,
    share_id: int,
    source_session_id: str,
    snapshot_json: str,
) -> str:
    share_id_segment = _base62_encode(share_id)
    signature = _share_signature(
        share_id=share_id,
        source_session_id=source_session_id,
        snapshot_json=snapshot_json,
    )
    return f"{share_id_segment}.{signature}"


def _share_id_from_token(token: str) -> int | None:
    try:
        share_id_segment, signature = token.split(".", 1)
    except ValueError:
        return None
    if len(signature) != SHARE_TOKEN_SIGNATURE_LENGTH:
        return None
    return _base62_decode(share_id_segment)


def _share_signature(
    *,
    share_id: int,
    source_session_id: str,
    snapshot_json: str,
) -> str:
    value = f"{share_id}:{source_session_id}:{_snapshot_digest(snapshot_json)}"
    return _sign(value.encode("utf-8"))[:SHARE_TOKEN_SIGNATURE_LENGTH]


def _build_share_url(token: str) -> str:
    base_url = str(global_config.app_domain or "").rstrip("/")
    path = f"/shared/chat/{token}"
    return f"{base_url}{path}" if base_url else path


def _snapshot_digest(snapshot_json: str) -> str:
    return hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()


def _sign(value: bytes) -> str:
    secret = global_config.app_secret_key.encode("utf-8")
    digest = hmac.new(secret, value, hashlib.sha256).digest()
    return _b64encode(digest)


def _dump_snapshot(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load_snapshot(value: str) -> dict[str, Any]:
    try:
        snapshot = json.loads(value)
    except json.JSONDecodeError:
        return {"messages": []}
    return snapshot if isinstance(snapshot, dict) else {"messages": []}


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _base62_encode(value: int) -> str:
    if value == 0:
        return SHARE_TOKEN_ALPHABET[0]
    result = ""
    base = len(SHARE_TOKEN_ALPHABET)
    current = value
    while current:
        current, remainder = divmod(current, base)
        result = f"{SHARE_TOKEN_ALPHABET[remainder]}{result}"
    return result


def _base62_decode(value: str) -> int | None:
    if not value:
        return None
    base = len(SHARE_TOKEN_ALPHABET)
    result = 0
    for char in value:
        index = SHARE_TOKEN_ALPHABET.find(char)
        if index < 0:
            return None
        result = result * base + index
    return result
