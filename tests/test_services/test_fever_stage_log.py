"""Checkpoint 0 (_guidance/fever-detect-agent-task.md §5.6) — trace log của agent fever.

Mô phỏng 1 lượt hội thoại Stage 3A đầy đủ 10 step theo bảng §5.2, cộng 1 lần `stage_enter` ở Stage 0
để có 2 file stage khác nhau, rồi kiểm cấu trúc/nội dung/an toàn của module log.
"""

from __future__ import annotations

import json

import pytest

from src import paths
from src.services.infra import fever_stage_log


@pytest.fixture(autouse=True)
def _isolated_log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LOGS_DIR", tmp_path)
    monkeypatch.delenv("FEVER_LOG_REDACT", raising=False)
    yield


def _simulate_full_turn(session_id: str, *, user_text: str = "bé co giật từ nãy tới giờ chưa dứt") -> None:
    """Ghi đủ 10 step của 1 lượt Stage 3A (hướng C) đúng thứ tự §5.2, cộng 1 lần stage_enter ở stage 0."""
    fever_stage_log.start(session_id, route="ROUTE_HIGH_RISK", budget=6)
    fever_stage_log.stage_enter(session_id, "0")

    turn = 1
    stage = "3A"
    cluster_id = "Q3-06"

    fever_stage_log.step(
        session_id, turn=turn, stage=stage, cluster_id=cluster_id, event="user_message",
        step=1, input=None, output={"text": user_text},
    )
    fever_stage_log.step(
        session_id, turn=turn, stage=stage, cluster_id=cluster_id, event="retrieve",
        step=2, input={"cluster_id": cluster_id}, output={"fields": ["seizure_active_now"], "schema_size": 1},
    )
    fever_stage_log.llm_io(
        session_id, turn=turn, stage=stage, cluster_id=cluster_id, purpose="extract",
        provider="openrouter", model="openai/gpt-4o-mini",
        messages=[{"role": "user", "content": user_text}],
        response_text='{"seizure_active_now": "true"}',
        parsed={"seizure_active_now": "true"}, tokens=42, latency_ms=350,
    )
    fever_stage_log.step(
        session_id, turn=turn, stage=stage, cluster_id=cluster_id, event="extract",
        step=5, input=None, output={"seizure_active_now": "true"},
        answers_delta={"seizure_active_now": "unknown -> true"},
    )
    with fever_stage_log.tool(
        session_id, turn=turn, stage=stage, cluster_id=cluster_id,
        tool="red_flag_engine.evaluate", input={"seizure_active_now": "true"},
    ) as rec:
        rec.output = {"triggered_rules": ["R-E-03"], "reason_codes": ["RF-11"], "triage_level": "EMERGENCY"}
    fever_stage_log.step(
        session_id, turn=turn, stage=stage, cluster_id=cluster_id, event="rule_gate",
        step=7, input=None, output={"triage_level": "EMERGENCY"}, stop_reason="RED_FLAG",
    )
    fever_stage_log.step(
        session_id, turn=turn, stage=stage, cluster_id=cluster_id, event="agent_message",
        step=10, input=None, output={"text": "Gọi cấp cứu ngay."}, llm_used=False,
    )
    fever_stage_log.finish(session_id, triage_level="EMERGENCY", stop_reason="RED_FLAG", turns=turn)


# --- cấu trúc thư mục/file ------------------------------------------------------------------


def test_creates_one_file_per_stage_touched():
    session_id = "sess-structure"
    _simulate_full_turn(session_id)

    directory = fever_stage_log.session_dir(session_id)
    stage_files = sorted(p.name for p in directory.glob("stage-*.jsonl"))
    assert stage_files == ["stage-0.jsonl", "stage-3A.jsonl"]
    assert (directory / "llm-io.jsonl").exists()
    assert (directory / "rule-engine.jsonl").exists()
    assert (directory / "session.json").exists()


def test_read_turn_returns_all_steps_in_order():
    session_id = "sess-turn"
    _simulate_full_turn(session_id)

    records = fever_stage_log.read_turn(session_id, 1)
    events = [r["event"] for r in records]
    assert events == [
        "user_message",
        "retrieve",
        "llm_request",
        "llm_response",
        "extract",
        "tool_call",
        "rule_gate",
        "agent_message",
    ]
    seqs = [r["seq"] for r in records]
    assert seqs == sorted(seqs)


# --- input/output đầy đủ ----------------------------------------------------------------------


def test_tool_call_and_retrieve_rows_always_have_input_and_output():
    session_id = "sess-io"
    _simulate_full_turn(session_id)

    records = fever_stage_log.read_all(session_id)
    for record in records:
        if record["event"] in ("tool_call", "retrieve"):
            assert record["input"] is not None, record
            assert record["output"] is not None, record


def test_llm_request_has_input_only_llm_response_has_output_only():
    session_id = "sess-llm-io-shape"
    _simulate_full_turn(session_id)

    records = fever_stage_log.read_all(session_id)
    request = next(r for r in records if r["event"] == "llm_request")
    response = next(r for r in records if r["event"] == "llm_response")
    assert request["input"] is not None
    assert request["output"] is None
    assert response["output"] is not None
    assert response["input"] is None


# --- enum tool ---------------------------------------------------------------------------------


def test_tool_name_must_be_known():
    with pytest.raises(ValueError):
        fever_stage_log.step(
            "sess-bad-tool", turn=1, stage="3A", cluster_id="Q3-06", event="tool_call",
            tool="totally_made_up_tool",  # type: ignore[arg-type]
            input={}, output={},
        )


def test_event_name_must_be_known():
    with pytest.raises(ValueError):
        fever_stage_log.step(
            "sess-bad-event", turn=1, stage="3A", cluster_id="Q3-06",
            event="not_a_real_event",  # type: ignore[arg-type]
        )


def test_all_tool_calls_use_declared_tool_names():
    session_id = "sess-tool-enum"
    _simulate_full_turn(session_id)

    records = fever_stage_log.read_all(session_id)
    tool_calls = [r for r in records if r["event"] == "tool_call"]
    assert tool_calls
    for record in tool_calls:
        assert record["tool"] in fever_stage_log.TOOL_NAMES


# --- io_ref --------------------------------------------------------------------------------


def test_llm_response_io_ref_points_to_existing_llm_io_row():
    session_id = "sess-io-ref"
    _simulate_full_turn(session_id)

    response = next(r for r in fever_stage_log.read_all(session_id) if r["event"] == "llm_response")
    io_ref = response["io_ref"]
    assert io_ref

    io_rows = fever_stage_log.read_llm_io(session_id)
    matched = [row for row in io_rows if row["io_ref"] == io_ref]
    assert len(matched) == 1
    assert matched[0]["messages"] == [{"role": "user", "content": "bé co giật từ nãy tới giờ chưa dứt"}]
    assert matched[0]["response_text"] == '{"seizure_active_now": "true"}'


# --- redact ----------------------------------------------------------------------------------


def test_redact_env_var_strips_verbatim_text(monkeypatch):
    monkeypatch.setenv("FEVER_LOG_REDACT", "1")
    session_id = "sess-redact"
    secret = "bé co giật từ nãy tới giờ chưa dứt, tên bé là Nguyễn Văn A"
    _simulate_full_turn(session_id, user_text=secret)

    directory = fever_stage_log.session_dir(session_id)
    for path in directory.glob("*.jsonl"):
        raw = path.read_text(encoding="utf-8")
        assert secret not in raw

    io_rows = fever_stage_log.read_llm_io(session_id)
    assert all(secret not in json.dumps(row, ensure_ascii=False) for row in io_rows)


# --- an toàn I/O -------------------------------------------------------------------------------


def test_step_never_raises_when_disk_write_fails(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(fever_stage_log.Path, "open", _boom)

    # Không được ném ra ngoài dù ghi file thất bại hoàn toàn.
    fever_stage_log.step(
        "sess-io-fail", turn=1, stage="3A", cluster_id="Q3-06", event="user_message",
        input=None, output={"text": "..."},
    )
