"""Protocol quyết định cho đau bụng (F09 §3.6.2)."""

from __future__ import annotations

from src.services.checklists.abdominal_checklist import (
    CRITICAL_SCAN_STAGE,
    EARLY_VISIT_SCAN_STAGE,
    EMERGENCY_SCAN_STAGE,
    FIELDS_BY_KEY,
    GATE_STAGES,
    QUESTION_CLUSTERS,
    STAGE_ORDER,
)
from src.services.symptom_protocol.common_safety import rules as common_rules
from src.services.symptom_protocol.common_safety import screening_groups as common_screening
from src.services.symptom_protocol.common_safety.emergency_message import SUSPECTED_RED_FLAG_MESSAGE
from src.services.symptom_protocol.common_safety.predicates import age_in_months, array_has_any, as_float, is_true
from src.services.symptom_protocol.models import QuestionCluster, RuleMatch
from src.services.symptom_protocol.protocol import SymptomProtocol

PROTOCOL_NAME = "abdominal"
SEVERE_PAIN_HOURS = 1.0
MODERATE_CONTINUOUS_HOURS = 2.0

REASON_CODE_LABELS = {
    **common_rules.REASON_CODE_LABELS,
    "RF-60": "Đau bụng dữ dội kéo dài trên 1 giờ",
    "RF-61": "Đau bụng mức vừa liên tục trên 2 giờ",
    "RF-62": "Bí tiểu trên 4 giờ",
    "RF-63": "Sốt cao kèm đau bụng",
    "RF-64": "Bụng chướng hoặc vàng da mới",
}


def _duration_hours(answers: dict[str, object]) -> float | None:
    return as_float(answers.get("abdominal_pain_duration_hours"))


def _high_fever_for_context(answers: dict[str, object]) -> bool:
    temp = as_float(answers.get("temp_c"))
    if temp is None:
        return False
    age = age_in_months(answers)
    high_risk = is_true(answers.get("immunocompromised")) or array_has_any(
        answers.get("chronic_conditions"), frozenset({"diabetes"}),
    )
    if high_risk:
        return temp > 38.1
    if age is not None and age > 60 * 12:
        return temp > 38.3
    return temp > 39.4


def determine_route(answers: dict[str, object]) -> str:
    if _high_fever_for_context(answers) or is_true(answers.get("immunocompromised")):
        return "ROUTE_HIGH_RISK"
    return "ROUTE_STANDARD"


BUDGET = {"EMERGENCY": (3, 6), "ROUTE_HIGH_RISK": (9, 15), "ROUTE_STANDARD": (8, 13)}
BUDGET_FLOOR_STAGE = "3"


def budget_key(answers: dict[str, object], route: str, known_triage_level: str | None = None) -> str:
    del answers
    if known_triage_level == "EMERGENCY":
        return "EMERGENCY"
    return route if route in BUDGET else "ROUTE_STANDARD"


def skip_rule(cluster: QuestionCluster, answers: dict[str, object]) -> bool:
    if cluster.id in {"Q4-01", "Q4-01b", "Q4-02"}:
        return answers.get("sex") == "male" or answers.get("is_pregnant") == "false"
    return False


def r_ab_01(answers: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    duration = _duration_hours(answers)
    if answers.get("abdominal_pain_severity") == "severe" and duration is not None and duration > SEVERE_PAIN_HOURS:
        return RuleMatch("R-AB-01", ("RF-60",), "EMERGENCY", "now")
    return None


def r_ab_02(answers: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    duration = _duration_hours(answers)
    if (
        answers.get("abdominal_pain_severity") == "moderate"
        and answers.get("abdominal_pain_pattern") == "continuous"
        and duration is not None
        and duration > MODERATE_CONTINUOUS_HOURS
    ):
        return RuleMatch("R-AB-02", ("RF-61",), "EARLY_VISIT", "within_4h")
    return None


def r_ab_03(answers: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if is_true(answers.get("urinary_retention_gt_4h")):
        return RuleMatch("R-AB-03", ("RF-62",), "EARLY_VISIT", "within_4h")
    return None


def r_ab_04(answers: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if _high_fever_for_context(answers):
        return RuleMatch("R-AB-04", ("RF-63",), "EARLY_VISIT", "within_4h")
    return None


def r_ab_05(answers: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if is_true(answers.get("abdominal_distension")) or is_true(answers.get("jaundice_new")):
        return RuleMatch("R-AB-05", ("RF-64",), "EARLY_VISIT", "within_24h")
    return None


def self_care_checklist_satisfied(answers: dict[str, object]) -> bool:
    if common_rules.has_emergency_signal(answers):
        return False
    if answers.get("abdominal_pain_severity") != "mild":
        return False
    if answers.get("abdominal_pain_onset_mode") != "gradual" or answers.get("abdominal_pain_pattern") != "intermittent":
        return False
    for key in ("gi_bleeding", "urinary_retention_gt_4h", "abdominal_distension", "jaundice_new"):
        if answers.get(key) != "false":
            return False
    return is_true(answers.get("can_return_for_followup"))


def _self_care_default(_answers: dict[str, object]) -> RuleMatch:
    return RuleMatch("R-S-04", (), "SELF_CARE", "monitor")


RULE_CATALOG = (
    *common_rules.EMERGENCY_RULES, r_ab_01, common_rules.r_e_21,
    *common_rules.EARLY_VISIT_RULES, r_ab_02, r_ab_03, r_ab_04, r_ab_05, common_rules.r_g_01,
)
SCREENING_GROUPS = (
    common_screening.critical_scan_groups(CRITICAL_SCAN_STAGE)
    + common_screening.emergency_scan_groups(EMERGENCY_SCAN_STAGE)
    + common_screening.early_visit_scan_groups(EARLY_VISIT_SCAN_STAGE)
    + common_screening.risk_context_groups("4")
)

ABDOMINAL_PROTOCOL = SymptomProtocol(
    name=PROTOCOL_NAME, fields_by_key=FIELDS_BY_KEY, clusters=QUESTION_CLUSTERS,
    stage_order=STAGE_ORDER, gate_stages=GATE_STAGES,
    critical_scan_stage=CRITICAL_SCAN_STAGE, emergency_scan_stage=EMERGENCY_SCAN_STAGE,
    early_visit_scan_stage=EARLY_VISIT_SCAN_STAGE, budget=BUDGET,
    budget_floor_stage=BUDGET_FLOOR_STAGE, determine_route=determine_route, budget_key=budget_key,
    provisional_emergency_signal=common_rules.has_emergency_signal,
    self_care_checklist_satisfied=self_care_checklist_satisfied, skip_rule=skip_rule,
    rule_catalog=RULE_CATALOG, fallback_rule=common_rules.default_early_visit_rule,
    self_care_default_rule=_self_care_default, patient_red_flag_message=SUSPECTED_RED_FLAG_MESSAGE,
    safety_signal_fields=common_rules.EMERGENCY_TRI_STATE_FIELDS + (
        "abdominal_pain_severity", "abdominal_guarding", "gi_bleeding", "temp_c",
    ),
    opportunistic_keywords=common_rules.OPPORTUNISTIC_KEYWORDS, screening_groups=SCREENING_GROUPS,
    reason_code_labels=REASON_CODE_LABELS, default_chief_complaint="Đau bụng",
    onset_field="complaint_onset_at", severity_field="abdominal_pain_severity",
)
