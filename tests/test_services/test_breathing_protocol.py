"""Đối chiếu từng dòng mapping của protocol khó thở F09."""

import pytest

from src.services.engines.breathing_protocol import BREATHING_PROTOCOL
from src.services.symptom_protocol import rule_engine


@pytest.mark.parametrize(
    ("answers", "level", "rule_id"),
    (
        ({"dyspnea_at_rest": "true"}, "EARLY_VISIT", "R-BR-01"),
        ({"dyspnea_onset_mode": "sudden", "chest_pain": "true"}, "EMERGENCY", "R-BR-02"),
        ({"functional_impact": "marked"}, "EARLY_VISIT", "R-BR-03"),
        ({"leg_swelling": "true"}, "EARLY_VISIT", "R-BR-04"),
        ({"temp_c": "38.2", "breathing_difficulty": "mild"}, "EARLY_VISIT", "R-BR-05"),
    ),
)
def test_breathing_mapping(answers: dict[str, object], level: str, rule_id: str) -> None:
    result = rule_engine.evaluate(BREATHING_PROTOCOL, answers)
    assert result.triage_level == level
    assert rule_id in result.triggered_rules


def test_breathing_self_care_mapping_is_reachable() -> None:
    answers = {
        "breathing_difficulty": "mild", "dyspnea_onset_mode": "gradual",
        "dyspnea_at_rest": "false", "functional_impact": "mild",
        "chest_pain": "false", "hemoptysis": "false", "leg_swelling": "false",
        "rapid_breathing": "false", "can_return_for_followup": "true",
    }
    result = rule_engine.evaluate(BREATHING_PROTOCOL, answers)
    assert result.triage_level == "SELF_CARE"
    assert result.triggered_rules == ("R-S-05",)
