# -*- coding: utf-8 -*-
"""Shared ChatWeb router."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/chat", tags=["ChatWeb"])
