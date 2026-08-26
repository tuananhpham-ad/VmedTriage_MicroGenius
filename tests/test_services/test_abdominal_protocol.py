"""Đối chiếu từng dòng mapping của protocol đau bụng F09."""

import pytest

from src.services.engines.abdominal_protocol import ABDOMINAL_PROTOCOL
from src.services.symptom_protocol import rule_engine


@pytest.mark.parametrize(
    ("answers", "level", "rule_id"),
    (
        ({"abdominal_pain_severity": "severe", "abdominal_pain_duration_hours": "1.5"}, "EMERGENCY", "R-AB-01"),
        ({"abdominal_pain_severity": "moderate", "abdominal_pain_pattern": "continuous", "abdominal_pain_duration_hours": "3"}, "EARLY_VISIT", "R-AB-02"),
        ({"urinary_retention_gt_4h": "true"}, "EARLY_VISIT", "R-AB-03"),
        ({"temp_c": "39.5", "age_value": "30", "age_unit": "year"}, "EARLY_VISIT", "R-AB-04"),
        ({"abdominal_distension": "true"}, "EARLY_VISIT", "R-AB-05"),
    ),
)
def test_abdominal_mapping(answers: dict[str, object], level: str, rule_id: str) -> None:
    result = rule_engine.evaluate(ABDOMINAL_PROTOCOL, answers)
    assert result.triage_level == level
    assert rule_id in result.triggered_rules


@pytest.mark.parametrize(
    ("temp", "age", "risk"),
    (("39.5", "30", {}), ("38.4", "61", {}), ("38.2", "30", {"immunocompromised": "true"})),
)
def test_abdominal_fever_thresholds(temp: str, age: str, risk: dict[str, object]) -> None:
    answers = {"temp_c": temp, "age_value": age, "age_unit": "year", **risk}
    result = rule_engine.evaluate(ABDOMINAL_PROTOCOL, answers)
    assert "R-AB-04" in result.triggered_rules


def test_abdominal_self_care_mapping_is_reachable() -> None:
    answers = {
        "abdominal_pain_severity": "mild", "abdominal_pain_onset_mode": "gradual",
        "abdominal_pain_pattern": "intermittent", "gi_bleeding": "false",
        "urinary_retention_gt_4h": "false", "abdominal_distension": "false",
        "jaundice_new": "false", "can_return_for_followup": "true",
    }
    result = rule_engine.evaluate(ABDOMINAL_PROTOCOL, answers)
    assert result.triage_level == "SELF_CARE"
    assert result.triggered_rules == ("R-S-04",)
