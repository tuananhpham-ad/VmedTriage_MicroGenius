"""Đối chiếu từng dòng mapping SNNOOP10 của protocol đau đầu F09."""

import pytest

from src.services.engines.headache_protocol import HEADACHE_PROTOCOL
from src.services.symptom_protocol import rule_engine


@pytest.mark.parametrize(
    ("answers", "level", "rule_id"),
    (
        ({"thunderclap_onset": "true"}, "EMERGENCY", "R-HA-01"),
        ({"headache_progressive": "true"}, "EARLY_VISIT", "R-HA-02"),
        ({"visual_disturbance": "true"}, "EARLY_VISIT", "R-HA-03"),
        ({"is_pregnant": "true"}, "EARLY_VISIT", "R-HA-04"),
        ({"head_trauma_recent": "true"}, "EARLY_VISIT", "R-HA-05"),
    ),
)
def test_headache_mapping(answers: dict[str, object], level: str, rule_id: str) -> None:
    result = rule_engine.evaluate(HEADACHE_PROTOCOL, answers)
    assert result.triage_level == level
    assert rule_id in result.triggered_rules


def test_headache_self_care_mapping_is_reachable() -> None:
    answers = {
        "headache_severity": "2", "thunderclap_onset": "false",
        "headache_different_from_usual": "false", "headache_progressive": "false",
        "headache_positional": "false", "visual_disturbance": "false",
        "head_trauma_recent": "false", "can_return_for_followup": "true",
    }
    result = rule_engine.evaluate(HEADACHE_PROTOCOL, answers)
    assert result.triage_level == "SELF_CARE"
    assert result.triggered_rules == ("R-S-06",)
