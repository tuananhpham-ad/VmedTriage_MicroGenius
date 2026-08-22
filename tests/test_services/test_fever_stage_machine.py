"""Checkpoint 2 (_guidance/fever-detect-agent-task.md Bước 2) — state machine & ngân sách câu hỏi.

Lưu ý về căng thẳng số liệu giữa 2 tài liệu nguồn: Stage 3A (minimum safety scan, KHÔNG được cắt
theo CS §4.2/P0-1) đã chiếm **11 cụm**, cộng Stage 0-2 (~8 cụm) = ~19 cụm - tự nó đã vượt trần ngân
sách `SELF_CARE_CANDIDATE`/`EARLY_VISIT` (12-16/8-12) ở §6.5 TRƯỚC KHI hết Stage 3A. Thêm nữa, field
M1 bắt buộc cho checklist SELF_CARE (KM §5.4) nằm rải ở CẢ Stage 3B lẫn Stage 4 (`can_return_for_followup`,
`caregiver_available` ở Q4-08) - nếu ngân sách cắt trước khi Stage 4 xong, SELF_CARE sẽ KHÔNG BAO GIỜ
kết luận được (phát hiện qua Checkpoint 6 khi chạy qua API thật). Đây là căng thẳng có thật giữa
CS §4.2/§4.3 (không được cắt M0/M1 khi đang hướng SELF_CARE) và CS §6.5 (ngân sách tổng), không phải
bug của state machine - test dưới đây phản ánh đúng hệ quả: ngân sách chỉ thực sự có hiệu lực ở
Stage 5 (đúng CS §4.2, liệt kê "field P3 ở Stage 5" là phần được phép bỏ khi đã rõ lành tính).

Golden: bảng ngân sách CS §6.5, chép tay thành BUDGET (đã định nghĩa trong module, kiểm bằng test
riêng để chống hồi quy). Driver mô phỏng hội thoại: giữ 2 dict - `known` (dữ liệu "thật" của ca, đầy
đủ ngay từ đầu, giống việc feed sẵn 1 bộ answers giả lập) và `revealed` (những gì hệ thống đã "hỏi và
biết" - bắt đầu rỗng, chỉ được điền khi `next_cluster` thực sự chọn hỏi cụm đó). Đây là cách duy nhất
kiểm tra đúng ngân sách: nếu feed thẳng `known` vào `next_cluster` ngay từ đầu thì mọi field đã có sẵn,
sẽ không hỏi gì cả.
"""

from __future__ import annotations

import pytest

from src import paths
from src.services.infra import fever_stage_log
from tests.helpers import fever_api as fsm


@pytest.fixture(autouse=True)
def _isolated_log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LOGS_DIR", tmp_path)
    yield


def _run_conversation(
    known: dict[str, object],
    *,
    session_id: str,
    known_triage_level_at: dict[int, str] | None = None,
    max_turns: int = 60,
) -> tuple[list[str], str | None, dict[str, object]]:
    """Mô phỏng hội thoại đầy đủ: hỏi từng cụm theo `next_cluster`, dừng theo `should_stop`.

    `known_triage_level_at`: {asked_count: triage_level} - mô phỏng việc Bước 5 truyền hint từ rule
    engine sau khi đã hỏi đủ N cụm (state machine tự nó không tính triage_level, xem docstring
    module).
    """
    revealed: dict[str, object] = {}
    asked_ids: list[str] = []
    # KHONG hardcode "0": tu 2026-08-22 stage dau tien la "E" (quet cap cuu pho quat).
    # Hardcode o day thi mo phong bo qua han mot stage va moi so dem cum deu lech.
    stage: fsm.Stage = fsm.STAGE_ORDER[0]
    stop_reason: str | None = None
    known_triage_level_at = known_triage_level_at or {}
    known_triage_level: str | None = None
    fever_stage_log.start(session_id, route=None, budget=0)

    for _ in range(max_turns):
        known_triage_level = known_triage_level_at.get(len(asked_ids), known_triage_level)
        route = fsm.determine_route(revealed)
        with fever_stage_log.tool(
            session_id, turn=len(asked_ids) + 1, stage=stage, cluster_id=None,
            tool="fever_stage_machine.next_cluster", input={"stage": stage},
        ) as rec:
            cluster = fsm.next_cluster(stage, revealed, asked_ids=frozenset(asked_ids))
            rec.output = {"cluster_id": cluster.id if cluster else None}

        if cluster is None:
            following = fsm.next_stage(stage)
            if following is None:
                stop_reason = "SUFFICIENT_EVIDENCE" if fsm.self_care_checklist_satisfied(revealed) else "BUDGET_EXHAUSTED"
                break
            stage = following
            continue

        for key in cluster.fields:
            if key in known:
                revealed[key] = known[key]
        asked_ids.append(cluster.id)

        stop_reason = fsm.should_stop(
            stage, revealed, asked_count=len(asked_ids), route=route, known_triage_level=known_triage_level,
        )
        if stop_reason is not None:
            break

    fever_stage_log.finish(session_id, triage_level=known_triage_level or "", stop_reason=stop_reason or "", turns=len(asked_ids))
    return asked_ids, stop_reason, revealed


# --- ngân sách theo route/kết luận (§6.5) -------------------------------------------------------


def test_infant_route_stops_as_emergency_within_budget():
    known = {"age_value": 2, "age_unit": "month", "reporter_type": "parent_caregiver", "sex": "male", "fever_reported": True}
    asked, stop_reason, revealed = _run_conversation(known, session_id="infant-high")

    assert fsm.determine_route(revealed) == "ROUTE_INFANT_HIGH"
    assert stop_reason == "RED_FLAG"
    low, high = fsm.BUDGET["ROUTE_INFANT_HIGH"]
    assert low <= len(asked) <= high, asked


def test_high_risk_route_exhausts_budget_without_premature_self_care():
    known = {
        "age_value": 40, "age_unit": "year", "sex": "female", "reporter_type": "self",
        "fever_reported": True, "fever_status": "objective", "temp_c": 38.2, "temp_site": "axillary",
        "immunocompromised": True, "immunocompromise_cause": ["hiv_uncontrolled"],
        "fever_onset_at": "2026-08-10", "rigors": "false", "antipyretic_taken": "true",
        "worse_after_defervescence": "false", "consciousness_level": "alert",
        "social_response_child": "not_applicable", "feeding_intake": "normal",
        "breathing_difficulty": "none", "cyanosis": "false", "stridor_or_drooling": "false",
        "cold_clammy_skin": "false", "capillary_refill_ge_3s": "false", "urine_output": "normal",
        "vomiting_severity": "none", "seizure_occurred": "false", "neck_stiffness": "false",
        "severe_headache": "false", "focal_neuro_deficit": "false", "non_blanching_rash": "false",
        "mucosal_bleeding": "false", "gi_bleeding": "false", "abdominal_pain_severity": "none",
        "abdominal_guarding": "false", "is_pregnant": "false", "chronic_conditions": ["none"],
        "recent_surgery_30d": "false", "indwelling_device": ["none"], "malaria_risk_area": "false",
    }
    # `immunocompromised` chỉ lộ ra ở Stage 4 (Q4-03/Q4-00). Ngân sách chỉ có hiệu lực ở Stage 5
    # (xem should_stop), nên hội thoại vẫn kịp đi hết Stage 4 và chốt đúng route trước khi dừng.
    asked, stop_reason, revealed = _run_conversation(known, session_id="high-risk", max_turns=80)

    stage_3a_ids = {c.id for c in fsm.clusters_for_stage("3A")}
    assert stage_3a_ids.issubset(set(asked)), "Stage 3A (an toàn) không được bị ngân sách cắt ngang"
    assert revealed.get("immunocompromised") is True
    assert fsm.determine_route(revealed) == "ROUTE_HIGH_RISK"
    assert not fsm.has_provisional_emergency_signal(revealed)
    assert stop_reason in ("BUDGET_EXHAUSTED", "SUFFICIENT_EVIDENCE")


def test_determine_route_pure_function_covers_every_named_route():
    assert fsm.determine_route({"age_value": 1, "age_unit": "month"}) == "ROUTE_INFANT_HIGH"
    assert fsm.determine_route({"age_value": 30, "age_unit": "year", "is_pregnant": "true"}) == "ROUTE_HIGH_RISK"
    assert fsm.determine_route({"age_value": 40, "age_unit": "year", "malaria_risk_area": "true"}) == "ROUTE_HIGH_RISK"
    assert fsm.determine_route({"age_value": 78, "age_unit": "year"}) == "ROUTE_HIGH_RISK"
    assert fsm.determine_route({"age_value": 20, "age_unit": "year", "mosquito_exposure": "true"}) == "ROUTE_DENGUE_CONTEXT"
    assert (
        fsm.determine_route({"age_value": 10, "age_unit": "year", "sore_throat": "true"})
        == "ROUTE_LOCALIZED_SOURCE"
    )
    assert fsm.determine_route({"age_value": 10, "age_unit": "year"}) == "ROUTE_STANDARD"


def test_mandatory_m0_scan_never_truncated_by_budget_even_when_over_16_clusters():
    """P0-1: Stage 0-3A (an toàn tuyệt đối) không bao giờ bị ngân sách §6.5 cắt ngang, dù tổng số cụm
    của riêng Stage 3A (11 cụm) đã gần bằng/ vượt trần ngân sách self-care (12-16)."""
    known = {
        "age_value": 40, "age_unit": "year", "sex": "female", "reporter_type": "self",
        "fever_reported": True, "fever_status": "objective", "temp_c": 38.0, "temp_site": "axillary",
        "fever_onset_at": "2026-08-10", "rigors": "false", "antipyretic_taken": "true",
        "worse_after_defervescence": "false", "consciousness_level": "alert",
        "social_response_child": "not_applicable", "feeding_intake": "normal",
        "breathing_difficulty": "none", "cyanosis": "false", "stridor_or_drooling": "false",
        "cold_clammy_skin": "false", "capillary_refill_ge_3s": "false", "urine_output": "normal",
        "vomiting_severity": "none", "seizure_occurred": "false", "neck_stiffness": "false",
        "severe_headache": "false", "focal_neuro_deficit": "false", "non_blanching_rash": "false",
        "mucosal_bleeding": "false", "gi_bleeding": "false", "abdominal_pain_severity": "none",
        "abdominal_guarding": "false",
    }
    asked, _stop_reason, _revealed = _run_conversation(known, session_id="mandatory-scan")

    stage_3a_ids = {c.id for c in fsm.clusters_for_stage("3A")}
    assert stage_3a_ids.issubset(set(asked)), sorted(stage_3a_ids - set(asked))
    assert len(asked) > fsm.BUDGET["SELF_CARE_CANDIDATE"][1]


def test_early_visit_known_from_rule_engine_hint_stays_within_budget():
    known = {
        "age_value": 4, "age_unit": "month", "sex": "female", "reporter_type": "parent_caregiver",
        "fever_reported": True, "fever_status": "objective", "temp_c": 39.2, "temp_site": "tympanic",
        "fever_onset_at": "2026-08-11", "rigors": "false", "antipyretic_taken": "true",
        "worse_after_defervescence": "false", "consciousness_level": "alert", "feeding_intake": "normal",
        "social_response_child": "normal", "breathing_difficulty": "none", "cyanosis": "false",
        "chest_indrawing": "false", "nasal_flaring_grunting": "false", "stridor_or_drooling": "false",
        "cold_clammy_skin": "false", "capillary_refill_ge_3s": "false", "urine_output": "normal",
        "vomiting_severity": "none", "seizure_occurred": "false", "neck_stiffness": "false",
        "photophobia": "false", "severe_headache": "false", "bulging_fontanelle": "false",
        "focal_neuro_deficit": "false", "non_blanching_rash": "false", "mucosal_bleeding": "false",
        "gi_bleeding": "false", "abdominal_pain_severity": "none", "abdominal_guarding": "false",
    }
    # Rule engine (ngoài phạm vi state machine) đã kết luận EARLY_VISIT ngay khi đủ dữ liệu Q1-02
    # (age 3-6 tháng + temp>=39 -> RF-23/R-V-01) - giả lập bằng cách gắn hint từ cụm thứ 4 trở đi.
    asked, stop_reason, revealed = _run_conversation(
        known, session_id="early-visit", known_triage_level_at={4: "EARLY_VISIT"}, max_turns=80,
    )

    stage_3a_ids = {c.id for c in fsm.clusters_for_stage("3A")}
    assert stage_3a_ids.issubset(set(asked)), "Stage 3A (an toàn) không được bị ngân sách cắt ngang"
    assert fsm.determine_route(revealed) == "ROUTE_STANDARD"
    assert stop_reason == "BUDGET_EXHAUSTED"
    # Ngân sách chỉ có hiệu lực ở Stage 5 - kiểm tra nó THỰC SỰ dừng trong Stage 5, không chạy tràn
    # vô hạn (Stage 0-4 hoàn tất trước, đúng CS §4.2/§4.3, rồi mới bị cắt ở phần enrichment).
    assert asked[-1] in {c.id for c in fsm.clusters_for_stage("5")}


def test_self_care_candidate_route_standard_stays_within_budget_cap():
    known = {
        "age_value": 8, "age_unit": "year", "sex": "male", "reporter_type": "parent_caregiver",
        "fever_reported": True, "fever_status": "objective", "temp_c": 38.1, "temp_site": "axillary",
        "temp_measured_at": "2026-08-12T08:00:00+07:00",
        "fever_onset_at": "2026-08-11", "rigors": "false", "antipyretic_taken": "true",
        "antipyretic_drug": "paracetamol", "antipyretic_response": "partial",
        "worse_after_defervescence": "false", "consciousness_level": "alert",
        "social_response_child": "not_applicable", "activity_vs_baseline": "normal",
        "feeding_intake": "normal", "caregiver_concern_level": 2, "looks_very_unwell": "false",
        "breathing_difficulty": "none", "rapid_breathing": "false", "cyanosis": "false",
        "stridor_or_drooling": "false", "cold_clammy_skin": "false", "capillary_refill_ge_3s": "false",
        "dizziness_on_standing": "false", "urine_output": "normal", "vomiting_severity": "none",
        "seizure_occurred": "false", "neck_stiffness": "false", "severe_headache": "false",
        "focal_neuro_deficit": "false", "non_blanching_rash": "false", "mucosal_bleeding": "false",
        "gi_bleeding": "false", "abdominal_pain_severity": "none", "abdominal_guarding": "false",
        "joint_limb_swelling": "false", "non_weight_bearing": "false",
        "caregiver_available": "true", "can_return_for_followup": "true",
    }
    asked, stop_reason, revealed = _run_conversation(known, session_id="self-care", max_turns=80)

    stage_3a_ids = {c.id for c in fsm.clusters_for_stage("3A")}
    assert stage_3a_ids.issubset(set(asked)), "Stage 3A (an toàn) không được bị ngân sách cắt ngang"
    assert fsm.determine_route(revealed) == "ROUTE_STANDARD"
    assert stop_reason in ("BUDGET_EXHAUSTED", "SUFFICIENT_EVIDENCE")
    if stop_reason == "BUDGET_EXHAUSTED":
        assert asked[-1] in {c.id for c in fsm.clusters_for_stage("5")}


def test_budget_table_matches_conversation_spec_6_5():
    assert fsm.BUDGET["ROUTE_INFANT_HIGH"] == (3, 6)
    assert fsm.BUDGET["EMERGENCY"] == (3, 6)
    assert fsm.BUDGET["EARLY_VISIT"] == (8, 12)
    assert fsm.BUDGET["ROUTE_HIGH_RISK"] == (8, 12)
    assert fsm.BUDGET["SELF_CARE_CANDIDATE"] == (12, 16)


# --- thứ tự stage ----------------------------------------------------------------------------


def test_stage_order_is_monotonic_never_goes_backwards():
    order_index = {stage: i for i, stage in enumerate(fsm.STAGE_ORDER)}
    known = {"age_value": 10, "age_unit": "year", "sex": "male", "reporter_type": "self"}
    stage: fsm.Stage = fsm.STAGE_ORDER[0]
    revealed: dict[str, object] = {}
    seen_indices: list[int] = []
    for _ in range(80):
        seen_indices.append(order_index[stage])
        cluster = fsm.next_cluster(stage, revealed)
        if cluster is None:
            following = fsm.next_stage(stage)
            if following is None:
                break
            stage = following
            continue
        for key in cluster.fields:
            revealed[key] = known.get(key, "false")

    assert seen_indices == sorted(seen_indices)
    assert seen_indices[0] == 0


def test_stage_3b_entirely_skipped_when_stage_3a_not_clean():
    answers = {"neck_stiffness": "true"}  # 1 red flag M0 đã dương tính -> Stage 3A không sạch
    assert fsm.next_cluster("3B", answers) is None


def test_stage_3b_runs_when_stage_3a_is_clean():
    answers = {"neck_stiffness": "false", "cyanosis": "false"}
    cluster = fsm.next_cluster("3B", answers)
    assert cluster is not None
    assert cluster.stage == "3B"


# --- dừng cứng ---------------------------------------------------------------------------------


def test_should_stop_returns_red_flag_immediately_on_emergency_field():
    answers = {"seizure_active_now": "true"}
    assert fsm.should_stop("3A", answers, asked_count=1) == "RED_FLAG"


def test_should_stop_user_cannot_continue_beats_everything_except_a_red_flag():
    """Tên cũ ghi "overrides everything" và đó chính là lỗi P0.6: ý định dừng của người bệnh KHÔNG
    được thắng một tín hiệu đỏ. Thứ tự đầy đủ nằm ở `test_user_intent_and_stopping.py`."""
    answers: dict[str, object] = {}
    assert fsm.should_stop("1", answers, asked_count=1, user_can_continue=False) == "USER_CANNOT_CONTINUE"


# --- thuần rule (không LLM) --------------------------------------------------------------------


def test_module_never_imports_llm_provider():
    import ast
    import inspect

    from src.services.symptom_protocol import stage_machine

    tree = ast.parse(inspect.getsource(stage_machine))
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    assert not any("provider_router" in name or name in ("src.services.infra.llm", "src.services.llm") for name in imported_modules)


# --- log -----------------------------------------------------------------------------------


def test_next_cluster_tool_calls_are_logged_once_per_asked_cluster():
    known = {"age_value": 2, "age_unit": "month", "reporter_type": "parent_caregiver", "sex": "male", "fever_reported": True}
    asked, _stop_reason, _revealed = _run_conversation(known, session_id="log-check")

    records = fever_stage_log.read_all("log-check")
    tool_calls = [r for r in records if r["event"] == "tool_call" and r["tool"] == "fever_stage_machine.next_cluster"]
    successful_calls = [r for r in tool_calls if r["output"]["cluster_id"] is not None]
    assert len(successful_calls) == len(asked)
