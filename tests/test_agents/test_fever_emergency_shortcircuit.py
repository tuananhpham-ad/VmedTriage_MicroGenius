"""Checkpoint 5 (_guidance/fever-detect-agent-task.md Bước 5) — ghép hướng C/E theo stage,
short-circuit EMERGENCY.

Ca dùng: E2 Part 8 (co giật đang diễn ra) - input user nguyên văn từ tài liệu. Test đếm chính xác số
lần `provider_router.complete` được gọi trong lượt chốt đỏ (đo hành vi) VÀ đọc log để xác nhận thứ tự
`rule_gate` nằm giữa `extract`/`llm_response` và không có `llm_request(next_question)` nào sau đó
(đo trace) - hai phép đo độc lập, phải xanh cả hai mới coi là short-circuit đúng.
"""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from src import paths
from src.services.agents import fever_intake_agent as agent
from src.services.checklists.fever_checklist import CLUSTERS_BY_ID
from src.services.engines import fever_stage_machine as fsm
from src.services.infra import fever_stage_log, provider_router

E2_USER_MESSAGE = "Con em đang sốt cao, giờ tay chân đang giật, mắt trợn lên, em không biết làm sao."


@pytest.fixture(autouse=True)
def _isolated_log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LOGS_DIR", tmp_path)
    yield


def _fake_complete(response_json: dict):
    return Mock(
        return_value=provider_router.CompletionResult(
            text=json.dumps(response_json), provider="openrouter", model="openai/gpt-4o-mini"
        )
    )


# --- đếm call: đúng 1 lần (chỉ extract) ở lượt chốt đỏ -------------------------------------------


def test_emergency_turn_calls_provider_exactly_once(monkeypatch):
    fake = _fake_complete({"seizure_occurred": "true", "seizure_active_now": "true"})
    monkeypatch.setattr(provider_router, "complete", fake)

    session_id = "e2-shortcircuit"
    fever_stage_log.start(session_id, route="ROUTE_STANDARD", budget=6)
    cluster = CLUSTERS_BY_ID["Q3-03"]  # seizure_occurred, seizure_active_now, seizure_features

    result = agent.run_turn(session_id, turn=1, stage="3A", cluster=cluster, message=E2_USER_MESSAGE, answers={})

    assert fake.call_count == 1
    assert result.emergency is True
    assert result.triage_level == "EMERGENCY"
    assert "R-E-02" in result.triggered_rules


def test_emergency_response_has_no_question_mark_and_no_disease_name(monkeypatch):
    fake = _fake_complete({"seizure_occurred": "true", "seizure_active_now": "true"})
    monkeypatch.setattr(provider_router, "complete", fake)

    session_id = "e2-content"
    fever_stage_log.start(session_id, route="ROUTE_STANDARD", budget=6)
    cluster = CLUSTERS_BY_ID["Q3-03"]

    result = agent.run_turn(session_id, turn=1, stage="3A", cluster=cluster, message=E2_USER_MESSAGE, answers={})

    assert "?" not in result.agent_message
    for disease_word in ("sốt xuất huyết", "viêm màng não", "nhiễm khuẩn huyết", "sốt rét"):
        assert disease_word not in result.agent_message.casefold()


# --- hướng E vẫn đúng 1 call nhưng có cả extracted lẫn next_question -----------------------------


def test_non_gate_stage_still_uses_single_combined_call(monkeypatch):
    fake = _fake_complete({"extracted": {"fever_reported": "true"}, "next_question": "Bé sốt được mấy ngày rồi ạ?"})
    monkeypatch.setattr(provider_router, "complete", fake)

    session_id = "self-care-stage1"
    fever_stage_log.start(session_id, route="ROUTE_STANDARD", budget=16)
    cluster = CLUSTERS_BY_ID["Q1-01"]
    next_cluster = fsm.next_cluster("1", {"fever_reported": "true"}, asked_ids=frozenset({"Q1-01"}))

    result = agent.run_turn(
        session_id, turn=1, stage="1", cluster=cluster, message="Dạ bé đang sốt ạ",
        answers={}, next_cluster=next_cluster,
    )

    assert fake.call_count == 1
    assert result.emergency is False
    assert result.extracted == {"fever_reported": "true"}
    assert result.agent_message == "Bé sốt được mấy ngày rồi ạ?"


# --- thứ tự tool trong log: rule_gate SAU extract, TRƯỚC mọi llm_request khác --------------------


def test_rule_gate_sits_between_extract_and_next_question_request(monkeypatch):
    fake = _fake_complete({"seizure_occurred": "true", "seizure_active_now": "true"})
    monkeypatch.setattr(provider_router, "complete", fake)

    session_id = "e2-log-order"
    fever_stage_log.start(session_id, route="ROUTE_STANDARD", budget=6)
    cluster = CLUSTERS_BY_ID["Q3-03"]
    agent.run_turn(session_id, turn=1, stage="3A", cluster=cluster, message=E2_USER_MESSAGE, answers={})

    records = fever_stage_log.read_turn(session_id, 1)
    events = [r["event"] for r in records]

    assert "rule_gate" in events
    extract_index = events.index("extract")
    rule_gate_index = events.index("rule_gate")
    assert extract_index < rule_gate_index

    # Không có llm_request nào với purpose next_question SAU rule_gate.
    llm_io_rows = fever_stage_log.read_llm_io(session_id)
    assert all(row["purpose"] != "next_question" for row in llm_io_rows)


def test_no_next_cluster_tool_call_logged_when_emergency(monkeypatch):
    fake = _fake_complete({"seizure_occurred": "true", "seizure_active_now": "true"})
    monkeypatch.setattr(provider_router, "complete", fake)

    session_id = "e2-no-next-cluster-call"
    fever_stage_log.start(session_id, route="ROUTE_STANDARD", budget=6)
    cluster = CLUSTERS_BY_ID["Q3-03"]
    agent.run_turn(session_id, turn=1, stage="3A", cluster=cluster, message=E2_USER_MESSAGE, answers={})

    records = fever_stage_log.read_turn(session_id, 1)
    next_cluster_calls = [
        r for r in records if r["event"] == "tool_call" and r["tool"] == "fever_stage_machine.next_cluster"
    ]
    assert next_cluster_calls == []


def test_session_marked_stopped_with_red_flag_reason(monkeypatch):
    fake = _fake_complete({"seizure_occurred": "true", "seizure_active_now": "true"})
    monkeypatch.setattr(provider_router, "complete", fake)

    session_id = "e2-session-stop"
    fever_stage_log.start(session_id, route="ROUTE_STANDARD", budget=6)
    cluster = CLUSTERS_BY_ID["Q3-03"]
    result = agent.run_turn(session_id, turn=1, stage="3A", cluster=cluster, message=E2_USER_MESSAGE, answers={})
    fever_stage_log.finish(session_id, triage_level=result.triage_level, stop_reason="RED_FLAG", turns=1)

    records = fever_stage_log.read_turn(session_id, 1)
    assert records[-1]["event"] == "stop"
    assert records[-1]["stop_reason"] == "RED_FLAG"

    session_snapshot = fever_stage_log.read_session(session_id)
    assert session_snapshot["stop_reason"] == "RED_FLAG"
    assert session_snapshot["triage_level"] == "EMERGENCY"
