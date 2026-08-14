"""`GENERIC_PROTOCOL` - protocol thu thập ban đầu cho than phiền CHƯA có protocol chuyên biệt.

Đọc `generic_checklist.py` trước để biết hợp đồng (hẹp) của protocol này.

Điểm khác fever quan trọng nhất, và là điểm CỐ Ý:

    self_care_checklist_satisfied  ->  luôn False
      => should_stop không bao giờ trả "SUFFICIENT_EVIDENCE"
      => luôn kết thúc bằng "BUDGET_EXHAUSTED"
      => fallback_rule chạy  =>  EARLY_VISIT  =>  TriagePriority.URGENT ("Khám sớm")

Nghĩa là **mọi** than phiền ngoài sốt đều vào hàng đợi điều dưỡng ở mức "Khám sớm". Đây là hệ quả có
ý thức, không phải tác dụng phụ: protocol này chỉ quét được tập dấu hiệu nguy hiểm PHỔ QUÁT, nó không
có căn cứ lâm sàng nào để nói "đau ngực này an toàn, cứ ở nhà". Không tuyên bố an toàn là điều đúng
duy nhất làm được. Đổi lại phải theo dõi tải hàng đợi sau khi lên production và chỉnh `BUDGET` nếu cần.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.services.checklists.generic_checklist import (
    FIELDS_BY_KEY,
    GATE_STAGES,
    QUESTION_CLUSTERS,
    STAGE_ORDER,
)
from src.services.symptom_protocol.common_safety import rules as common_rules
from src.services.symptom_protocol.common_safety.emergency_message import EMERGENCY_MESSAGE
from src.services.symptom_protocol.common_safety.predicates import age_in_months, array_has_any, is_true
from src.services.symptom_protocol.models import QuestionCluster, RuleMatch
from src.services.symptom_protocol.protocol import SymptomProtocol

PROTOCOL_NAME = "general"

BUDGET_FLOOR_STAGE = "4"

# Ngân sách tính theo CỤM. Hẹp hơn fever vì protocol này không đào sâu nguyên nhân - nó chỉ quét đỏ
# rồi bàn giao, hỏi dài thêm không đổi được kết luận (vốn luôn là EARLY_VISIT).
BUDGET: dict[str, tuple[int, int]] = {
    "EMERGENCY": (3, 6),
    "ROUTE_HIGH_RISK": (8, 14),
    "ROUTE_STANDARD": (8, 14),
}

REASON_CODE_LABELS: dict[str, str] = common_rules.REASON_CODE_LABELS

SAFETY_SIGNAL_FIELDS: tuple[str, ...] = common_rules.EMERGENCY_TRI_STATE_FIELDS + (
    "consciousness_level",
    "feeding_intake",
    "urine_output",
    "chief_complaint",
    "complaint_site",
    "complaint_onset_at",
)


def determine_route(answers: dict[str, object]) -> str:
    """Chỉ 2 nhánh: có bối cảnh nguy cơ hay không. Generic không có nhánh lâm sàng nào khác - mọi
    phân nhánh sâu hơn là việc của protocol chuyên biệt."""
    if _has_risk_context(answers):
        return "ROUTE_HIGH_RISK"
    return "ROUTE_STANDARD"


def _has_risk_context(a: dict[str, object]) -> bool:
    age_months = age_in_months(a)
    if age_months is not None and (age_months < 3 or age_months >= 75 * 12):
        return True
    return (
        is_true(a.get("immunocompromised"))
        or is_true(a.get("is_pregnant"))
        or is_true(a.get("postpartum_6w"))
        or is_true(a.get("recent_surgery_30d"))
        or array_has_any(a.get("chronic_conditions"), common_rules.CHRONIC_SEVERE)
    )


def budget_key(answers: dict[str, object], route: str, known_triage_level: str | None = None) -> str:
    if known_triage_level == "EMERGENCY":
        return "EMERGENCY"
    return route if route in BUDGET else "ROUTE_STANDARD"


def never_self_care(_answers: dict[str, object]) -> bool:
    """Protocol generic KHÔNG BAO GIỜ tự kết luận mức nhẹ nhất - xem docstring module."""
    return False


def _self_care_default_rule(_a: dict[str, object]) -> RuleMatch:
    """Không có đường nào gọi tới (vì `never_self_care` luôn False) nhưng `SymptomProtocol` bắt buộc
    khai. Trả EARLY_VISIT chứ không raise: nếu bất biến kia có ngày bị phá, hỏng theo hướng thận trọng
    vẫn tốt hơn là ném exception giữa một phiên đang hỏi bệnh."""
    return common_rules.default_early_visit_rule(_a)


def derive_duration(answers: dict[str, object]) -> dict[str, object]:
    """`complaint_duration_days` từ `complaint_onset_at` - phép tính THUẦN, không qua LLM (LLM không
    biết hôm nay là ngày nào nếu không được cho biết, và hay nhẩm sai)."""
    onset = answers.get("complaint_onset_at")
    if not isinstance(onset, str):
        return {}
    try:
        year, month, day = (int(part) for part in onset[:10].split("-"))
        onset_date = datetime(year, month, day, tzinfo=timezone.utc).date()
    except ValueError:
        return {}
    days = (datetime.now(timezone.utc).date() - onset_date).days
    if days < 0:
        return {}
    return {"complaint_duration_days": days}


# --- Skip rule -----------------------------------------------------------------------------------


def _skip_pregnancy_detail(answers: dict[str, object]) -> bool:
    """Chi tiết thai sản chỉ hỏi khi có căn cứ - hỏi tuần thai một người đã nói không mang thai (hoặc
    nam giới) là mất lượt và mất tin tưởng."""
    if answers.get("sex") == "male":
        return True
    return answers.get("is_pregnant") == "false"


def _skip_surgical_detail(answers: dict[str, object]) -> bool:
    return answers.get("recent_surgery_30d") == "false" and answers.get("indwelling_device") in (None, "unknown", "none")


_SKIP_RULES: dict[str, object] = {
    "Q4-01": _skip_pregnancy_detail,
    "Q4-01b": _skip_pregnancy_detail,
    "Q4-02": _skip_pregnancy_detail,
    "Q4-05": _skip_surgical_detail,
}


def skip_rule(cluster: QuestionCluster, answers: dict[str, object]) -> bool:
    predicate = _SKIP_RULES.get(cluster.id)
    return bool(predicate(answers)) if predicate is not None else False


# --- Rule catalog --------------------------------------------------------------------------------
#
# TOÀN BỘ là rule phổ quát: generic không có rule riêng nào và không được có. Rule mới cho một than
# phiền cụ thể phải đi kèm tài liệu lâm sàng và một protocol riêng, không nhét vào đây.
# `r_e_21` (sản khoa) phải đứng SAU mọi rule EMERGENCY khác - nó đọc `matches_so_far`.
RULE_CATALOG: tuple = (
    *common_rules.EMERGENCY_RULES,
    common_rules.r_e_21,
    *common_rules.EARLY_VISIT_RULES,
    common_rules.r_g_01,
)

FIELD_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "is_pregnant": ("gestational_weeks", "obstetric_red_flags"),
    "immunocompromised": ("immunocompromise_cause", "known_neutropenia"),
    "recent_surgery_30d": ("surgical_site_signs",),
    "rash_present": ("rash_type",),
}


GENERIC_PROTOCOL = SymptomProtocol(
    name=PROTOCOL_NAME,
    fields_by_key=FIELDS_BY_KEY,
    clusters=QUESTION_CLUSTERS,
    stage_order=STAGE_ORDER,
    gate_stages=GATE_STAGES,
    budget=BUDGET,
    budget_floor_stage=BUDGET_FLOOR_STAGE,
    determine_route=determine_route,
    budget_key=budget_key,
    provisional_emergency_signal=common_rules.has_emergency_signal,
    self_care_checklist_satisfied=never_self_care,
    skip_rule=skip_rule,
    rule_catalog=RULE_CATALOG,
    fallback_rule=common_rules.default_early_visit_rule,
    self_care_default_rule=_self_care_default_rule,
    emergency_message=EMERGENCY_MESSAGE,
    safety_signal_fields=SAFETY_SIGNAL_FIELDS,
    opportunistic_keywords=common_rules.OPPORTUNISTIC_KEYWORDS,
    field_dependencies=FIELD_DEPENDENCIES,
    derive_fields=derive_duration,
    reason_code_labels=REASON_CODE_LABELS,
    chief_complaint_field="chief_complaint",
    default_chief_complaint="Chưa rõ triệu chứng chính",
    onset_field="complaint_onset_at",
    severity_field="complaint_severity",
)
