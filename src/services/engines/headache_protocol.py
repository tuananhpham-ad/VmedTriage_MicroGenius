"""Protocol quyết định cho đau đầu theo SNNOOP10 (F09 §3.6.4)."""

from __future__ import annotations

from src.services.checklists.headache_checklist import (
    CRITICAL_SCAN_STAGE,
    EARLY_VISIT_SCAN_STAGE,
    EMERGENCY_SCAN_STAGE,
    FIELDS_BY_KEY,
    GATE_STAGES,
    QUESTION_CLUSTERS,
    STAGE_ORDER,
)
from src.services.symptom_protocol.common_safety import fields as common_fields
from src.services.symptom_protocol.common_safety import rules as common_rules
from src.services.symptom_protocol.common_safety import screening_groups as common_screening
from src.services.symptom_protocol.common_safety.emergency_message import SUSPECTED_RED_FLAG_MESSAGE
from src.services.symptom_protocol.common_safety.predicates import age_in_months, as_float, is_true
from src.services.symptom_protocol.models import QuestionCluster, RuleMatch
from src.services.symptom_protocol.protocol import SymptomProtocol

PROTOCOL_NAME = "headache"
REASON_CODE_LABELS = {
    **common_rules.REASON_CODE_LABELS,
    "RF-80": "Đau đầu đột ngột dữ dội kiểu thunderclap",
    "RF-81": "Đau đầu mới, khác thường hoặc tăng dần",
    "RF-82": "Đau đầu thay đổi theo tư thế hoặc kèm rối loạn thị giác",
    "RF-83": "Đau đầu trong bối cảnh nguy cơ cao",
    "RF-84": "Đau đầu sau chấn thương đầu gần đây",
}


def determine_route(answers: dict[str, object]) -> str:
    if is_true(answers.get("thunderclap_onset")) or is_true(answers.get("head_trauma_recent")):
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


def r_ha_01(answers: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if is_true(answers.get("thunderclap_onset")):
        return RuleMatch("R-HA-01", ("RF-80",), "EMERGENCY", "now")
    return None


def r_ha_02(answers: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    age = age_in_months(answers)
    headache_present = (
        as_float(answers.get("headache_severity")) is not None
        or is_true(answers.get("severe_headache"))
        or is_true(answers.get("headache_different_from_usual"))
        or is_true(answers.get("headache_progressive"))
    )
    older_new_headache = age is not None and age > 50 * 12 and headache_present
    if older_new_headache or is_true(answers.get("headache_progressive")) or is_true(answers.get("headache_different_from_usual")):
        return RuleMatch("R-HA-02", ("RF-81",), "EARLY_VISIT", "within_4h")
    return None


def r_ha_03(answers: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if is_true(answers.get("headache_positional")) or is_true(answers.get("visual_disturbance")):
        return RuleMatch("R-HA-03", ("RF-82",), "EARLY_VISIT", "within_4h")
    return None


def r_ha_04(answers: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    temp = as_float(answers.get("temp_c"))
    if (
        is_true(answers.get("is_pregnant"))
        or is_true(answers.get("immunocompromised"))
        or (temp is not None and temp >= 38.0)
    ):
        return RuleMatch("R-HA-04", ("RF-83",), "EARLY_VISIT", "within_4h")
    return None


def r_ha_05(answers: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if is_true(answers.get("head_trauma_recent")):
        return RuleMatch("R-HA-05", ("RF-84",), "EARLY_VISIT", "within_4h")
    return None


def self_care_checklist_satisfied(answers: dict[str, object]) -> bool:
    if common_rules.has_emergency_signal(answers):
        return False
    severity = as_float(answers.get("headache_severity"))
    if severity is None or severity > 3:
        return False
    for key in (
        "thunderclap_onset", "headache_different_from_usual", "headache_progressive",
        "headache_positional", "visual_disturbance", "head_trauma_recent",
    ):
        if answers.get(key) != "false":
            return False
    return is_true(answers.get("can_return_for_followup"))


def _self_care_default(_answers: dict[str, object]) -> RuleMatch:
    return RuleMatch("R-S-06", (), "SELF_CARE", "monitor")


RULE_CATALOG = (
    *common_rules.EMERGENCY_RULES, r_ha_01, common_rules.r_e_21,
    *common_rules.EARLY_VISIT_RULES, r_ha_02, r_ha_03, r_ha_04, r_ha_05, common_rules.r_g_01,
)
SCREENING_GROUPS = (
    common_screening.critical_scan_groups(CRITICAL_SCAN_STAGE)
    + common_screening.emergency_scan_groups(EMERGENCY_SCAN_STAGE)
    + common_screening.early_visit_scan_groups(EARLY_VISIT_SCAN_STAGE)
    + common_screening.risk_context_groups("4")
)

HEADACHE_PROTOCOL = SymptomProtocol(
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
        "thunderclap_onset", "focal_neuro_deficit", "new_confusion", "seizure_occurred", "neck_stiffness", "temp_c",
    ),
    opportunistic_keywords=common_rules.OPPORTUNISTIC_KEYWORDS, screening_groups=SCREENING_GROUPS,
    confirm_before_retract=common_fields.CONFIRM_BEFORE_RETRACT,
    reason_code_labels=REASON_CODE_LABELS, default_chief_complaint="Đau đầu",
    severity_field="headache_severity",
)
