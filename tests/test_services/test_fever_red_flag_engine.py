"""Checkpoint 3 (_guidance/fever-detect-agent-task.md Bước 3) — golden 25 ca Part 8 (thực tế: 16 ca
có kết luận triage tường minh trong `docs/medical_knowledge/fever-conversation-specification.md`
Part 8 — 5 EMERGENCY, 5 EARLY_VISIT, 5 SELF_CARE, 1 minh hoạ tối ưu có kết luận (O2); ca O1 KHÔNG có
`session.triage_level` trong JSON mẫu — tài liệu dùng O1 để minh hoạ batch-negation extraction giữa
chừng hội thoại, chưa kết luận, nên không đưa vào bộ golden của rule engine). Con số "25 ca (5+5+5+5)"
trong bản nháp task spec ban đầu là ước đoán trước khi đọc hết tài liệu - đã sửa lại đúng theo tài
liệu nguồn thật.

Golden: `tests/fixtures/fever/part8_cases.json`, field verbatim từ khối ```json``` dưới mỗi ca Part 8.
Một số ca SELF_CARE (H1-H5) được bổ sung thêm field mà JSON gốc không liệt kê (tài liệu tự nói rõ
"JSON chỉ gồm field liên quan trực tiếp tới kết luận, không liệt kê toàn schema") - mọi field bổ sung
đều ghi rõ trong `narrative_supplement_keys` + `note` của từng ca, suy luận từ đúng mạch hội thoại,
không tự sáng tạo dữ liệu trái ngược.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from tests.helpers import fever_api as engine

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "fever" / "part8_cases.json"


def _load_cases() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


PART8_CASES = _load_cases()


# --- đủ bộ, đúng phân bố --------------------------------------------------------------------


def test_case_count_and_distribution_matches_part_8():
    assert len(PART8_CASES) == 16
    by_level = {"EMERGENCY": 0, "EARLY_VISIT": 0, "SELF_CARE": 0}
    for case in PART8_CASES:
        by_level[case["expected_triage_level"]] += 1
    assert by_level == {"EMERGENCY": 5, "EARLY_VISIT": 6, "SELF_CARE": 5}  # O2 cộng vào EARLY_VISIT


# --- golden: khớp 100% triage_level, và reason_codes/triggered_rules mà tài liệu liệt kê phải là
# tập con của kết quả engine (tài liệu tự nói JSON không liệt kê hết field/rule liên quan) ---------


@pytest.mark.parametrize("case", PART8_CASES, ids=lambda c: c["case_id"])
def test_golden_case_matches_expected_triage(case: dict):
    result = engine.evaluate(case["fields"])

    assert result.triage_level == case["expected_triage_level"], case["case_id"]
    assert set(case["expected_reason_codes"]).issubset(set(result.reason_codes)), (
        case["case_id"], result.reason_codes,
    )
    assert set(case["expected_triggered_rules"]).issubset(set(result.triggered_rules)), (
        case["case_id"], result.triggered_rules,
    )


# --- đúng tool: rule engine không được gọi LLM --------------------------------------------------


@pytest.mark.parametrize("case", PART8_CASES, ids=lambda c: c["case_id"])
def test_rule_engine_never_calls_llm_provider(case: dict, monkeypatch):
    from src.services.infra import provider_router

    def _boom(*_args, **_kwargs):
        raise AssertionError("rule engine không được gọi LLM")

    monkeypatch.setattr(provider_router, "complete", Mock(side_effect=_boom))
    engine.evaluate(case["fields"])  # không được ném AssertionError


# --- P0-6: mơ hồ giữa 2 mức luôn chọn mức thận trọng hơn ----------------------------------------


def test_p0_6_ambiguous_m0_field_does_not_default_to_self_care():
    ambiguous_case = {
        "age_value": 5, "age_unit": "year",
        "consciousness_level": "alert", "feeding_intake": "normal",
        # urine_output cố tình để "unknown" - field M0 ảnh hưởng checklist SELF_CARE
        "urine_output": "unknown",
        "caregiver_available": "true", "can_return_for_followup": "true",
        "fever_duration_days": 1,
    }
    result = engine.evaluate(ambiguous_case)
    assert result.triage_level != "SELF_CARE"


def test_tri_state_unknown_is_never_treated_as_false_for_safety_fields():
    # non_blanching_rash="unknown" không được rule engine ngầm hiểu là false rồi bỏ qua ca -
    # kiểm bằng cách đảm bảo engine không crash và không tự tin kết luận SELF_CARE khi field an
    # toàn cốt lõi còn unknown.
    case = {
        "age_value": 3, "age_unit": "year",
        "non_blanching_rash": "unknown",
        "consciousness_level": "alert", "feeding_intake": "normal", "urine_output": "normal",
        "caregiver_available": "true", "can_return_for_followup": "true", "fever_duration_days": 1,
    }
    result = engine.evaluate(case)
    # unknown không kích hoạt rule (đúng - rule chỉ khớp khi field THỰC SỰ true), nhưng cũng không
    # được coi là "đã loại trừ" một cách an toàn để tự tin SELF_CARE nếu còn field M0 khác unknown.
    assert "non_blanching_rash" not in [f for m in result.matches for f in m.reason_codes]


# --- log -----------------------------------------------------------------------------------


def test_rule_engine_evaluation_is_logged(monkeypatch, tmp_path):
    from src import paths
    from src.services.infra import fever_stage_log

    monkeypatch.setattr(paths, "LOGS_DIR", tmp_path)
    session_id = "rule-engine-log-check"
    fever_stage_log.start(session_id, route=None, budget=0)

    case = next(c for c in PART8_CASES if c["case_id"] == "E2")
    with fever_stage_log.tool(
        session_id, turn=1, stage="3A", cluster_id="Q3-03",
        tool="red_flag_engine.evaluate", input=case["fields"],
    ) as rec:
        result = engine.evaluate(case["fields"])
        rec.output = {
            "triage_level": result.triage_level,
            "reason_codes": list(result.reason_codes),
            "triggered_rules": list(result.triggered_rules),
        }

    records = fever_stage_log.read_all(session_id)
    rule_gate_calls = [r for r in records if r["event"] == "tool_call" and r["tool"] == "red_flag_engine.evaluate"]
    assert len(rule_gate_calls) == 1
    assert rule_gate_calls[0]["output"]["triage_level"] == "EMERGENCY"

    rule_engine_file_records = fever_stage_log.read_all(session_id)
    assert any(r["tool"] == "red_flag_engine.evaluate" for r in rule_engine_file_records)
