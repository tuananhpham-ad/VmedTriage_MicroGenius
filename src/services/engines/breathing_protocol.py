"""Protocol quyết định cho khó thở (F09 §3.6.3)."""

from __future__ import annotations

from src.services.checklists.breathing_checklist import (
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
from src.services.symptom_protocol.common_safety.predicates import as_float, is_true
from src.services.symptom_protocol.models import QuestionCluster, RuleMatch
from src.services.symptom_protocol.protocol import SymptomProtocol

PROTOCOL_NAME = "breathing"
REASON_CODE_LABELS = {
    **common_rules.REASON_CODE_LABELS,
    "RF-70": "Khó thở ngay cả khi nghỉ",
    "RF-71": "Khó thở đột ngột kèm đau ngực hoặc ho ra máu",
    "RF-72": "Khó thở ảnh hưởng rõ hoạt động thường ngày",
    "RF-73": "Khó thở kèm sưng chân",
    "RF-74": "Sốt kèm khó thở",
}


def determine_route(answers: dict[str, object]) -> str:
    if answers.get("dyspnea_onset_mode") == "sudden" or is_true(answers.get("dyspnea_at_rest")):
        return "ROUTE_HIGH_RISK"
    return "ROUTE_STANDARD"


BUDGET = {"EMERGENCY": (3, 6), "ROUTE_HIGH_RISK": (8, 14), "ROUTE_STANDARD": (7, 12)}
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


def r_br_01(answers: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if is_true(answers.get("dyspnea_at_rest")):
        return RuleMatch("R-BR-01", ("RF-70",), "EARLY_VISIT", "within_4h")
    return None


def r_br_02(answers: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    sudden = answers.get("dyspnea_onset_mode") == "sudden"
    if sudden and (is_true(answers.get("chest_pain")) or is_true(answers.get("hemoptysis"))):
        return RuleMatch("R-BR-02", ("RF-71",), "EMERGENCY", "now")
    return None


def r_br_03(answers: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if answers.get("functional_impact") == "marked" or answers.get("activity_vs_baseline") == "markedly_reduced":
        return RuleMatch("R-BR-03", ("RF-72",), "EARLY_VISIT", "within_4h")
    return None


def r_br_04(answers: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if is_true(answers.get("leg_swelling")):
        return RuleMatch("R-BR-04", ("RF-73",), "EARLY_VISIT", "within_4h")
    return None


def r_br_05(answers: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    temp = as_float(answers.get("temp_c"))
    if temp is not None and temp >= 38.0 and answers.get("breathing_difficulty") in {"mild", "severe"}:
        return RuleMatch("R-BR-05", ("RF-74",), "EARLY_VISIT", "within_24h")
    return None


def self_care_checklist_satisfied(answers: dict[str, object]) -> bool:
    if common_rules.has_emergency_signal(answers):
        return False
    if answers.get("breathing_difficulty") != "mild" or answers.get("dyspnea_onset_mode") != "gradual":
        return False
    if answers.get("dyspnea_at_rest") != "false" or answers.get("functional_impact") not in {"none", "mild"}:
        return False
    for key in ("chest_pain", "hemoptysis", "leg_swelling", "rapid_breathing"):
        if answers.get(key) != "false":
            return False
    return is_true(answers.get("can_return_for_followup"))


def _self_care_default(_answers: dict[str, object]) -> RuleMatch:
    return RuleMatch("R-S-05", (), "SELF_CARE", "monitor")


RULE_CATALOG = (
    *common_rules.EMERGENCY_RULES, r_br_02, common_rules.r_e_21,
    *common_rules.EARLY_VISIT_RULES, r_br_01, r_br_03, r_br_04, r_br_05, common_rules.r_g_01,
)
SCREENING_GROUPS = (
    common_screening.critical_scan_groups(CRITICAL_SCAN_STAGE)
    + common_screening.emergency_scan_groups(EMERGENCY_SCAN_STAGE)
    + common_screening.early_visit_scan_groups(EARLY_VISIT_SCAN_STAGE)
    + common_screening.risk_context_groups("4")
)

BREATHING_PROTOCOL = SymptomProtocol(
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
        "breathing_difficulty", "dyspnea_at_rest", "chest_pain", "hemoptysis", "temp_c",
    ),
    opportunistic_keywords=common_rules.OPPORTUNISTIC_KEYWORDS, screening_groups=SCREENING_GROUPS,
    reason_code_labels=REASON_CODE_LABELS, default_chief_complaint="Khó thở",
    onset_field="complaint_onset_at", severity_field="breathing_difficulty",
)
