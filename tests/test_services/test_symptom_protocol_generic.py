"""Chứng minh engine chung (`src/services/symptom_protocol/`) THẬT SỰ dùng lại được cho bệnh khác,
không chỉ "trông có vẻ generic" trên giấy: định nghĩa một `SymptomProtocol` TỐI GIẢN cho một
symptom_group giả lập (không phải fever) - chỉ toàn DATA + vài hàm hook nhỏ, KHÔNG viết thêm dòng
thuật toán nào - rồi chạy qua đúng `stage_machine`/`rule_engine` dùng chung với fever.

Đây chính là bài kiểm chứng cho yêu cầu "kế thừa được" khi làm thêm bệnh thứ 2 trong tương lai.
"""

from __future__ import annotations

from src.services.symptom_protocol import rule_engine, stage_machine
from src.services.symptom_protocol.models import FieldSpec, QuestionCluster, RuleMatch
from src.services.symptom_protocol.protocol import SymptomProtocol

# --- "bệnh giả lập": đau ngực tối giản, chỉ 4 field, 3 cụm câu hỏi, 2 rule ----------------------

_FIELDS = {
    "age_value": FieldSpec("age_value", "Tuổi", "M0", "Số tuổi", tri_state=False),
    "age_unit": FieldSpec("age_unit", "Đơn vị tuổi", "M0", "year/month", tri_state=False),
    "chest_pain_severe": FieldSpec("chest_pain_severe", "Đau ngực dữ dội", "M0", "Đau ngực dữ dội đột ngột"),
    "resolved_with_rest": FieldSpec("resolved_with_rest", "Đỡ khi nghỉ", "O", "Có đỡ khi nghỉ ngơi không"),
}

_CLUSTERS = (
    QuestionCluster("T0-01", "0", ("age_value", "age_unit"), script_hint="Tuổi bao nhiêu"),
    QuestionCluster("T1-01", "1", ("chest_pain_severe",), script_hint="Có đau ngực dữ dội không"),
    QuestionCluster("T1-02", "1", ("resolved_with_rest",), script_hint="Có đỡ khi nghỉ không"),
)


def _toy_r_e_01(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if a.get("chest_pain_severe") == "true":
        return RuleMatch("T-E-01", ("TF-01",), "EMERGENCY", "now")
    return None


def _toy_fallback(_a: dict[str, object]) -> RuleMatch:
    return RuleMatch("T-G-01", (), "EARLY_VISIT", "within_24h")


def _toy_self_care_default(_a: dict[str, object]) -> RuleMatch:
    return RuleMatch("T-S-01", (), "SELF_CARE", "monitor")


def _toy_determine_route(_a: dict[str, object]) -> str:
    return "ROUTE_STANDARD"


def _toy_provisional_emergency(a: dict[str, object]) -> bool:
    return a.get("chest_pain_severe") == "true"


def _toy_self_care_checklist(a: dict[str, object]) -> bool:
    return a.get("resolved_with_rest") == "true"


def _toy_budget_key(_a: dict[str, object], _route: str, _known: str | None) -> str:
    return "DEFAULT"


def _toy_skip_rule(_cluster: QuestionCluster, _a: dict[str, object]) -> bool:
    return False


TOY_PROTOCOL = SymptomProtocol(
    name="toy_chest_pain",
    fields_by_key=_FIELDS,
    clusters=_CLUSTERS,
    stage_order=("0", "1"),
    gate_stages=("1", "1"),  # protocol tối giản không cần 2 gate stage riêng biệt
    budget={"DEFAULT": (2, 5)},
    budget_floor_stage="1",
    determine_route=_toy_determine_route,
    budget_key=_toy_budget_key,
    provisional_emergency_signal=_toy_provisional_emergency,
    self_care_checklist_satisfied=_toy_self_care_checklist,
    skip_rule=_toy_skip_rule,
    rule_catalog=(_toy_r_e_01,),
    fallback_rule=_toy_fallback,
    self_care_default_rule=_toy_self_care_default,
    emergency_message="Đau ngực dữ dội - gọi cấp cứu ngay.",
    safety_signal_fields=("chest_pain_severe",),
    opportunistic_keywords=(("chest_pain_severe", ("đau ngực dữ dội",)),),
)


# --- stage_machine dùng chung, không sửa 1 dòng nào cho protocol mới -----------------------------


def test_next_cluster_walks_toy_protocol_in_declared_order():
    first = stage_machine.next_cluster(TOY_PROTOCOL, "0", {})
    assert first.id == "T0-01"

    second = stage_machine.next_cluster(TOY_PROTOCOL, "1", {})
    assert second.id == "T1-01"

    remaining = stage_machine.next_cluster(TOY_PROTOCOL, "1", {}, asked_ids=frozenset({"T1-01"}))
    assert remaining.id == "T1-02"


def test_next_stage_follows_toy_stage_order():
    assert stage_machine.next_stage(TOY_PROTOCOL, "0") == "1"
    assert stage_machine.next_stage(TOY_PROTOCOL, "1") is None


def test_advance_crosses_stage_boundary_when_current_stage_is_exhausted():
    """Cụm cuối của stage vừa được trả lời -> phải đi thẳng sang cụm đầu stage sau.

    `next_cluster` trả `None` ở đây, và đó chính là lỗi đo được khi chạy LLM thật: `run_turn` sinh
    câu hỏi RỖNG rồi session âm thầm nhảy stage, người bệnh không được hỏi gì nhưng lượt sau vẫn bị
    trích theo schema của cụm chưa từng hỏi."""
    answers = {"age_value": 30, "age_unit": "year"}
    assert stage_machine.next_cluster(TOY_PROTOCOL, "0", answers) is None

    step = stage_machine.advance(TOY_PROTOCOL, "0", answers, asked_ids=frozenset({"T0-01"}))
    assert step.cluster is not None
    assert step.cluster.id == "T1-01"
    assert step.stage == "1"
    assert step.stop_reason is None


def test_advance_reports_stop_reason_instead_of_cluster_at_end_of_protocol():
    answers = {"age_value": 30, "age_unit": "year", "chest_pain_severe": "false", "resolved_with_rest": "true"}
    step = stage_machine.advance(
        TOY_PROTOCOL, "1", answers, asked_ids=frozenset({"T0-01", "T1-01", "T1-02"}), asked_count=3,
    )
    assert step.cluster is None
    assert step.stop_reason == "SUFFICIENT_EVIDENCE"


def test_should_stop_red_flag_on_toy_emergency_signal():
    answers = {"chest_pain_severe": "true"}
    assert stage_machine.should_stop(TOY_PROTOCOL, "1", answers, asked_count=1) == "RED_FLAG"


def test_should_stop_sufficient_evidence_when_toy_checklist_satisfied():
    answers = {"age_value": 30, "age_unit": "year", "chest_pain_severe": "false", "resolved_with_rest": "true"}
    stop = stage_machine.should_stop(TOY_PROTOCOL, "1", answers, asked_count=3)
    assert stop == "SUFFICIENT_EVIDENCE"


# --- rule_engine dùng chung, không sửa 1 dòng nào cho protocol mới -------------------------------


def test_rule_engine_emergency_on_toy_protocol():
    result = rule_engine.evaluate(TOY_PROTOCOL, {"chest_pain_severe": "true"})
    assert result.triage_level == "EMERGENCY"
    assert result.triggered_rules == ("T-E-01",)
    assert result.reason_codes == ("TF-01",)


def test_rule_engine_self_care_fallback_on_toy_protocol():
    result = rule_engine.evaluate(TOY_PROTOCOL, {"chest_pain_severe": "false", "resolved_with_rest": "true"})
    assert result.triage_level == "SELF_CARE"
    assert result.triggered_rules == ("T-S-01",)


def test_rule_engine_early_visit_fallback_when_checklist_not_satisfied():
    result = rule_engine.evaluate(TOY_PROTOCOL, {"chest_pain_severe": "false", "resolved_with_rest": "unknown"})
    assert result.triage_level == "EARLY_VISIT"
    assert result.triggered_rules == ("T-G-01",)


def test_toy_protocol_and_fever_protocol_run_through_the_same_engine_independently():
    """Chốt hạ: cùng 1 hàm `rule_engine.evaluate`, cùng 1 hàm `stage_machine.next_cluster`, chạy đúng
    cho CẢ HAI protocol trong CÙNG một quá trình, không protocol nào rò rỉ state sang protocol kia."""
    from src.services.engines.fever_protocol import FEVER_PROTOCOL

    toy_result = rule_engine.evaluate(TOY_PROTOCOL, {"chest_pain_severe": "true"})
    fever_result = rule_engine.evaluate(FEVER_PROTOCOL, {"seizure_active_now": "true", "seizure_occurred": "true"})

    assert toy_result.triage_level == "EMERGENCY"
    assert toy_result.triggered_rules == ("T-E-01",)
    assert fever_result.triage_level == "EMERGENCY"
    assert fever_result.triggered_rules == ("R-E-02",)
