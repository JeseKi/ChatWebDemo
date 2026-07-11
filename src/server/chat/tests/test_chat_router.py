# -*- coding: utf-8 -*-
import json
import asyncio
from http import HTTPStatus
from types import SimpleNamespace
from typing import Any, AsyncGenerator, cast

import pytest

from src.server.chat import service
from src.server.auth import service as auth_service
from src.server.auth.models import User
from src.server.chat.models import ChatMessage, ChatSession, ChatSessionShare
from src.server.chat.dao import ChatDAO


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


async def _collect_stream_events(stream) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    async for chunk in stream:
        events.extend(_parse_sse(chunk))
    return events


async def _wait_for_run_succeeded(test_db_session, *, run_id: str) -> None:
    dao = ChatDAO(test_db_session)
    for _ in range(30):
        await asyncio.sleep(0.02)
        test_db_session.expire_all()
        run = dao.get_run_by_id(run_id=run_id)
        if run and run.status == "succeeded":
            return
    raise AssertionError("background chat run did not finish")


def _explicit_agent_runner(handler):
    async def runner(messages, *, model_config, thinking_effort, user_id: str):
        assert model_config.id == "test-model"
        assert thinking_effort == "low"
        async for event in handler(messages, user_id=user_id):
            yield event

    return runner


def test_stream_chat_persists_messages_and_tool_calls(
    test_client, init_test_database, monkeypatch
):
    headers = _login_admin(test_client)

    async def fake_stream_agent_events(messages, *, user_id: str):
        assert "ORDER-8831" in messages
        assert user_id == "1"
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

    monkeypatch.setattr(service, "stream_agent_events", _explicit_agent_runner(fake_stream_agent_events))

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
    assert events[2]["data"]["tool_call"]["display_name"] == "查询订单状态"
    assert events[3]["data"]["tool_call"]["display_name"] == "查询订单状态"
    assert done["message"]["tool_calls"][0]["name"] == "get_order_status"
    assert done["message"]["tool_calls"][0]["display_name"] == "查询订单状态"
    assert done["message"]["tool_calls"][0]["status"] == "completed"
    assert [part["type"] for part in done["message"]["parts"]] == ["tool", "output"]
    assert done["message"]["parts"][0]["tool_call"]["name"] == "get_order_status"
    assert done["message"]["parts"][0]["tool_call"]["display_name"] == "查询订单状态"
    assert done["message"]["parts"][1]["content"] == "订单已延迟，预计 7 月 6 日送达。"

    detail_resp = test_client.get(f"/api/chat/sessions/{session_id}", headers=headers)
    assert detail_resp.status_code == HTTPStatus.OK, detail_resp.text
    detail = detail_resp.json()
    assert detail["title"] == "查询 ORDER-8831 的状态"
    assert [message["role"] for message in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["tool_calls"][0]["display_name"] == "查询订单状态"
    assert detail["messages"][1]["tool_calls"][0]["result"]["status"] == "delayed"
    assert [part["type"] for part in detail["messages"][1]["parts"]] == ["tool", "output"]

    list_resp = test_client.get("/api/chat/sessions", headers=headers)
    assert list_resp.status_code == HTTPStatus.OK, list_resp.text
    assert list_resp.json()[0]["id"] == session_id


def test_stream_chat_persists_reasoning_parts(
    test_client, init_test_database, monkeypatch
):
    headers = _login_admin(test_client)

    async def fake_stream_agent_events(messages, *, user_id: str):
        yield SimpleNamespace(event="RunReasoningContent", reasoning_content="先检查订单状态")
        yield SimpleNamespace(event="RunReasoningContent", reasoning_content="，再组织回复。")
        yield SimpleNamespace(event="RunContent", content="订单会按时送达。")

    monkeypatch.setattr(service, "stream_agent_events", _explicit_agent_runner(fake_stream_agent_events))

    resp = test_client.post(
        "/api/chat/stream",
        json={"message": "帮我看看订单"},
        headers=headers,
    )

    assert resp.status_code == HTTPStatus.OK, resp.text
    events = _parse_sse(resp.text)
    assert [event["event"] for event in events] == [
        "session_ready",
        "user_message",
        "reasoning_delta",
        "reasoning_delta",
        "content_delta",
        "done",
    ]
    assert events[2]["data"]["part_id"] == "reasoning-1"
    assert events[4]["data"]["part_id"] == "output-2"

    done = events[-1]["data"]
    assert done["message"]["content"] == "订单会按时送达。"
    assert [part["type"] for part in done["message"]["parts"]] == [
        "reasoning",
        "output",
    ]
    assert done["message"]["parts"][0]["content"] == "先检查订单状态，再组织回复。"
    assert done["message"]["parts"][1]["content"] == "订单会按时送达。"

    detail_resp = test_client.get(
        f"/api/chat/sessions/{done['session']['id']}",
        headers=headers,
    )
    assert detail_resp.status_code == HTTPStatus.OK, detail_resp.text
    assistant = detail_resp.json()["messages"][1]
    assert assistant["content"] == "订单会按时送达。"
    assert [part["type"] for part in assistant["parts"]] == ["reasoning", "output"]


def test_stream_chat_background_run_survives_client_disconnect(
    test_db_session, init_test_database, monkeypatch
):
    current_user = test_db_session.query(User).filter(User.username == "admin").one()

    async def fake_stream_agent_events(messages, *, user_id: str):
        yield SimpleNamespace(event="RunContent", content="后台")
        await asyncio.sleep(0.01)
        yield SimpleNamespace(event="RunContent", content="完成")

    monkeypatch.setattr(service, "stream_agent_events", _explicit_agent_runner(fake_stream_agent_events))

    async def exercise_disconnect():
        stream = service.stream_chat(
            test_db_session,
            current_user=current_user,
            message="长任务",
            session_id=None,
            model_id="test-model",
            thinking_effort="low",
        )
        stream = cast(AsyncGenerator[str, None], stream)
        first = _parse_sse(await stream.__anext__())[0]
        second = _parse_sse(await stream.__anext__())[0]
        assert first["event"] == "session_ready"
        assert second["event"] == "user_message"
        run_id = first["data"]["run"]["id"]
        session_id = first["data"]["session"]["id"]
        await stream.aclose()

        dao = ChatDAO(test_db_session)
        for _ in range(30):
            await asyncio.sleep(0.02)
            test_db_session.expire_all()
            run = dao.get_run_by_id(run_id=run_id)
            if run and run.status == "succeeded":
                return session_id, run_id
        raise AssertionError("background chat run did not finish")

    session_id, run_id = asyncio.run(exercise_disconnect())
    test_db_session.expire_all()
    detail = service.get_session_detail(
        test_db_session,
        session_id=session_id,
        current_user=current_user,
    )

    assert detail.active_run is None
    assert [message.role for message in detail.messages] == ["user", "assistant"]
    assert detail.messages[1].content == "后台完成"

    dao = ChatDAO(test_db_session)
    events = dao.list_run_events_after(run_id=run_id, user_id=current_user.id, after=0)
    assert [event.type for event in events] == [
        "session_ready",
        "user_message",
        "content_delta",
        "content_delta",
        "done",
    ]


def test_stream_chat_rolls_back_prepare_when_run_creation_fails(
    test_db_session, init_test_database, monkeypatch
):
    current_user = test_db_session.query(User).filter(User.username == "admin").one()

    def fail_create_run(self, **kwargs):
        raise RuntimeError("run creation failed")

    monkeypatch.setattr(ChatDAO, "create_run", fail_create_run)

    async def exercise_failure():
        stream = service.stream_chat(
            test_db_session,
            current_user=current_user,
            message="不会落库",
            session_id=None,
            model_id="test-model",
            thinking_effort="low",
        )
        stream = cast(AsyncGenerator[str, None], stream)
        with pytest.raises(RuntimeError, match="run creation failed"):
            await stream.__anext__()

    asyncio.run(exercise_failure())
    test_db_session.expire_all()

    assert test_db_session.query(ChatSession).count() == 0
    assert test_db_session.query(ChatMessage).count() == 0


def test_edit_message_background_run_survives_client_disconnect(
    test_db_session, init_test_database, monkeypatch
):
    current_user = test_db_session.query(User).filter(User.username == "admin").one()

    async def first_agent(messages, *, user_id: str):
        yield SimpleNamespace(event="RunContent", content="旧回复")

    monkeypatch.setattr(service, "stream_agent_events", _explicit_agent_runner(first_agent))
    initial_events = asyncio.run(
        _collect_stream_events(
            service.stream_chat(
                test_db_session,
                current_user=current_user,
                message="旧问题",
                session_id=None,
                model_id="test-model",
                thinking_effort="low",
            )
        )
    )
    session_id = initial_events[-1]["data"]["session"]["id"]
    test_db_session.expire_all()
    old_user_id = service.get_session_detail(
        test_db_session,
        session_id=session_id,
        current_user=current_user,
    ).messages[0].id

    async def edited_agent(messages, *, user_id: str):
        await asyncio.sleep(0.01)
        yield SimpleNamespace(event="RunContent", content="新回复")

    monkeypatch.setattr(service, "stream_agent_events", _explicit_agent_runner(edited_agent))

    async def exercise_disconnect():
        stream = service.stream_edit_message(
            test_db_session,
            current_user=current_user,
            message_id=old_user_id,
            message="新问题",
            model_id="test-model",
            thinking_effort="low",
        )
        stream = cast(AsyncGenerator[str, None], stream)
        first = _parse_sse(await stream.__anext__())[0]
        second = _parse_sse(await stream.__anext__())[0]
        third = _parse_sse(await stream.__anext__())[0]
        assert [first["event"], second["event"], third["event"]] == [
            "session_ready",
            "branch_reset",
            "user_message",
        ]
        run_id = first["data"]["run"]["id"]
        await stream.aclose()
        await _wait_for_run_succeeded(test_db_session, run_id=run_id)
        return run_id

    run_id = asyncio.run(exercise_disconnect())
    test_db_session.expire_all()
    detail = service.get_session_detail(
        test_db_session,
        session_id=session_id,
        current_user=current_user,
    )
    assert detail.active_run is None
    assert [message.content for message in detail.messages] == ["新问题", "新回复"]
    assert detail.messages[0].source_message_id == old_user_id

    replay_events = asyncio.run(
        _collect_stream_events(
            service.stream_run_events(
                test_db_session,
                run_id=run_id,
                user_id=current_user.id,
                after=3,
            )
        )
    )
    assert [event["event"] for event in replay_events] == ["content_delta", "done"]
    assert all(event["data"]["run_id"] == run_id for event in replay_events)
    assert [event["data"]["seq"] for event in replay_events] == [4, 5]


def test_regenerate_background_run_survives_client_disconnect(
    test_db_session, init_test_database, monkeypatch
):
    current_user = test_db_session.query(User).filter(User.username == "admin").one()

    async def first_agent(messages, *, user_id: str):
        yield SimpleNamespace(event="RunContent", content="第一次回复")

    monkeypatch.setattr(service, "stream_agent_events", _explicit_agent_runner(first_agent))
    initial_events = asyncio.run(
        _collect_stream_events(
            service.stream_chat(
                test_db_session,
                current_user=current_user,
                message="请回答",
                session_id=None,
                model_id="test-model",
                thinking_effort="low",
            )
        )
    )
    session_id = initial_events[-1]["data"]["session"]["id"]
    old_assistant_id = initial_events[-1]["data"]["message"]["id"]

    async def regenerated_agent(messages, *, user_id: str):
        await asyncio.sleep(0.01)
        yield SimpleNamespace(event="RunContent", content="第二次回复")

    monkeypatch.setattr(service, "stream_agent_events", _explicit_agent_runner(regenerated_agent))

    async def exercise_disconnect():
        stream = service.stream_regenerate(
            test_db_session,
            current_user=current_user,
            session_id=session_id,
            model_id="test-model",
            thinking_effort="low",
        )
        stream = cast(AsyncGenerator[str, None], stream)
        first = _parse_sse(await stream.__anext__())[0]
        second = _parse_sse(await stream.__anext__())[0]
        assert [first["event"], second["event"]] == ["session_ready", "branch_reset"]
        run_id = first["data"]["run"]["id"]
        await stream.aclose()
        await _wait_for_run_succeeded(test_db_session, run_id=run_id)
        return run_id

    run_id = asyncio.run(exercise_disconnect())
    test_db_session.expire_all()
    detail = service.get_session_detail(
        test_db_session,
        session_id=session_id,
        current_user=current_user,
    )
    assert detail.active_run is None
    assert [message.content for message in detail.messages] == ["请回答", "第二次回复"]
    assert detail.messages[1].source_message_id == old_assistant_id
    assert detail.messages[1].version_index == 2

    replay_events = asyncio.run(
        _collect_stream_events(
            service.stream_run_events(
                test_db_session,
                run_id=run_id,
                user_id=current_user.id,
                after=2,
            )
        )
    )
    assert [event["event"] for event in replay_events] == ["content_delta", "done"]
    assert all(event["data"]["run_id"] == run_id for event in replay_events)
    assert [event["data"]["seq"] for event in replay_events] == [3, 4]


def test_update_and_delete_chat_session(
    test_client, test_db_session, init_test_database, monkeypatch
):
    headers = _login_admin(test_client)

    async def fake_stream_agent_events(messages, *, user_id: str):
        yield SimpleNamespace(event="RunContent", content="你好")

    monkeypatch.setattr(service, "stream_agent_events", _explicit_agent_runner(fake_stream_agent_events))

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


def test_bulk_delete_chat_sessions(test_client, test_db_session, init_test_database):
    headers = _login_admin(test_client)
    dao = ChatDAO(test_db_session)
    sessions = [
        dao.create_session(user_id=1, title=f"批量删除会话 {index}")
        for index in range(3)
    ]

    delete_resp = test_client.request(
        "DELETE",
        "/api/chat/sessions/bulk",
        json={"session_ids": [session.id for session in sessions[:2]]},
        headers=headers,
    )
    assert delete_resp.status_code == HTTPStatus.NO_CONTENT, delete_resp.text

    test_db_session.expire_all()
    assert all(session.deleted_at is not None for session in sessions[:2])
    assert sessions[2].deleted_at is None

    list_resp = test_client.get("/api/chat/sessions", headers=headers)
    assert list_resp.status_code == HTTPStatus.OK, list_resp.text
    assert [item["id"] for item in list_resp.json()] == [sessions[2].id]


def test_edit_user_message_creates_active_branch(
    test_client, test_db_session, init_test_database, monkeypatch
):
    headers = _login_admin(test_client)

    async def first_agent(messages, *, user_id: str):
        yield SimpleNamespace(event="RunContent", content="旧回复")

    monkeypatch.setattr(service, "stream_agent_events", _explicit_agent_runner(first_agent))
    create_resp = test_client.post(
        "/api/chat/stream",
        json={"message": "旧问题"},
        headers=headers,
    )
    assert create_resp.status_code == HTTPStatus.OK, create_resp.text
    create_done = _parse_sse(create_resp.text)[-1]["data"]
    session_id = create_done["session"]["id"]

    detail_resp = test_client.get(f"/api/chat/sessions/{session_id}", headers=headers)
    old_user_id = detail_resp.json()["messages"][0]["id"]

    async def edited_agent(messages, *, user_id: str):
        assert "新问题" in messages
        assert "旧回复" not in messages
        yield SimpleNamespace(event="RunContent", content="新回复")

    monkeypatch.setattr(service, "stream_agent_events", _explicit_agent_runner(edited_agent))
    edit_resp = test_client.post(
        f"/api/chat/messages/{old_user_id}/edit-stream",
        json={"message": "新问题"},
        headers=headers,
    )
    assert edit_resp.status_code == HTTPStatus.OK, edit_resp.text
    edit_events = _parse_sse(edit_resp.text)
    assert "branch_reset" in [event["event"] for event in edit_events]

    detail_after_edit_resp = test_client.get(
        f"/api/chat/sessions/{session_id}", headers=headers
    )
    assert detail_after_edit_resp.status_code == HTTPStatus.OK, detail_after_edit_resp.text
    active_messages = detail_after_edit_resp.json()["messages"]
    assert [message["content"] for message in active_messages] == ["新问题", "新回复"]
    assert active_messages[0]["source_message_id"] == old_user_id
    assert active_messages[0]["version_index"] == 2
    assert active_messages[0]["version_count"] == 2
    assert active_messages[0]["previous_version_message_id"] == old_user_id
    assert test_db_session.query(ChatMessage).filter(ChatMessage.session_id == session_id).count() == 4

    switch_resp = test_client.post(
        f"/api/chat/messages/{active_messages[0]['id']}/versions/{old_user_id}/activate",
        headers=headers,
    )
    assert switch_resp.status_code == HTTPStatus.OK, switch_resp.text
    switched_messages = switch_resp.json()["messages"]
    assert [message["content"] for message in switched_messages] == ["旧问题", "旧回复"]
    assert switched_messages[0]["next_version_message_id"] == active_messages[0]["id"]


def test_regenerate_replaces_latest_assistant_branch(
    test_client, test_db_session, init_test_database, monkeypatch
):
    headers = _login_admin(test_client)

    async def first_agent(messages, *, user_id: str):
        yield SimpleNamespace(event="RunContent", content="第一次回复")

    monkeypatch.setattr(service, "stream_agent_events", _explicit_agent_runner(first_agent))
    create_resp = test_client.post(
        "/api/chat/stream",
        json={"message": "请回答"},
        headers=headers,
    )
    assert create_resp.status_code == HTTPStatus.OK, create_resp.text
    create_done = _parse_sse(create_resp.text)[-1]["data"]
    session_id = create_done["session"]["id"]
    old_assistant_id = create_done["message"]["id"]

    async def regenerated_agent(messages, *, user_id: str):
        assert "请回答" in messages
        assert "第一次回复" not in messages
        yield SimpleNamespace(event="RunContent", content="第二次回复")

    monkeypatch.setattr(service, "stream_agent_events", _explicit_agent_runner(regenerated_agent))
    regenerate_resp = test_client.post(
        f"/api/chat/sessions/{session_id}/regenerate-stream",
        headers=headers,
    )
    assert regenerate_resp.status_code == HTTPStatus.OK, regenerate_resp.text
    regenerate_events = _parse_sse(regenerate_resp.text)
    assert regenerate_events[1]["event"] == "branch_reset"

    detail_resp = test_client.get(f"/api/chat/sessions/{session_id}", headers=headers)
    active_messages = detail_resp.json()["messages"]
    assert [message["content"] for message in active_messages] == ["请回答", "第二次回复"]
    assert active_messages[1]["source_message_id"] == old_assistant_id
    assert active_messages[1]["version_index"] == 2
    assert active_messages[1]["version_count"] == 2
    assert active_messages[1]["previous_version_message_id"] == old_assistant_id
    assert test_db_session.query(ChatMessage).filter(ChatMessage.session_id == session_id).count() == 3

    switch_resp = test_client.post(
        f"/api/chat/messages/{active_messages[1]['id']}/versions/{old_assistant_id}/activate",
        headers=headers,
    )
    assert switch_resp.status_code == HTTPStatus.OK, switch_resp.text
    switched_messages = switch_resp.json()["messages"]
    assert [message["content"] for message in switched_messages] == ["请回答", "第一次回复"]
    assert switched_messages[1]["next_version_message_id"] == active_messages[1]["id"]


def test_create_share_publicly_previews_immutable_snapshot(
    test_client, test_db_session, init_test_database, monkeypatch
):
    headers = _login_admin(test_client)

    async def first_agent(messages, *, user_id: str):
        yield SimpleNamespace(event="RunContent", content="第一次回复")

    monkeypatch.setattr(service, "stream_agent_events", _explicit_agent_runner(first_agent))
    create_resp = test_client.post(
        "/api/chat/stream",
        json={"message": "分享这个会话"},
        headers=headers,
    )
    assert create_resp.status_code == HTTPStatus.OK, create_resp.text
    create_done = _parse_sse(create_resp.text)[-1]["data"]
    session_id = create_done["session"]["id"]
    first_assistant_id = create_done["message"]["id"]

    share_resp = test_client.post(f"/api/chat/sessions/{session_id}/shares", headers=headers)
    assert share_resp.status_code == HTTPStatus.OK, share_resp.text
    share = share_resp.json()
    assert share["token"]
    assert "." in share["token"]
    assert len(share["token"].split(".", 1)[1]) == 16
    assert share["share_url"].endswith(f"/shared/chat/{share['token']}")
    assert share["message_count"] == 2

    duplicate_share_resp = test_client.post(
        f"/api/chat/sessions/{session_id}/shares", headers=headers
    )
    assert duplicate_share_resp.status_code == HTTPStatus.OK, duplicate_share_resp.text
    duplicate_share = duplicate_share_resp.json()
    assert duplicate_share["token"] == share["token"]
    assert duplicate_share["share_url"] == share["share_url"]
    assert test_db_session.query(ChatSessionShare).count() == 1

    preview_resp = test_client.get(f"/api/chat/shares/{share['token']}")
    assert preview_resp.status_code == HTTPStatus.OK, preview_resp.text
    preview = preview_resp.json()
    assert preview["title"] == "分享这个会话"
    assert [message["content"] for message in preview["messages"]] == [
        "分享这个会话",
        "第一次回复",
    ]

    async def second_agent(messages, *, user_id: str):
        yield SimpleNamespace(event="RunContent", content="第二次回复")

    monkeypatch.setattr(service, "stream_agent_events", _explicit_agent_runner(second_agent))
    regenerate_resp = test_client.post(
        f"/api/chat/sessions/{session_id}/regenerate-stream",
        headers=headers,
    )
    assert regenerate_resp.status_code == HTTPStatus.OK, regenerate_resp.text
    second_assistant_id = _parse_sse(regenerate_resp.text)[-1]["data"]["message"]["id"]

    immutable_preview_resp = test_client.get(f"/api/chat/shares/{share['token']}")
    assert immutable_preview_resp.status_code == HTTPStatus.OK, immutable_preview_resp.text
    immutable_preview = immutable_preview_resp.json()
    assert [message["content"] for message in immutable_preview["messages"]] == [
        "分享这个会话",
        "第一次回复",
    ]
    assert test_db_session.query(ChatSessionShare).count() == 1

    changed_share_resp = test_client.post(
        f"/api/chat/sessions/{session_id}/shares", headers=headers
    )
    assert changed_share_resp.status_code == HTTPStatus.OK, changed_share_resp.text
    changed_share = changed_share_resp.json()
    assert changed_share["token"] != share["token"]
    assert changed_share["message_count"] == 2
    assert test_db_session.query(ChatSessionShare).count() == 2

    changed_preview_resp = test_client.get(f"/api/chat/shares/{changed_share['token']}")
    assert changed_preview_resp.status_code == HTTPStatus.OK, changed_preview_resp.text
    changed_preview = changed_preview_resp.json()
    assert [message["content"] for message in changed_preview["messages"]] == [
        "分享这个会话",
        "第二次回复",
    ]

    switch_old_resp = test_client.post(
        f"/api/chat/messages/{second_assistant_id}/versions/{first_assistant_id}/activate",
        headers=headers,
    )
    assert switch_old_resp.status_code == HTTPStatus.OK, switch_old_resp.text
    old_share_resp = test_client.post(
        f"/api/chat/sessions/{session_id}/shares", headers=headers
    )
    assert old_share_resp.status_code == HTTPStatus.OK, old_share_resp.text
    old_share = old_share_resp.json()
    assert old_share["token"] == share["token"]
    assert test_db_session.query(ChatSessionShare).count() == 2

    delete_resp = test_client.delete(f"/api/chat/sessions/{session_id}", headers=headers)
    assert delete_resp.status_code == HTTPStatus.NO_CONTENT, delete_resp.text
    invalidated_preview_resp = test_client.get(f"/api/chat/shares/{share['token']}")
    assert invalidated_preview_resp.status_code == HTTPStatus.NOT_FOUND


def test_shared_session_rejects_tampered_signature(
    test_client, init_test_database, monkeypatch
):
    headers = _login_admin(test_client)

    async def fake_agent(messages, *, user_id: str):
        yield SimpleNamespace(event="RunContent", content="回复")

    monkeypatch.setattr(service, "stream_agent_events", _explicit_agent_runner(fake_agent))
    create_resp = test_client.post(
        "/api/chat/stream",
        json={"message": "签名测试"},
        headers=headers,
    )
    assert create_resp.status_code == HTTPStatus.OK, create_resp.text
    session_id = _parse_sse(create_resp.text)[-1]["data"]["session"]["id"]
    share_resp = test_client.post(f"/api/chat/sessions/{session_id}/shares", headers=headers)
    assert share_resp.status_code == HTTPStatus.OK, share_resp.text

    share_id_segment, signature = share_resp.json()["token"].split(".", 1)
    replacement = "A" if signature[-1] != "A" else "B"
    tampered_token = f"{share_id_segment}.{signature[:-1]}{replacement}"
    tampered_resp = test_client.get(f"/api/chat/shares/{tampered_token}")
    assert tampered_resp.status_code == HTTPStatus.NOT_FOUND


def test_share_requires_session_owner(
    test_client, test_db_session, init_test_database, monkeypatch
):
    headers = _login_admin(test_client)

    async def fake_agent(messages, *, user_id: str):
        yield SimpleNamespace(event="RunContent", content="回复")

    monkeypatch.setattr(service, "stream_agent_events", _explicit_agent_runner(fake_agent))
    create_resp = test_client.post(
        "/api/chat/stream",
        json={"message": "私有会话"},
        headers=headers,
    )
    assert create_resp.status_code == HTTPStatus.OK, create_resp.text
    session_id = _parse_sse(create_resp.text)[-1]["data"]["session"]["id"]

    user = User(username="member", email="member@example.com", name="普通用户")
    user.set_password("member123")
    test_db_session.add(user)
    test_db_session.commit()
    member_login_resp = test_client.post(
        "/api/auth/login",
        json={"username": "member", "password": "member123"},
    )
    assert member_login_resp.status_code == HTTPStatus.OK, member_login_resp.text
    member_headers = {
        "Authorization": f"Bearer {member_login_resp.json()['access_token']}",
    }

    forbidden_resp = test_client.post(
        f"/api/chat/sessions/{session_id}/shares",
        headers=member_headers,
    )
    assert forbidden_resp.status_code == HTTPStatus.NOT_FOUND


def test_shared_session_rejects_invalid_token(test_client, init_test_database):
    resp = test_client.get("/api/chat/shares/not-a-valid-token")
    assert resp.status_code == HTTPStatus.NOT_FOUND


def test_chat_requires_authentication(test_client):
    resp = test_client.get("/api/chat/sessions")
    assert resp.status_code == HTTPStatus.UNAUTHORIZED

    stream_resp = test_client.post(
        "/api/chat/stream",
        json={"message": "hello"},
    )
    assert stream_resp.status_code == HTTPStatus.UNAUTHORIZED


def test_chat_requires_llm_invoke_scope(test_client, test_db_session):
    user = User(
        username="chat_scope_member",
        email="chat_scope_member@example.com",
        scope_overrides=auth_service.serialize_scopes([auth_service.SCOPE_PROFILE_READ]),
    )
    user.set_password("Password123")
    test_db_session.add(user)
    test_db_session.commit()

    token = auth_service.create_access_token(
        {"sub": user.username, "scope": auth_service.get_user_scopes(user)}
    )
    resp = test_client.get(
        "/api/chat/sessions",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == HTTPStatus.FORBIDDEN
    assert resp.json()["detail"]["required_scopes"] == [
        auth_service.SCOPE_CHAT_LLM_INVOKE
    ]
