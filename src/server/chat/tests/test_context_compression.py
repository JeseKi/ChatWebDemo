# -*- coding: utf-8 -*-

from __future__ import annotations

import pytest

from src.server.auth.models import User
from src.server.chat.dao import ChatDAO
from src.server.chat.service import context_compression
from src.server.chat.service.model_catalog import get_model, replace_models_for_tests


@pytest.fixture
def small_model():
    replace_models_for_tests(
        [
            {
                "provider": "openai_chat",
                "id": "small-test-model",
                "name": "Small Test Model",
                "context": 220,
                "max_output": 20,
                "visual": True,
                "thinking": {"low": "低"},
                "keep_thinking_content": False,
            }
        ]
    )
    model = get_model("small-test-model")
    assert model is not None
    return model


@pytest.mark.asyncio
async def test_prepare_agent_context_creates_compression_and_keeps_tail(
    test_db_session,
    init_test_database,
    monkeypatch,
    small_model,
):
    dao = ChatDAO(test_db_session)
    user = test_db_session.query(User).filter(User.username == "admin").one()
    session, messages = _seed_three_turn_path(dao, user.id)

    async def fake_summarize_messages(**kwargs):
        assert kwargs["messages"] == messages[:2]
        return "## Objective\n- summary before tail"

    monkeypatch.setattr(context_compression, "summarize_messages", fake_summarize_messages)

    prepared = await context_compression.prepare_agent_context(
        dao,
        user_message=messages[-1],
        model_config=small_model,
        thinking_effort="low",
    )

    assert prepared.compression is not None
    assert prepared.compression.head_end_message_id == messages[1].id
    assert prepared.compression.tail_start_message_id == messages[2].id
    assert [event.type for event in prepared.events] == [
        "context_compaction_started",
        "context_compaction_done",
    ]
    assert "summary before tail" in str(prepared.messages)
    assert "first user" not in str(prepared.messages)
    assert messages[-1].content in str(prepared.messages)
    assert dao.get_session(session_id=session.id, user_id=user.id) is not None


def test_editing_covered_message_invalidates_old_compression(
    test_db_session,
    init_test_database,
):
    dao = ChatDAO(test_db_session)
    user = test_db_session.query(User).filter(User.username == "admin").one()
    session, messages = _seed_three_turn_path(dao, user.id)
    compression = dao.create_context_compression(
        session_id=session.id,
        user_id=user.id,
        head_end_message_id=messages[1].id,
        tail_start_message_id=messages[2].id,
        source_leaf_message_id=messages[-1].id,
        previous_compression_id=None,
        trigger="auto",
        summary="old summary",
        summary_model_id="small-test-model",
        original_token_estimate=180,
        summary_token_estimate=20,
        message_count=2,
    )

    edited = dao.append_message(
        session_id=session.id,
        user_id=user.id,
        role="user",
        content="edited first user",
        parent_message_id=None,
        source_message_id=messages[0].id,
        version_index=2,
    )
    path = dao.list_path_to_message(message=edited)

    assert compression.head_end_message_id not in {message.id for message in path}
    assert (
        context_compression.select_applicable_compression(
            dao,
            path=path,
            target_message=edited,
        )
        is None
    )


def test_regenerate_reuses_compression_before_target_user(
    test_db_session,
    init_test_database,
):
    dao = ChatDAO(test_db_session)
    user = test_db_session.query(User).filter(User.username == "admin").one()
    session, messages = _seed_three_turn_path(dao, user.id)
    compression = dao.create_context_compression(
        session_id=session.id,
        user_id=user.id,
        head_end_message_id=messages[1].id,
        tail_start_message_id=messages[2].id,
        source_leaf_message_id=messages[-1].id,
        previous_compression_id=None,
        trigger="auto",
        summary="old summary",
        summary_model_id="small-test-model",
        original_token_estimate=180,
        summary_token_estimate=20,
        message_count=2,
    )

    path = dao.list_path_to_message(message=messages[-1])

    selected = context_compression.select_applicable_compression(
        dao,
        path=path,
        target_message=messages[-1],
    )
    assert selected is not None
    assert selected.id == compression.id


def test_compression_trigger_uses_full_context_threshold(small_model):
    assert context_compression._compression_trigger_tokens(small_model) == 187
    assert context_compression._context_is_usable(
        context_compression.ContextEstimate(tokens=186),
        small_model,
    )
    assert not context_compression._context_is_usable(
        context_compression.ContextEstimate(tokens=187),
        small_model,
    )

    odd_context_model = small_model.model_copy(update={"context": 221})
    assert context_compression._compression_trigger_tokens(odd_context_model) == 188
    assert context_compression._context_is_usable(
        context_compression.ContextEstimate(tokens=187),
        odd_context_model,
    )
    assert not context_compression._context_is_usable(
        context_compression.ContextEstimate(tokens=188),
        odd_context_model,
    )


def _seed_three_turn_path(dao: ChatDAO, user_id: int):
    session = dao.create_session(user_id=user_id, title="compression test")
    u1 = dao.append_message(
        session_id=session.id,
        user_id=user_id,
        role="user",
        content="first user " * 80,
        parent_message_id=None,
    )
    a1 = dao.append_message(
        session_id=session.id,
        user_id=user_id,
        role="assistant",
        content="first assistant " * 80,
        parent_message_id=u1.id,
    )
    u2 = dao.append_message(
        session_id=session.id,
        user_id=user_id,
        role="user",
        content="second user",
        parent_message_id=a1.id,
    )
    a2 = dao.append_message(
        session_id=session.id,
        user_id=user_id,
        role="assistant",
        content="second assistant",
        parent_message_id=u2.id,
    )
    u3 = dao.append_message(
        session_id=session.id,
        user_id=user_id,
        role="user",
        content="third user",
        parent_message_id=a2.id,
    )
    return session, [u1, a1, u2, a2, u3]
