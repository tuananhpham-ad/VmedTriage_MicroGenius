"""Evidence-grounded documented emergency-rule gate shared by production and evaluation.

The gate does not classify triage itself.  It asks an LLM only to extract a deliberately
narrow set of documented red-flag facts, then passes those facts to the existing deterministic
generic/fever rule engine.  It is best-effort and must never delay the synchronous protocol
rule-engine escalation path.
"""

from __future__ import annotations

from typing import Any

from src.services.engines.fever_protocol import FEVER_PROTOCOL
from src.services.engines.generic_protocol import GENERIC_PROTOCOL
from src.services.infra.provider_router import LLMCredential
from src.services.symptom_protocol import intake_agent, registry, rule_engine
from src.services.symptom_protocol.models import QuestionCluster

_EMERGENCY_RULE_FIELDS = (
    "age_value", "age_unit", "fever_reported", "fever_status", "temp_c", "temp_site",
    "consciousness_level", "new_confusion", "seizure_occurred", "seizure_active_now",
    "seizure_features", "neck_stiffness", "bulging_fontanelle", "photophobia",
    "focal_neuro_deficit", "breathing_difficulty", "cyanosis", "stridor_or_drooling",
    "chest_indrawing", "nasal_flaring_grunting", "spo2_percent", "cold_clammy_skin",
    "capillary_refill_ge_3s", "urine_output", "feeding_intake", "vomiting_severity",
    "non_blanching_rash", "mucosal_bleeding", "gi_bleeding", "abdominal_pain_severity",
    "abdominal_guarding", "hypothermia_reported", "worse_after_defervescence",
    "known_neutropenia", "immunocompromise_cause", "malaria_risk_area", "travel_history_12m",
    "is_pregnant", "postpartum_6w", "obstetric_red_flags",
)


def rule_gate_cluster() -> QuestionCluster:
    """Return the narrow fact schema consumed by documented emergency rules."""
    missing = [key for key in _EMERGENCY_RULE_FIELDS if key not in FEVER_PROTOCOL.fields_by_key]
    if missing:
        raise RuntimeError(f"Rule-gate fields missing from fever protocol: {missing}")
    return QuestionCluster("OFFLINE-RULE-GATE", "3A", _EMERGENCY_RULE_FIELDS)


def extract_and_evaluate(text: str, credential: LLMCredential) -> dict[str, Any]:
    """Extract documented facts and return the deterministic protocol result.

    The returned payload is suitable for internal audit only.  Callers choose their own
    error policy; an extraction that completes but is not LLM-valid returns ``available=False``.
    """
    extraction = intake_agent.extract_turn(
        FEVER_PROTOCOL,
        rule_gate_cluster(),
        text,
        credential=credential,
        evidence="unasked",
    )
    if not extraction.llm_ok:
        return {"available": False, "error": "fact extraction failed"}

    answers = extraction.all_fields
    protocol_name = registry.select_protocol(answers)
    protocol = FEVER_PROTOCOL if protocol_name == FEVER_PROTOCOL.name else GENERIC_PROTOCOL
    result = rule_engine.evaluate(protocol, answers)
    return {
        "available": True,
        "protocol": protocol.name,
        "triage_level": result.triage_level,
        "emergency": result.triage_level == "EMERGENCY",
        "reason_codes": list(result.reason_codes),
        "triggered_rules": list(result.triggered_rules),
        "answers": {key: value for key, value in answers.items() if value not in (None, "unknown")},
    }
