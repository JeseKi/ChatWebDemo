# -*- coding: utf-8 -*-
"""Built-in Agent tools for ChatWeb."""

from __future__ import annotations

from typing import Any

ORDER_DATA: dict[str, dict[str, Any]] = {
    "ORDER-8831": {
        "status": "delayed",
        "eta": "2026-07-06",
        "carrier": "SF Express",
        "last_event": "Arrived at Shanghai sorting center",
        "recommended_action": (
            "Apologize, confirm the updated ETA, and offer expedited follow-up "
            "if it misses the new date."
        ),
    },
    "ORDER-2048": {
        "status": "delivered",
        "eta": "2026-07-02",
        "carrier": "DHL",
        "last_event": "Delivered and signed by recipient",
        "recommended_action": (
            "Confirm delivery details and ask whether the customer needs anything else."
        ),
    },
    "ORDER-5199": {
        "status": "needs_attention",
        "eta": "unknown",
        "carrier": "UPS",
        "last_event": "Address verification failed",
        "recommended_action": (
            "Ask the customer to confirm the shipping address before rescheduling delivery."
        ),
    },
}


def get_order_status(order_id: str) -> dict[str, Any]:
    """Look up a demo order by order ID and return shipping support context."""
    normalized = order_id.strip().upper()
    if normalized in ORDER_DATA:
        return {"order_id": normalized, **ORDER_DATA[normalized]}

    return {
        "order_id": normalized,
        "status": "not_found",
        "eta": None,
        "carrier": None,
        "last_event": "No matching demo order was found.",
        "recommended_action": "Ask the customer to verify the order ID.",
    }


def get_chat_tools() -> list[Any]:
    return [get_order_status]

