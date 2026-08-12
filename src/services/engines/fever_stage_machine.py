"""State machine (stage/route) cho agent fever, theo
`_guidance/fever-detect-agent-task.md` Bước 2 và
`docs/medical_knowledge/fever-conversation-specification.md` (CS) Part 1.3 (dừng hỏi), Part 2 (stage
table), Part 4 (§4.1 EMERGENCY short-circuit, §4.2 SELF_CARE minimum scan, §4.3 routing + ngân sách),
Part 7 (flowchart/state machine/conversation graph — nguồn thật cho thứ tự chuyển stage).

Module này THUẦN rule-based: không import LLM/`provider_router` ở bất kỳ đâu (Checkpoint 2 assert
`"provider_router" not in sys.modules` sau khi import module này). Nó xây trên
`fever_checklist.QUESTION_CLUSTERS`/`FEVER_FIELDS` (Bước 1), không định nghĩa lại field/cụm.

Phạm vi CHỦ ĐỊNH thu hẹp so với rule engine đầy đủ (đó là Bước 3, `red_flag_engine`, chưa tồn tại khi
module này được viết):

- `_has_red_flag()` chỉ dùng một tập field EMERGENCY tối thiểu, trực tiếp nguy hiểm (theo gợi ý của
  task: `seizure_active_now`, `non_blanching_rash`, `cyanosis`, `stridor_or_drooling`,
  `cold_clammy_skin`, `worse_after_defervescence`, tuổi <3 tháng có sốt, ...) — KHÔNG phải toàn bộ
  bảng `R-E-xx` của knowledge model. Khi Bước 3 có rule engine thật, gate an toàn thật sự phải chạy
  qua đó; hàm này chỉ đủ để state machine biết "dừng lại vì có khả năng đỏ" cho mục đích Checkpoint 2.
- `_is_high_risk()` (dùng cho `ROUTE_HIGH_RISK`) là một xấp xỉ đơn giản của `conservatism_tier >= 1`
  (KM §5.1/§5.2) dựa trên các field risk đã biết trực tiếp từ answers — không tính lại đầy đủ ma trận
  quần thể của KM §5.2 (đó cũng là việc của rule engine, không phải state machine).
- Điều kiện Ask/Skip theo tuổi/giới ở Stage 4 (Q4-01/01b/02/03/04/05/06) và các field `C` gated theo
  tuổi ở Stage 3A/3B (`bulging_fontanelle`, `social_response_child`, `chest_indrawing`,
  `nasal_flaring_grunting`, `non_weight_bearing`, `new_confusion`...) được mã hoá trực tiếp theo mô tả
  cột "Ask condition"/"Skip condition" của CS Part 3 — khi điều kiện phụ thuộc một giá trị còn
  `unknown` (vd tuổi chưa biết), chọn nhánh AN TOÀN HƠN (hỏi thêm) theo P0-6.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable

from src.services.checklists.fever_checklist import (
    FEVER_FIELDS,
    QuestionCluster,
    Stage,
    clusters_for_stage,
)
from src.services.infra import fever_stage_log

# ---------------------------------------------------------------------------------------------
# Stop reasons — CS Part 1.3
# ---------------------------------------------------------------------------------------------


class StopReason(str, Enum):
    """CS Part 1.3 — "áp dụng điều kiện nào đến trước thì dừng theo điều kiện đó"."""

    RED_FLAG = "RED_FLAG"
    SUFFICIENT = "SUFFICIENT"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    USER_CANNOT_CONTINUE = "USER_CANNOT_CONTINUE"


# ---------------------------------------------------------------------------------------------
# Stage order — CS Part 2 + Part 7.2 state machine (bỏ qua "6" vì đó là kết thúc, không có cụm hỏi)
# ---------------------------------------------------------------------------------------------

STAGE_ORDER: tuple[Stage, ...] = ("0", "1", "2", "3A", "3B", "4", "5")

_NEXT_STAGE_AFTER: dict[str, str | None] = {
    "0": "1",
    "1": "2",
    "2": "3A",
    "3A": "3B",
    "3B": "4",
    "4": "5",
    "5": None,
}


def stage_index(stage: str) -> int:
    return STAGE_ORDER.index(stage)


def advance_stage(stage: str) -> str | None:
    """Stage kế tiếp theo thứ tự cố định 0->1->2->3A->3B->4->5. `None` = hết, sang Stage 6."""
    return _NEXT_STAGE_AFTER.get(stage)


# ---------------------------------------------------------------------------------------------
# Routes — CS §4.3
# ---------------------------------------------------------------------------------------------

ROUTE_INFANT_HIGH = "ROUTE_INFANT_HIGH"
ROUTE_HIGH_RISK = "ROUTE_HIGH_RISK"
ROUTE_STANDARD = "ROUTE_STANDARD"
ROUTE_DENGUE_CONTEXT = "ROUTE_DENGUE_CONTEXT"
ROUTE_LOCALIZED_SOURCE = "ROUTE_LOCALIZED_SOURCE"

ROUTES: tuple[str, ...] = (
    ROUTE_INFANT_HIGH,
    ROUTE_HIGH_RISK,
    ROUTE_STANDARD,
    ROUTE_DENGUE_CONTEXT,
    ROUTE_LOCALIZED_SOURCE,
)

# Ngân sách câu hỏi (số CỤM, không phải field đơn lẻ) — CS §6.5.
#
# Bảng gốc CS §6.5 khoá theo TÌNH HUỐNG KẾT LUẬN (EMERGENCY/EARLY_VISIT/SELF_CARE-ứng viên/nguy cơ cao
# ổn định), không khoá trực tiếp theo 5 route đặt tên ở §4.3. Ánh xạ route -> ngân sách dưới đây là
# một lựa chọn hợp lý (ghi rõ để không giả vờ đây là chép nguyên văn 1:1):
#   - ROUTE_INFANT_HIGH  -> tình huống "EMERGENCY rõ ràng do tuổi/ngưỡng riêng" (§6.5 dòng 1): 3-6
#   - ROUTE_HIGH_RISK    -> tình huống "nguy cơ cao nhưng ổn định" (§6.5 dòng 4): 8-12
#   - ROUTE_DENGUE_CONTEXT -> đào sâu cảnh báo SXHD trước khi kết luận, tương ứng khung EARLY_VISIT
#     (§6.5 dòng 2): 8-12
#   - ROUTE_STANDARD / ROUTE_LOCALIZED_SOURCE -> ứng viên SELF_CARE (§6.5 dòng 3): 12-16
ROUTE_BUDGET: dict[str, tuple[int, int]] = {
    ROUTE_INFANT_HIGH: (3, 6),
    ROUTE_HIGH_RISK: (8, 12),
    ROUTE_STANDARD: (12, 16),
    ROUTE_DENGUE_CONTEXT: (8, 12),
    ROUTE_LOCALIZED_SOURCE: (12, 16),
}


def budget_for_route(route: str) -> tuple[int, int]:
    return ROUTE_BUDGET[route]


# ---------------------------------------------------------------------------------------------
# Helpers dùng chung
# ---------------------------------------------------------------------------------------------


def _is_unknown(value: Any) -> bool:
    return value is None or value == "unknown"


def _truthy(answers: dict[str, Any], key: str) -> bool:
    """Đúng tri-state: chỉ True khi field CHẮC CHẮN là "true" (P0-4 - không suy diễn từ mơ hồ)."""
    return answers.get(key) == "true"


def _falsy(answers: dict[str, Any], key: str) -> bool:
    return answers.get(key) == "false"


def _positive(answers: dict[str, Any], key: str) -> bool:
    """Dùng cho field không hẳn tri-state boolean (enum/list/string) - coi mọi giá trị "có nội dung
    thực" là dương tính, phục vụ routing/gợi ý (KHÔNG dùng hàm này cho quyết định red-flag an toàn -
    ở đó luôn dùng `_truthy` tri-state nghiêm ngặt)."""
    value = answers.get(key)
    if _is_unknown(value):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() not in ("false", "none", "no", "0", "")
    if isinstance(value, (list, tuple, dict)):
        return len(value) > 0
    return bool(value)


def _age_months(answers: dict[str, Any]) -> float | None:
    value = answers.get("age_value")
    unit = answers.get("age_unit")
    if _is_unknown(value) or _is_unknown(unit):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if unit == "day":
        return numeric / 30.0
    if unit == "month":
        return numeric
    if unit == "year":
        return numeric * 12.0
    return None


# ---------------------------------------------------------------------------------------------
# Red flag tối thiểu — chỉ đủ cho state machine biết "dừng vì khả năng đỏ", KHÔNG thay thế rule
# engine Bước 3. Xem docstring module.
# ---------------------------------------------------------------------------------------------

_EMERGENCY_TRI_STATE_FIELDS: frozenset[str] = frozenset(
    (
        "seizure_active_now",
        "non_blanching_rash",
        "cyanosis",
        "stridor_or_drooling",
        "cold_clammy_skin",
        "capillary_refill_ge_3s",
        "worse_after_defervescence",
        "neck_stiffness",
        "focal_neuro_deficit",
        "mucosal_bleeding",
        "gi_bleeding",
        "abdominal_guarding",
    )
)

_EMERGENCY_CONSCIOUSNESS_VALUES: frozenset[str] = frozenset(
    ("unresponsive", "difficult_to_rouse", "lethargic")
)


def _has_red_flag(answers: dict[str, Any]) -> bool:
    if any(_truthy(answers, key) for key in _EMERGENCY_TRI_STATE_FIELDS):
        return True
    if answers.get("consciousness_level") in _EMERGENCY_CONSCIOUSNESS_VALUES:
        return True
    if answers.get("urine_output") == "none_gt_6h":
        return True
    if answers.get("vomiting_severity") == "unable_to_keep_fluids":
        return True
    if answers.get("breathing_difficulty") == "severe":
        return True
    age_m = _age_months(answers)
    if age_m is not None and age_m < 3 and _truthy(answers, "fever_reported"):
        return True
    return False


# ---------------------------------------------------------------------------------------------
# Field applicability — một field `C` chỉ "cần trả lời" khi điều kiện kích hoạt của nó đúng (CS Part
# 3, cột Ask/Skip condition). Dùng để không kẹt chờ mãi 1 field không bao giờ được hỏi.
# ---------------------------------------------------------------------------------------------

_CONDITIONAL_FIELD_APPLICABLE: dict[str, Callable[[dict[str, Any]], bool]] = {
    "temp_c": lambda a: a.get("fever_status") == "objective",
    "temp_site": lambda a: a.get("fever_status") == "objective",
    "temp_measured_at": lambda a: a.get("fever_status") == "objective",
    "gestational_weeks": lambda a: _truthy(a, "is_pregnant"),
    "obstetric_red_flags": lambda a: _truthy(a, "is_pregnant") or _truthy(a, "postpartum_6w"),
    "bulging_fontanelle": lambda a: (m := _age_months(a)) is None or m < 18,
    "social_response_child": lambda a: (m := _age_months(a)) is None or m < 60,
    "chest_indrawing": lambda a: (m := _age_months(a)) is None or m < 60,
    "nasal_flaring_grunting": lambda a: (m := _age_months(a)) is None or m < 60,
    "non_weight_bearing": lambda a: (m := _age_months(a)) is None or m < 192,
    "rash_present": lambda a: not _falsy(a, "non_blanching_rash"),
    "rash_type": lambda a: _truthy(a, "non_blanching_rash"),
    "abdominal_pain_location": lambda a: a.get("abdominal_pain_severity") not in (None, "unknown", "none"),
    "seizure_features": lambda a: _truthy(a, "seizure_occurred") and not _truthy(a, "seizure_active_now"),
    "surgical_site_signs": lambda a: _truthy(a, "recent_surgery_30d"),
    "immunocompromise_cause": lambda a: not _falsy(a, "immunocompromised"),
    "known_neutropenia": lambda a: not _falsy(a, "immunocompromised"),
}


def _field_applicable(field_key: str, answers: dict[str, Any]) -> bool:
    predicate = _CONDITIONAL_FIELD_APPLICABLE.get(field_key)
    if predicate is None:
        return True
    return predicate(answers)


def _all_fields_known(cluster: QuestionCluster, answers: dict[str, Any]) -> bool:
    for key in cluster.fields:
        if not _field_applicable(key, answers):
            continue
        if _is_unknown(answers.get(key)):
            return False
    return True


# ---------------------------------------------------------------------------------------------
# Ask condition per cluster — CS Part 3, cột "Ask condition"/"Skip condition". Mặc định True (đa số
# cụm "luôn hỏi").
# ---------------------------------------------------------------------------------------------


def _gate_q2_05(a: dict[str, Any]) -> bool:
    """Q2-05 hypothermia_reported: age<3 tháng HOẶC age>=65 tuổi HOẶC immunocompromised=true."""
    age_m = _age_months(a)
    if age_m is None:
        return True  # tuổi chưa rõ -> hỏi để an toàn (P0-6)
    if age_m < 3 or age_m >= 65 * 12:
        return True
    return _truthy(a, "immunocompromised")


def _gate_q3_07(a: dict[str, Any]) -> bool:
    """Q3-07 stridor_or_drooling: skip nếu đã đủ căn cứ EMERGENCY hô hấp (cyanosis/severe)."""
    return not (_truthy(a, "cyanosis") or a.get("breathing_difficulty") == "severe")


def _gate_q3_08b(a: dict[str, Any]) -> bool:
    """Q3-08b dizziness_on_standing: skip nếu đã có căn cứ nặng hơn ở cụm tuần hoàn Q3-08."""
    return not (_truthy(a, "cold_clammy_skin") or _truthy(a, "capillary_refill_ge_3s"))


def _gate_q3_02(a: dict[str, Any]) -> bool:
    """Q3-02 new_confusion: age >= 16 tuổi."""
    age_m = _age_months(a)
    if age_m is None:
        return True
    return age_m >= 16 * 12


def _gate_q4_01(a: dict[str, Any]) -> bool:
    """Q4-01 is_pregnant/gestational_weeks: sex=female AND 10<=age<=60 AND Q4-00 dương/mơ hồ ý thai kỳ."""
    if a.get("sex") != "female":
        return False
    age_m = _age_months(a)
    if age_m is not None:
        age_y = age_m / 12
        if not (10 <= age_y <= 60):
            return False
    return not _falsy(a, "is_pregnant")


def _gate_q4_01b(a: dict[str, Any]) -> bool:
    return _truthy(a, "is_pregnant") or _truthy(a, "postpartum_6w")


def _gate_q4_02(a: dict[str, Any]) -> bool:
    """Q4-02 postpartum_6w: sex=female AND 15<=age<=55 AND chưa xác nhận đang mang thai."""
    if a.get("sex") != "female":
        return False
    age_m = _age_months(a)
    if age_m is not None:
        age_y = age_m / 12
        if not (15 <= age_y <= 55):
            return False
    if _truthy(a, "is_pregnant"):
        return False
    return not _falsy(a, "postpartum_6w")


def _gate_q4_03(a: dict[str, Any]) -> bool:
    return not _falsy(a, "immunocompromised")


def _gate_q4_04(a: dict[str, Any]) -> bool:
    return not _falsy(a, "chronic_conditions")


def _gate_q4_05(a: dict[str, Any]) -> bool:
    return not (_falsy(a, "recent_surgery_30d") and _falsy(a, "indwelling_device"))


def _gate_q4_06(a: dict[str, Any]) -> bool:
    return not _falsy(a, "malaria_risk_area")


def _gate_q5_06(a: dict[str, Any]) -> bool:
    """Q5-06 immunization: age < 5 tuổi."""
    age_m = _age_months(a)
    if age_m is None:
        return True
    return age_m < 5 * 12


ASK_CONDITIONS: dict[str, Callable[[dict[str, Any]], bool]] = {
    "Q1-02": lambda a: _truthy(a, "fever_reported"),
    "Q1-03": lambda a: a.get("fever_status") == "subjective",
    "Q2-05": _gate_q2_05,
    "Q3-07": _gate_q3_07,
    "Q3-08b": _gate_q3_08b,
    "Q3-02": _gate_q3_02,
    "Q4-01": _gate_q4_01,
    "Q4-01b": _gate_q4_01b,
    "Q4-02": _gate_q4_02,
    "Q4-03": _gate_q4_03,
    "Q4-04": _gate_q4_04,
    "Q4-05": _gate_q4_05,
    "Q4-06": _gate_q4_06,
    "Q5-06": _gate_q5_06,
}


def _ask_allowed(cluster: QuestionCluster, answers: dict[str, Any]) -> bool:
    condition = ASK_CONDITIONS.get(cluster.id)
    if condition is None:
        return True
    return condition(answers)


# ---------------------------------------------------------------------------------------------
# next_cluster — pure rule-based
# ---------------------------------------------------------------------------------------------


def next_cluster(stage: str, answers: dict[str, Any]) -> QuestionCluster | None:
    """Cụm kế tiếp cần hỏi trong `stage`, hoặc `None` nếu hết cụm áp dụng (caller advance stage).

    - Không bao giờ trả cụm Stage 3B nếu đã có red flag EMERGENCY (kể cả khi được gọi trực tiếp với
      `stage="3B"`) — CS §3.3B: "Chỉ chạy khi Stage 3A âm tính toàn bộ".
    - Bỏ qua cụm mà điều kiện "Ask" không thỏa, hoặc mọi field áp dụng của cụm đã có giá trị xác định
      (không hỏi lại field đã biết — CS Part 3, quy ước "Không hỏi lại field đã có giá trị xác định").
    """
    if _has_red_flag(answers):
        return None
    for cluster in clusters_for_stage(stage):  # type: ignore[arg-type]
        if not _ask_allowed(cluster, answers):
            continue
        if _all_fields_known(cluster, answers):
            continue
        return cluster
    return None


def next_cluster_logged(
    session_id: str, *, turn: int, stage: str, answers: dict[str, Any]
) -> QuestionCluster | None:
    """Như `next_cluster`, nhưng ghi 1 dòng `tool_call` (`tool="fever_stage_machine.next_cluster"`)
    vào `fever_stage_log` cho mỗi lần gọi - dùng bởi driver thật/driver test Checkpoint 2."""
    known_fields = sorted(key for key, value in answers.items() if not _is_unknown(value))
    with fever_stage_log.tool(
        session_id,
        turn=turn,
        stage=stage,
        cluster_id=None,
        tool="fever_stage_machine.next_cluster",
        input={"stage": stage, "known_fields": known_fields},
    ) as rec:
        cluster = next_cluster(stage, answers)
        rec.output = {"cluster_id": cluster.id if cluster is not None else None}
    return cluster


# ---------------------------------------------------------------------------------------------
# Sufficiency / budget — CS Part 1.3, Part 6, §6.5
# ---------------------------------------------------------------------------------------------


def _is_sufficient(answers: dict[str, Any], route: str | None) -> bool:
    """CS Part 1.3 điều kiện 2 - "Đủ căn cứ": toàn bộ M0 (+ M1 nếu đang hướng SELF_CARE) đã xác định.

    Phạm vi thu hẹp: chỉ xét field M0/M1 CÓ áp dụng theo `_field_applicable` (bỏ qua field `C` chưa
    kích hoạt điều kiện tuổi/quần thể). Route quyết định SELF_CARE track dựa trên §4.3 (route hướng
    tới SELF_CARE là `ROUTE_STANDARD`/`ROUTE_LOCALIZED_SOURCE`)."""
    for field in FEVER_FIELDS:
        if field.tier != "M0":
            continue
        if not _field_applicable(field.key, answers):
            continue
        if _is_unknown(answers.get(field.key)):
            return False
    if route in (ROUTE_STANDARD, ROUTE_LOCALIZED_SOURCE):
        for field in FEVER_FIELDS:
            if field.tier != "M1":
                continue
            if not _field_applicable(field.key, answers):
                continue
            if _is_unknown(answers.get(field.key)):
                return False
    return True


def _remaining_only_optional(answers: dict[str, Any]) -> bool:
    """CS Part 1.3 điều kiện 3 / Part 6 "Dừng hẳn"(b) - phần còn thiếu chỉ là field O (rộng ra cả H,
    theo câu chữ Part 6 "chỉ là field O/H")."""
    for field in FEVER_FIELDS:
        if field.tier in ("O", "H"):
            continue
        if not _field_applicable(field.key, answers):
            continue
        if _is_unknown(answers.get(field.key)):
            return False
    return True


def should_stop(
    stage: str,
    answers: dict[str, Any],
    *,
    route: str | None = None,
    asked_count: int = 0,
    budget: int | None = None,
) -> StopReason | None:
    """CS Part 1.3 - áp dụng điều kiện nào đến trước thì dừng theo điều kiện đó:

    1. `RED_FLAG` - một field EMERGENCY tối thiểu dương tính (xem docstring module, phạm vi thu hẹp).
    2. `SUFFICIENT` - đủ M0 (+M1 nếu SELF_CARE track) đã xác định.
    3. `BUDGET_EXCEEDED` - hết ngân sách cụm câu hỏi (`asked_count >= budget`) VÀ phần còn thiếu chỉ
       là field O/H.
    4. `USER_CANNOT_CONTINUE` - không tự phát hiện được ở đây (cần tín hiệu ngoài luồng dữ liệu, vd
       mất kết nối) - caller tự set khi cần, giá trị enum tồn tại để hỗ trợ việc đó.

    `stage` hiện chưa dùng trực tiếp trong điều kiện (mọi field truy theo `answers`, không theo
    stage đang đứng) nhưng giữ trong signature đúng theo spec Bước 2 và dự phòng mở rộng.
    """
    del stage  # xem docstring - giữ tham số theo đúng chữ ký spec, chưa cần dùng trực tiếp.
    if _has_red_flag(answers):
        return StopReason.RED_FLAG
    if _is_sufficient(answers, route):
        return StopReason.SUFFICIENT
    if budget is not None and asked_count >= budget and _remaining_only_optional(answers):
        return StopReason.BUDGET_EXCEEDED
    return None


# ---------------------------------------------------------------------------------------------
# Routing — CS §4.3
# ---------------------------------------------------------------------------------------------


def _is_high_risk(answers: dict[str, Any]) -> bool:
    """Xấp xỉ đơn giản của `conservatism_tier >= 1` (KM §5.1/§5.2) - xem docstring module."""
    age_m = _age_months(answers)
    if age_m is not None and age_m >= 75 * 12:
        return True
    return any(
        _positive(answers, key)
        for key in (
            "is_pregnant",
            "postpartum_6w",
            "immunocompromised",
            "chronic_conditions",
            "recent_surgery_30d",
            "indwelling_device",
            "malaria_risk_area",
            "lives_alone",
        )
    )


def _is_dengue_context(answers: dict[str, Any]) -> bool:
    if any(_positive(answers, key) for key in ("mosquito_exposure", "outbreak_exposure", "nsaid_use")):
        return True
    if _truthy(answers, "worse_after_defervescence"):
        return True
    if _truthy(answers, "mucosal_bleeding") or _truthy(answers, "gi_bleeding"):
        return True
    return answers.get("abdominal_pain_severity") not in (None, "unknown", "none")


def _is_localized_source(answers: dict[str, Any]) -> bool:
    return any(
        _positive(answers, key)
        for key in ("sore_throat", "ear_pain", "cough", "urinary_symptoms", "localized_infection_signs")
    )


def determine_route(answers: dict[str, Any]) -> str:
    """CS §4.3 - xác định route ngay khi đủ dữ liệu. Thứ tự kiểm tra theo mức ưu tiên an toàn: tuổi
    nhũ nhi > nguy cơ cao > bối cảnh SXHD > ổ nhiễm khuẩn lành tính rõ > chuẩn."""
    age_m = _age_months(answers)
    if age_m is not None and age_m < 3:
        return ROUTE_INFANT_HIGH
    if _is_high_risk(answers):
        return ROUTE_HIGH_RISK
    if _is_dengue_context(answers):
        return ROUTE_DENGUE_CONTEXT
    if _is_localized_source(answers):
        return ROUTE_LOCALIZED_SOURCE
    return ROUTE_STANDARD
