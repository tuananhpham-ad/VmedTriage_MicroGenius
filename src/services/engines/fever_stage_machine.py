"""State machine thuần rule-based cho agent fever: chọn cụm câu hỏi kế tiếp, xác định route, và
quyết định khi nào dừng hội thoại. Theo đúng
`docs/medical_knowledge/fever-conversation-specification.md` (CS) Part 2 (stages), Part 4.3
(routing), Part 6/§6.5 (ngân sách câu hỏi), Part 1.3 (điều kiện dừng), và Part 7 (state diagram).

KHÔNG gọi LLM, không import `provider_router`/`llm`. Đây là ranh giới kiến trúc bắt buộc (mục 2 của
`_guidance/fever-detect-agent-task.md`): mọi quyết định stage/route/dừng đều rule-based thuần.

Ranh giới với rule engine (Bước 3, `red_flag_engine`): `should_stop` ở đây chỉ chạy một provisional
scan RẤT NHẸ trên các field `M0` "đỏ tuyệt đối" để biết KHI NÀO dừng hỏi ở Stage 3A/3B (đúng Part 1.3
CS điểm 1) — đây KHÔNG phải rule engine đầy đủ (không sinh `reason_codes`/`triggered_rules` chính
thức, không thay thế `red_flag_engine.evaluate()`). Kết luận triage chính thức luôn do rule engine của
Bước 3 quyết định.
"""

from __future__ import annotations

from typing import Literal

from src.services.checklists.fever_checklist import (
    QUESTION_CLUSTERS,
    QuestionCluster,
    Stage,
    clusters_for_stage,
)

Route = Literal[
    "ROUTE_INFANT_HIGH",
    "ROUTE_HIGH_RISK",
    "ROUTE_STANDARD",
    "ROUTE_DENGUE_CONTEXT",
    "ROUTE_LOCALIZED_SOURCE",
]

StopReason = Literal["RED_FLAG", "SUFFICIENT_EVIDENCE", "BUDGET_EXHAUSTED", "USER_CANNOT_CONTINUE"]

# CS Part 2: thứ tự stage cố định. "6" là kết thúc đánh giá - không có QuestionCluster nào ở đó.
STAGE_ORDER: tuple[Stage, ...] = ("0", "1", "2", "3A", "3B", "4", "5")

# CS §6.5 - ngân sách câu hỏi tính theo CỤM (không phải field đơn lẻ), khoá theo route/kết luận.
# ROUTE_DENGUE_CONTEXT không có hàng riêng trong §6.5 - tài liệu mô tả nó "đào sâu" bộ câu hỏi trước
# khi kết luận, nên dùng chung ngân sách với nhóm ứng viên SELF_CARE (12-16) [EN - suy luận hợp lý từ
# §4.3/§6.5, không có con số riêng trong tài liệu nguồn].
BUDGET: dict[str, tuple[int, int]] = {
    "ROUTE_INFANT_HIGH": (3, 6),
    "EMERGENCY": (3, 6),
    "EARLY_VISIT": (8, 12),
    "ROUTE_HIGH_RISK": (8, 12),
    "SELF_CARE_CANDIDATE": (12, 16),
    "ROUTE_DENGUE_CONTEXT": (12, 16),
}

# Field M0 "đỏ tuyệt đối" dùng cho provisional scan của should_stop (xem docstring module).
# Value coi là dương tính: chuỗi tri-state "true", hoặc enum/giá trị cụ thể liệt kê trong set.
_EMERGENCY_TRI_STATE_FIELDS: tuple[str, ...] = (
    "seizure_active_now",
    "seizure_occurred",
    "neck_stiffness",
    "focal_neuro_deficit",
    "cyanosis",
    "stridor_or_drooling",
    "cold_clammy_skin",
    "capillary_refill_ge_3s",
    "non_blanching_rash",
    "mucosal_bleeding",
    "gi_bleeding",
    "worse_after_defervescence",
)
_EMERGENCY_ENUM_MATCHES: dict[str, frozenset[str]] = {
    "consciousness_level": frozenset({"difficult_to_rouse", "unresponsive"}),
    "breathing_difficulty": frozenset({"severe"}),
    "urine_output": frozenset({"none_gt_6h"}),
    "feeding_intake": frozenset({"unable"}),
    "vomiting_severity": frozenset({"unable_to_keep_fluids"}),
    "abdominal_pain_severity": frozenset({"severe"}),
}


def _is_filled(value: object) -> bool:
    return value is not None and value != "unknown" and value != ""


def _is_true(value: object) -> bool:
    return value is True or value == "true"


def age_in_months(answers: dict[str, object]) -> float | None:
    value = answers.get("age_value")
    unit = answers.get("age_unit")
    if not _is_filled(value) or not _is_filled(unit):
        return None
    try:
        numeric = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if unit == "day":
        return numeric / 30.0
    if unit == "month":
        return numeric
    if unit == "year":
        return numeric * 12.0
    return None


def has_provisional_emergency_signal(answers: dict[str, object]) -> bool:
    """Quét rất nhẹ các field M0 đỏ tuyệt đối - CHỈ dùng để biết khi nào state machine nên dừng hỏi
    thường quy (Part 1.3 CS điểm 1). Không sinh reason_codes/triggered_rules chính thức."""
    for key in _EMERGENCY_TRI_STATE_FIELDS:
        if _is_true(answers.get(key)):
            return True
    for key, matches in _EMERGENCY_ENUM_MATCHES.items():
        if answers.get(key) in matches:
            return True
    age_months = age_in_months(answers)
    if age_months is not None and age_months < 3 and _is_true(answers.get("fever_reported")):
        return True  # RF-22: sốt ở trẻ < 3 tháng luôn EMERGENCY
    return False


def determine_route(answers: dict[str, object]) -> Route:
    """CS §4.3. Thứ tự ưu tiên: infant > high_risk > dengue_context > localized_source > standard -
    route mạnh hơn không bao giờ bị route yếu hơn ghi đè, đúng tinh thần "không rule nào hạ mức"."""
    age_months = age_in_months(answers)
    if age_months is not None and age_months < 3:
        return "ROUTE_INFANT_HIGH"

    if _is_high_risk_tier(answers):
        return "ROUTE_HIGH_RISK"

    if _is_dengue_context(answers):
        return "ROUTE_DENGUE_CONTEXT"

    if _is_localized_source(answers):
        return "ROUTE_LOCALIZED_SOURCE"

    return "ROUTE_STANDARD"


def _is_high_risk_tier(answers: dict[str, object]) -> bool:
    """KM §5.1-5.2 conservatism_tier >= 1 - tập điều kiện chính, không đòi hỏi phủ hết ma trận đầy đủ
    (đó là việc của rule engine Bước 3)."""
    if _is_true(answers.get("is_pregnant")) or _is_true(answers.get("postpartum_6w")):
        return True
    if _is_true(answers.get("immunocompromised")) or _is_true(answers.get("known_neutropenia")):
        return True
    if _is_true(answers.get("malaria_risk_area")):
        return True
    chronic = answers.get("chronic_conditions")
    if isinstance(chronic, (list, tuple)) and any(item not in ("none", "unknown") for item in chronic):
        return True
    age_months = age_in_months(answers)
    if age_months is not None and age_months >= 75 * 12:
        return True
    if _is_true(answers.get("lives_alone")) or answers.get("caregiver_available") == "false":
        return True
    return False


def _is_dengue_context(answers: dict[str, object]) -> bool:
    if _is_true(answers.get("mosquito_exposure")):
        return True
    outbreak = answers.get("outbreak_exposure")
    if isinstance(outbreak, (list, tuple)) and "dengue" in outbreak:
        return True
    if answers.get("abdominal_pain_severity") == "severe":
        return True
    if _is_true(answers.get("mucosal_bleeding")) or _is_true(answers.get("gi_bleeding")):
        return True
    if _is_true(answers.get("worse_after_defervescence")):
        return True
    if _is_true(answers.get("nsaid_use")):
        return True
    return False


def _is_localized_source(answers: dict[str, object]) -> bool:
    """Chỉ có ý nghĩa SAU Stage 3A sạch (CS §4.3) - caller đảm bảo không gọi sớm hơn."""
    localized_signals = (
        _is_true(answers.get("sore_throat")),
        _is_true(answers.get("ear_pain")),
        _is_true(answers.get("cough")),
        _is_true(answers.get("urinary_symptoms")),
        _is_true(answers.get("localized_infection_signs")),
    )
    return any(localized_signals) and not has_provisional_emergency_signal(answers)


# ---------------------------------------------------------------------------------------------
# Skip condition riêng cho các cụm có "Ask condition" không đơn thuần là "luôn hỏi" (CS Part 3).
# Trả True => BỎ QUA cụm này dù còn field chưa điền.
# ---------------------------------------------------------------------------------------------


def _skip_q1_03(answers: dict[str, object]) -> bool:
    return answers.get("fever_status") != "subjective"


def _skip_q2_05(answers: dict[str, object]) -> bool:
    age_months = age_in_months(answers)
    young = age_months is not None and age_months < 3
    old = age_months is not None and age_months >= 65 * 12
    return not (young or old or _is_true(answers.get("immunocompromised")))


def _skip_q3_02(answers: dict[str, object]) -> bool:
    age_months = age_in_months(answers)
    return age_months is not None and age_months < 16 * 12


def _skip_if_stage_3a_not_clean(answers: dict[str, object]) -> bool:
    """Stage 3B chỉ chạy nếu Stage 3A âm tính toàn bộ (CS §3.3B)."""
    return has_provisional_emergency_signal(answers)


def _skip_q4_01(answers: dict[str, object]) -> bool:
    age_months = age_in_months(answers)
    if answers.get("sex") != "female" or age_months is None:
        return True
    age_years = age_months / 12.0
    return not (10 <= age_years <= 60)


def _skip_q4_01b(answers: dict[str, object]) -> bool:
    return not (_is_true(answers.get("is_pregnant")) or _is_true(answers.get("postpartum_6w")))


def _skip_q4_02(answers: dict[str, object]) -> bool:
    age_months = age_in_months(answers)
    if answers.get("sex") != "female" or age_months is None:
        return True
    age_years = age_months / 12.0
    if _is_true(answers.get("is_pregnant")):
        return True
    return not (15 <= age_years <= 55)


def _skip_q5_06(answers: dict[str, object]) -> bool:
    age_months = age_in_months(answers)
    return not (age_months is not None and age_months < 5 * 12)


_SKIP_RULES: dict[str, object] = {
    "Q1-03": _skip_q1_03,
    "Q2-05": _skip_q2_05,
    "Q3-02": _skip_q3_02,
    "Q4-01": _skip_q4_01,
    "Q4-01b": _skip_q4_01b,
    "Q4-02": _skip_q4_02,
    "Q5-06": _skip_q5_06,
}

_STAGE_3B_STAGES: frozenset[Stage] = frozenset({"3B"})


def _cluster_is_skipped(cluster: QuestionCluster, answers: dict[str, object]) -> bool:
    if cluster.stage in _STAGE_3B_STAGES and _skip_if_stage_3a_not_clean(answers):
        return True
    rule = _SKIP_RULES.get(cluster.id)
    if rule is not None and rule(answers):
        return True
    return False


def _cluster_needs_answer(cluster: QuestionCluster, answers: dict[str, object]) -> bool:
    return any(not _is_filled(answers.get(key)) for key in cluster.fields)


def next_cluster(
    stage: Stage,
    answers: dict[str, object],
    *,
    asked_ids: frozenset[str] = frozenset(),
) -> QuestionCluster | None:
    """Cụm câu hỏi kế tiếp trong `stage` hiện tại, hoặc `None` nếu đã hết cụm khả dụng của stage đó
    (caller khi đó tự chuyển sang `next_stage(stage)`). Rule-based thuần, không gọi LLM."""
    for cluster in clusters_for_stage(stage):
        if cluster.id in asked_ids:
            continue
        if _cluster_is_skipped(cluster, answers):
            continue
        if not _cluster_needs_answer(cluster, answers):
            continue
        return cluster
    return None


def next_stage(stage: Stage) -> Stage | None:
    """Stage kế tiếp theo STAGE_ORDER, hoặc None nếu đã ở stage cuối (Stage 5 -> hết, sang Stage 6
    kết thúc đánh giá - Stage 6 không sinh QuestionCluster nào, xem CS §3.6)."""
    try:
        index = STAGE_ORDER.index(stage)
    except ValueError:
        return None
    if index + 1 >= len(STAGE_ORDER):
        return None
    return STAGE_ORDER[index + 1]


def budget_key(
    answers: dict[str, object],
    route: Route,
    *,
    known_triage_level: str | None = None,
) -> str:
    """Chọn đúng hàng ngân sách trong BUDGET theo route/kết luận hiện có (§6.5).

    `known_triage_level`: kết luận triage MỚI NHẤT do rule engine (Bước 3, chạy ở Stage 3A/3B/4)
    trả về, do caller (Bước 5 `run_turn`) truyền vào - state machine không tự tính lại rule engine
    (xem docstring module). Không truyền gì thì chỉ dựa vào provisional scan (chỉ bắt được
    EMERGENCY, không bắt được EARLY_VISIT sinh ra ở Stage 4 như RF-23)."""
    if route == "ROUTE_INFANT_HIGH" or has_provisional_emergency_signal(answers) or known_triage_level == "EMERGENCY":
        return "EMERGENCY"
    if route == "ROUTE_HIGH_RISK":
        return "ROUTE_HIGH_RISK"
    if route == "ROUTE_DENGUE_CONTEXT":
        return "ROUTE_DENGUE_CONTEXT"
    if known_triage_level == "EARLY_VISIT":
        return "EARLY_VISIT"
    return "SELF_CARE_CANDIDATE"


def self_care_checklist_satisfied(answers: dict[str, object]) -> bool:
    """KM §5.4 - checklist bắt buộc trước khi cho phép kết luận SELF_CARE."""
    if has_provisional_emergency_signal(answers):
        return False
    age_months = age_in_months(answers)
    if age_months is None or age_months < 6:
        return False
    duration = answers.get("fever_duration_days")
    if isinstance(duration, (int, float)) and duration >= 5:
        return False
    if answers.get("consciousness_level") != "alert":
        return False
    if answers.get("feeding_intake") not in ("normal", "reduced"):
        return False
    if answers.get("urine_output") != "normal":
        return False
    if not (_is_true(answers.get("caregiver_available")) or answers.get("reporter_type") == "self"):
        return False
    if not _is_true(answers.get("can_return_for_followup")):
        return False
    for cluster in QUESTION_CLUSTERS:
        if cluster.stage not in ("0", "1", "2", "3A", "3B"):
            continue
        if _cluster_is_skipped(cluster, answers):
            continue
        if _cluster_needs_answer(cluster, answers):
            return False
    return True


def should_stop(
    stage: Stage,
    answers: dict[str, object],
    *,
    asked_count: int,
    route: Route | None = None,
    known_triage_level: str | None = None,
    user_can_continue: bool = True,
) -> StopReason | None:
    """CS Part 1.3 - áp theo thứ tự: chốt đỏ > đủ căn cứ > hết ngân sách > người dùng không tiếp tục
    được. `asked_count` là số CỤM đã hỏi trong toàn phiên (không phải field đơn lẻ, đúng §6.5).
    Ngân sách chỉ có hiệu lực từ Stage 3B trở đi - xem chú thích tại nơi kiểm tra bên dưới."""
    if not user_can_continue:
        return "USER_CANNOT_CONTINUE"

    if has_provisional_emergency_signal(answers) or known_triage_level == "EMERGENCY":
        return "RED_FLAG"

    resolved_route = route or determine_route(answers)

    if stage == "5" and next_cluster(stage, answers) is None and self_care_checklist_satisfied(answers):
        return "SUFFICIENT_EVIDENCE"

    # CS §4.2: "Không được bỏ minimum scan an toàn - tức Stage 3A (toàn bộ field M0)". Ngân sách
    # câu hỏi KHÔNG BAO GIỜ được phép cắt ngang Stage 0-3A (an toàn tuyệt đối theo P0-1) - chỉ áp
    # dụng từ Stage 3B trở đi (M1/enrichment), nơi rút gọn là hợp lệ.
    if STAGE_ORDER.index(stage) < STAGE_ORDER.index("3B"):
        return None

    budget_max = BUDGET[budget_key(answers, resolved_route, known_triage_level=known_triage_level)][1]
    if asked_count >= budget_max:
        return "BUDGET_EXHAUSTED"

    return None
