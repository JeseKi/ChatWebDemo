# -*- coding: utf-8 -*-

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from types import SimpleNamespace

from sqlalchemy.orm import Session

from src.server.auth.models import User
from src.server.chat import service as chat_service
from src.server.chat.dao import ChatDAO
from src.server.token_audit import service
from src.server.token_audit.models import TokenUsageAudit


def _login_admin(test_client):
    resp = test_client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert resp.status_code == HTTPStatus.OK, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_chat_run_persists_usage_events(
    test_db_session: Session,
    init_test_database,
    monkeypatch,
):
    current_user = test_db_session.query(User).filter(User.username == "admin").one()

    async def fake_stream_agent_events(messages, *, model_config, thinking_effort, user_id):
        yield SimpleNamespace(
            event="RunUsage",
            usage=SimpleNamespace(
                provider="openai_chat",
                model_id="test-model",
                input_tokens=10,
                output_tokens=5,
                total_tokens=15,
                reasoning_tokens=2,
                cached_input_tokens=1,
                tool_tokens=None,
                raw_usage={"prompt_tokens": 10, "completion_tokens": 5},
            ),
        )
        yield SimpleNamespace(event="RunContent", content="ok")

    monkeypatch.setattr(chat_service, "stream_agent_events", fake_stream_agent_events)

    async def exercise():
        return [
            event
            async for event in chat_service.stream_chat(
                test_db_session,
                current_user=current_user,
                message="hello",
                session_id=None,
                model_id="test-model",
                thinking_effort="low",
            )
        ]

    events = asyncio.run(exercise())

    assert any("event: done" in event for event in events)
    audits = test_db_session.query(TokenUsageAudit).all()
    assert len(audits) == 1
    assert audits[0].user_id == current_user.id
    assert audits[0].provider == "openai_chat"
    assert audits[0].input_tokens == 10
    assert audits[0].output_tokens == 5
    assert audits[0].total_tokens == 15
    assert audits[0].reasoning_tokens == 2
    assert audits[0].request_index == 1


def test_admin_token_audit_summary_and_events(test_client, test_db_session, init_test_database):
    admin = test_db_session.query(User).filter(User.username == "admin").one()
    dao = ChatDAO(test_db_session)
    session = dao.create_session(user_id=admin.id, title="audit")
    service.create_usage_audit(
        test_db_session,
        user_id=admin.id,
        session_id=session.id,
        run_id="R" * 32,
        request_index=1,
        provider="openai_responses",
        model_id="gpt-test",
        input_tokens=20,
        output_tokens=10,
        total_tokens=30,
        reasoning_tokens=4,
        cached_input_tokens=3,
        tool_tokens=0,
        raw_usage={"input_tokens": 20, "output_tokens": 10},
    )
    service.create_usage_audit(
        test_db_session,
        user_id=admin.id,
        session_id=session.id,
        run_id="S" * 32,
        request_index=1,
        provider="google",
        model_id="gemini-test",
        input_tokens=7,
        output_tokens=3,
        total_tokens=11,
        reasoning_tokens=1,
        cached_input_tokens=0,
        tool_tokens=0,
        raw_usage={"totalTokenCount": 11},
    )

    headers = _login_admin(test_client)

    summary_resp = test_client.get(
        "/api/admin/token-audit/summary",
        params={"provider": "openai_responses"},
        headers=headers,
    )
    assert summary_resp.status_code == HTTPStatus.OK, summary_resp.text
    assert summary_resp.json()[0]["total_tokens"] == 30
    assert summary_resp.json()[0]["request_count"] == 1

    events_resp = test_client.get(
        "/api/admin/token-audit/events",
        params={"limit": 1, "offset": 0},
        headers=headers,
    )
    assert events_resp.status_code == HTTPStatus.OK, events_resp.text
    payload = events_resp.json()
    assert payload["total"] == 2
    assert len(payload["items"]) == 1
    assert payload["items"][0]["username"] == "admin"


def test_admin_token_audit_timeseries_and_breakdown(
    test_client, test_db_session, init_test_database
):
    admin = test_db_session.query(User).filter(User.username == "admin").one()
    member = User(username="auditmember", email="auditmember@example.com", name="审计成员")
    member.set_password("Password123")
    test_db_session.add(member)
    test_db_session.commit()

    base_time = datetime(2026, 1, 2, 8, 30, tzinfo=timezone.utc)

    first = service.create_usage_audit(
        test_db_session,
        user_id=admin.id,
        session_id="A" * 32,
        run_id="T" * 32,
        request_index=1,
        provider="openai_chat",
        model_id="gpt-test",
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        reasoning_tokens=2,
        cached_input_tokens=1,
        tool_tokens=0,
        raw_usage=None,
    )
    second = service.create_usage_audit(
        test_db_session,
        user_id=member.id,
        session_id="B" * 32,
        run_id="U" * 32,
        request_index=1,
        provider="google",
        model_id="gemini-test",
        input_tokens=30,
        output_tokens=10,
        total_tokens=42,
        reasoning_tokens=1,
        cached_input_tokens=3,
        tool_tokens=2,
        raw_usage=None,
    )
    first.created_at = base_time
    second.created_at = base_time + timedelta(hours=2)
    test_db_session.commit()

    headers = _login_admin(test_client)
    timeseries_resp = test_client.get(
        "/api/admin/token-audit/timeseries",
        params={"group_by": "hour"},
        headers=headers,
    )
    assert timeseries_resp.status_code == HTTPStatus.OK, timeseries_resp.text
    points = timeseries_resp.json()
    assert [point["total_tokens"] for point in points] == [15, 42]
    assert points[0]["request_count"] == 1

    provider_resp = test_client.get(
        "/api/admin/token-audit/breakdown",
        params={"dimension": "provider"},
        headers=headers,
    )
    assert provider_resp.status_code == HTTPStatus.OK, provider_resp.text
    providers = provider_resp.json()
    assert providers[0]["key"] == "google"
    assert providers[0]["tool_tokens"] == 2

    user_resp = test_client.get(
        "/api/admin/token-audit/breakdown",
        params={"dimension": "user", "limit": 1},
        headers=headers,
    )
    assert user_resp.status_code == HTTPStatus.OK, user_resp.text
    users = user_resp.json()
    assert users[0]["username"] == "auditmember"
    assert users[0]["email"] == "auditmember@example.com"


def test_admin_token_audit_requires_admin(test_client, test_db_session, init_test_database):
    member = User(username="member", email="member@example.com", name="Member")
    member.set_password("Password123")
    test_db_session.add(member)
    test_db_session.commit()

    login_resp = test_client.post(
        "/api/auth/login",
        json={"username": "member", "password": "Password123"},
    )
    assert login_resp.status_code == HTTPStatus.OK, login_resp.text

    resp = test_client.get(
        "/api/admin/token-audit/summary",
        headers={"Authorization": f"Bearer {login_resp.json()['access_token']}"},
    )

    assert resp.status_code == HTTPStatus.FORBIDDEN
