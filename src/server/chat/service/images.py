# -*- coding: utf-8 -*-
"""User image storage and marker helpers for ChatWeb."""

from __future__ import annotations

import base64
import re
import secrets
import struct
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from src.server.config import global_config

IMAGE_OPEN = "<|IMAGE|>"
IMAGE_CLOSE = "</|IMAGE|>"
ESCAPED_IMAGE_OPEN = "<\\|IMAGE\\|>"
ESCAPED_IMAGE_CLOSE = "</\\|IMAGE\\|>"
IMAGE_MARKER_PATTERN = re.compile(r"<\|IMAGE\|>(?P<url>.*?)</\|IMAGE\|>")

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGES_PER_MESSAGE = 8
IMAGE_ROOT = Path(global_config.project_root) / "data"

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


@dataclass(frozen=True)
class StoredImage:
    image_id: str
    url: str
    mime_type: str
    width: int
    height: int
    path: Path

    @property
    def data_url(self) -> str:
        encoded = base64.b64encode(self.path.read_bytes()).decode("ascii")
        return f"data:{self.mime_type};base64,{encoded}"

    @property
    def base64_data(self) -> str:
        return base64.b64encode(self.path.read_bytes()).decode("ascii")

    @property
    def data_bytes(self) -> bytes:
        return self.path.read_bytes()


def escape_image_markers(text: str) -> str:
    return text.replace(IMAGE_OPEN, ESCAPED_IMAGE_OPEN).replace(
        IMAGE_CLOSE, ESCAPED_IMAGE_CLOSE
    )


def append_image_markers(text: str, images: list[StoredImage]) -> str:
    parts = [escape_image_markers(text.strip())] if text.strip() else []
    parts.extend(f"{IMAGE_OPEN}{image.url}{IMAGE_CLOSE}" for image in images)
    return "\n".join(parts)


def extract_image_urls(content: str) -> list[str]:
    return [match.group("url") for match in IMAGE_MARKER_PATTERN.finditer(content)]


def content_without_image_markers(content: str) -> str:
    return IMAGE_MARKER_PATTERN.sub("", content).strip()


def estimate_text_tokens(text: str) -> int:
    tokens = 0.0
    for char in text:
        tokens += 0.6 if _is_cjk(char) else 0.3
    return int(tokens + 0.999999)


def estimate_image_tokens(width: int, height: int) -> int:
    import math

    return math.ceil(width / 512) * math.ceil(height / 512) * 200


async def store_upload(user_id: int, upload: UploadFile) -> StoredImage:
    data = await upload.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="图片不能为空")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="图片不能超过 10MB")

    detected = detect_image(data)
    if detected is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅支持 JPEG、PNG、WebP 图片",
        )
    mime_type, width, height = detected
    suffix = ALLOWED_IMAGE_TYPES[mime_type]
    image_id = secrets.token_urlsafe(24).replace("-", "").replace("_", "")[:32]
    directory = user_image_directory(user_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{image_id}{suffix}"
    path.write_bytes(data)
    return StoredImage(
        image_id=image_id,
        url=image_url(image_id),
        mime_type=mime_type,
        width=width,
        height=height,
        path=path,
    )


def image_url(image_id: str) -> str:
    return f"/api/chat/images/{image_id}"


def share_image_url(token: str, image_id: str) -> str:
    return f"/api/chat/shares/{token}/images/{image_id}"


def get_user_image(user_id: int, image_id: str) -> StoredImage | None:
    if not _valid_image_id(image_id):
        return None
    matches = list(user_image_directory(user_id).glob(f"{image_id}.*"))
    if len(matches) != 1:
        return None
    path = matches[0]
    detected = detect_image(path.read_bytes())
    if detected is None:
        return None
    mime_type, width, height = detected
    return StoredImage(
        image_id=image_id,
        url=image_url(image_id),
        mime_type=mime_type,
        width=width,
        height=height,
        path=path,
    )


def image_id_from_url(url: str) -> str | None:
    match = re.search(r"/api/chat/(?:shares/[^/]+/)?images/([^/?#]+)", url)
    if not match:
        return None
    image_id = match.group(1)
    return image_id if _valid_image_id(image_id) else None


def user_image_directory(user_id: int) -> Path:
    return IMAGE_ROOT / str(user_id) / "images"


def detect_image(data: bytes) -> tuple[str, int, int] | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return ("image/png", width, height) if width and height else None
    if data.startswith(b"\xff\xd8"):
        size = _jpeg_size(data)
        return ("image/jpeg", *size) if size else None
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        size = _webp_size(data)
        return ("image/webp", *size) if size else None
    return None


def _jpeg_size(data: bytes) -> tuple[int, int] | None:
    index = 2
    while index + 9 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        index += 2
        if marker in {0xD8, 0xD9}:
            continue
        if index + 2 > len(data):
            return None
        length = int.from_bytes(data[index : index + 2], "big")
        if length < 2 or index + length > len(data):
            return None
        if marker in {
            0xC0,
            0xC1,
            0xC2,
            0xC3,
            0xC5,
            0xC6,
            0xC7,
            0xC9,
            0xCA,
            0xCB,
            0xCD,
            0xCE,
            0xCF,
        }:
            height = int.from_bytes(data[index + 3 : index + 5], "big")
            width = int.from_bytes(data[index + 5 : index + 7], "big")
            return (width, height) if width and height else None
        index += length
    return None


def _webp_size(data: bytes) -> tuple[int, int] | None:
    chunk = data[12:16]
    if chunk == b"VP8X" and len(data) >= 30:
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
        return width, height
    if chunk == b"VP8L" and len(data) >= 25:
        bits = int.from_bytes(data[21:25], "little")
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
        return width, height
    if chunk == b"VP8 " and len(data) >= 30:
        width = int.from_bytes(data[26:28], "little") & 0x3FFF
        height = int.from_bytes(data[28:30], "little") & 0x3FFF
        return (width, height) if width and height else None
    return None


def _valid_image_id(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9]{12,80}", value))


def _is_cjk(char: str) -> bool:
    code = ord(char)
    return (
        0x4E00 <= code <= 0x9FFF
        or 0x3400 <= code <= 0x4DBF
        or 0x20000 <= code <= 0x2A6DF
        or 0x2A700 <= code <= 0x2B73F
        or 0x2B740 <= code <= 0x2B81F
        or 0x2B820 <= code <= 0x2CEAF
        or 0xF900 <= code <= 0xFAFF
    )
