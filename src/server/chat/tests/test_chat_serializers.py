# -*- coding: utf-8 -*-

from src.server.chat.service.serializers import enrich_message_parts, enrich_tool_calls


def test_enrich_tool_calls_adds_display_name_to_legacy_payloads():
    tool_calls = [
        {
            "id": "tool-1",
            "name": "get_order_status",
            "arguments": {"order_id": "ORDER-8831"},
            "result": {"status": "delayed"},
            "status": "completed",
        }
    ]

    enriched = enrich_tool_calls(tool_calls)

    assert enriched[0]["display_name"] == "查询订单状态"
    assert "display_name" not in tool_calls[0]


def test_enrich_message_parts_adds_display_name_to_legacy_tool_parts():
    parts = [
        {
            "id": "tool-1",
            "type": "tool",
            "tool_call": {
                "id": "tool-1",
                "name": "get_order_status",
                "arguments": {"order_id": "ORDER-8831"},
                "result": None,
                "status": "running",
            },
        }
    ]

    enriched = enrich_message_parts(parts)

    assert enriched[0]["tool_call"]["display_name"] == "查询订单状态"
    assert "display_name" not in parts[0]["tool_call"]


def test_enrich_message_parts_drops_invalid_tool_parts():
    parts = [
        {"id": "tool-1", "type": "tool", "tool_call": None},
        {"id": "output-1", "type": "output", "content": "回复"},
    ]

    enriched = enrich_message_parts(parts)

    assert enriched == [{"id": "output-1", "type": "output", "content": "回复"}]
