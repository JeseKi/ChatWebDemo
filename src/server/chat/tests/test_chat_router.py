# -*- coding: utf-8 -*-
import json
from http import HTTPStatus
from types import SimpleNamespace
from typing import Any

from src.server.chat import service
from src.server.chat.models import ChatMessage, ChatSession


def _login_admin(test_client):
    resp = test_client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert resp.status_code == HTTPStatus.OK, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _parse_sse(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in text.strip().split("\n\n"):
        event_name = None
        data = None
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line.removeprefix("event:").strip()
            if line.startswith("data:"):
                data = json.loads(line.removeprefix("data:").strip())
        if event_name and data is not None:
            events.append({"event": event_name, "data": data})
    return events


def test_stream_chat_persists_messages_and_tool_calls(
    test_client, init_test_database, monkeypatch
):
    headers = _login_admin(test_client)

    async def fake_stream_agent_events(prompt: str, *, user_id: str, session_id: str):
        assert "ORDER-8831" in prompt
        assert user_id == "1"
        assert session_id
        yield SimpleNamespace(
            event="ToolCallStarted",
            tool=SimpleNamespace(
                tool_name="get_order_status",
                tool_args={"order_id": "ORDER-8831"},
                result=None,
            ),
        )
        yield SimpleNamespace(
            event="ToolCallCompleted",
            tool=SimpleNamespace(
                tool_name="get_order_status",
                tool_args={"order_id": "ORDER-8831"},
                result={"order_id": "ORDER-8831", "status": "delayed"},
            ),
        )
        yield SimpleNamespace(event="RunContent", content="订单已延迟")
        yield SimpleNamespace(event="RunContent", content="，预计 7 月 6 日送达。")

    monkeypatch.setattr(service, "stream_agent_events", fake_stream_agent_events)

    resp = test_client.post(
        "/api/chat/stream",
        json={"message": "查询 ORDER-8831 的状态"},
        headers=headers,
    )

    assert resp.status_code == HTTPStatus.OK, resp.text
    events = _parse_sse(resp.text)
    assert [event["event"] for event in events] == [
        "session_ready",
        "user_message",
        "tool_call_started",
        "tool_call_completed",
        "content_delta",
        "content_delta",
        "done",
    ]
    assert events[4]["data"]["part_id"] == "output-2"

    done = events[-1]["data"]
    session_id = done["session"]["id"]
    assert done["message"]["content"] == "订单已延迟，预计 7 月 6 日送达。"
    assert done["message"]["tool_calls"][0]["name"] == "get_order_status"
    assert done["message"]["tool_calls"][0]["status"] == "completed"
    assert [part["type"] for part in done["message"]["parts"]] == ["tool", "output"]
    assert done["message"]["parts"][0]["tool_call"]["name"] == "get_order_status"
    assert done["message"]["parts"][1]["content"] == "订单已延迟，预计 7 月 6 日送达。"

    detail_resp = test_client.get(f"/api/chat/sessions/{session_id}", headers=headers)
    assert detail_resp.status_code == HTTPStatus.OK, detail_resp.text
    detail = detail_resp.json()
    assert detail["title"] == "查询 ORDER-8831 的状态"
    assert [message["role"] for message in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["tool_calls"][0]["result"]["status"] == "delayed"
    assert [part["type"] for part in detail["messages"][1]["parts"]] == ["tool", "output"]

    list_resp = test_client.get("/api/chat/sessions", headers=headers)
    assert list_resp.status_code == HTTPStatus.OK, list_resp.text
    assert list_resp.json()[0]["id"] == session_id


def test_update_and_delete_chat_session(
    test_client, test_db_session, init_test_database, monkeypatch
):
    headers = _login_admin(test_client)

    async def fake_stream_agent_events(prompt: str, *, user_id: str, session_id: str):
        yield SimpleNamespace(event="RunContent", content="你好")

    monkeypatch.setattr(service, "stream_agent_events", fake_stream_agent_events)

    create_resp = test_client.post(
        "/api/chat/stream",
        json={"message": "初始会话名称"},
        headers=headers,
    )
    assert create_resp.status_code == HTTPStatus.OK, create_resp.text
    session_id = _parse_sse(create_resp.text)[-1]["data"]["session"]["id"]

    update_resp = test_client.patch(
        f"/api/chat/sessions/{session_id}",
        json={"title": "  客服订单查询  "},
        headers=headers,
    )
    assert update_resp.status_code == HTTPStatus.OK, update_resp.text
    assert update_resp.json()["title"] == "客服订单查询"

    list_resp = test_client.get("/api/chat/sessions", headers=headers)
    assert list_resp.status_code == HTTPStatus.OK, list_resp.text
    assert list_resp.json()[0]["title"] == "客服订单查询"

    delete_resp = test_client.delete(f"/api/chat/sessions/{session_id}", headers=headers)
    assert delete_resp.status_code == HTTPStatus.NO_CONTENT, delete_resp.text

    stored_session = (
        test_db_session.query(ChatSession).filter(ChatSession.id == session_id).first()
    )
    assert stored_session is not None
    assert stored_session.deleted_at is not None
    assert (
        test_db_session.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .count()
        == 2
    )

    detail_resp = test_client.get(f"/api/chat/sessions/{session_id}", headers=headers)
    assert detail_resp.status_code == HTTPStatus.NOT_FOUND

    list_after_delete_resp = test_client.get("/api/chat/sessions", headers=headers)
    assert list_after_delete_resp.status_code == HTTPStatus.OK, list_after_delete_resp.text
    assert list_after_delete_resp.json() == []


def test_chat_requires_authentication(test_client):
    resp = test_client.get("/api/chat/sessions")
    assert resp.status_code == HTTPStatus.UNAUTHORIZED

    stream_resp = test_client.post(
        "/api/chat/stream",
        json={"message": "hello"},
    )
    assert stream_resp.status_code == HTTPStatus.UNAUTHORIZED
