"""Đối chiếu từng dòng mapping của protocol đau ngực F09."""

import pytest

from src.services.engines.chest_pain_protocol import CHEST_PAIN_PROTOCOL
from src.services.symptom_protocol import rule_engine


@pytest.mark.parametrize(
    ("answers", "level", "rule_id"),
    (
        ({"chest_pain": "true", "chest_pain_duration_min": "10", "chest_pain_character": "pressure", "age_value": "55", "age_unit": "year"}, "EMERGENCY", "R-CP-01"),
        ({"chest_pain": "true", "breathing_difficulty": "mild"}, "EMERGENCY", "R-CP-02"),
        ({"chest_pain": "true", "chest_pain_duration_min": "10"}, "EARLY_VISIT", "R-CP-03"),
        ({"chest_pain": "true", "recent_surgery_30d": "true"}, "EARLY_VISIT", "R-CP-04"),
        ({"chest_pain_worsening": "true"}, "EARLY_VISIT", "R-CP-05"),
        ({"chest_pain": "true", "temp_c": "38.2"}, "EARLY_VISIT", "R-CP-06"),
        ({"chest_pain_radiation": "back", "chest_pain_duration_min": "10"}, "EMERGENCY", "R-CP-07"),
    ),
)
def test_chest_pain_mapping(answers: dict[str, object], level: str, rule_id: str) -> None:
    result = rule_engine.evaluate(CHEST_PAIN_PROTOCOL, answers)
    assert result.triage_level == level
    assert rule_id in result.triggered_rules


def test_chest_pain_self_care_mapping_is_reachable() -> None:
    answers = {
        "chest_pain": "true", "age_value": "30", "age_unit": "year", "reporter_type": "self",
        "consciousness_level": "alert", "chest_pain_severity": "2",
        "chest_pain_pattern": "intermittent", "chest_pain_duration_min": "0.5",
        "chest_pain_worsening": "false", "breathing_difficulty": "none",
        "diaphoresis": "false", "palpitations": "false", "hemoptysis": "false",
        "recent_surgery_30d": "false", "immobility_or_long_travel": "false",
        "cardiac_risk_factors": ["none"], "can_return_for_followup": "true",
    }
    result = rule_engine.evaluate(CHEST_PAIN_PROTOCOL, answers)
    assert result.triage_level == "SELF_CARE"
    assert result.triggered_rules == ("R-S-03",)
