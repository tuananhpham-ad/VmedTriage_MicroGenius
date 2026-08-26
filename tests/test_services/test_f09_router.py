"""Router, phủ chéo và phân định đa nhóm của F09."""

import pytest

from src.services.engines.breathing_protocol import BREATHING_PROTOCOL
from src.services.engines.chest_pain_protocol import CHEST_PAIN_PROTOCOL
from src.services.symptom_protocol import ranking, registry
from src.services.symptom_protocol.common_safety import screening_groups


def test_registry_contains_six_protocols() -> None:
    assert set(registry.PROTOCOL_REGISTRY) == {
        "fever", "general", "chest_pain", "abdominal", "breathing", "headache",
    }


@pytest.mark.parametrize(
    ("answers", "expected"),
    (
        ({"temp_c": 39, "breathing_difficulty": "severe"}, "breathing"),
        ({"chest_pain": "true", "breathing_difficulty": "severe"}, "chest_pain"),
        ({"severe_headache": "true", "abdominal_pain_severity": "moderate"}, "headache"),
        ({"abdominal_pain_severity": "moderate", "temp_c": 39}, "abdominal"),
    ),
)
def test_router_priority(answers: dict[str, object], expected: str) -> None:
    assert registry.select_protocol(answers) == expected


def test_explicit_primary_group_can_select_lower_priority_candidate() -> None:
    answers = {
        "severe_headache": "true", "abdominal_pain_severity": "moderate",
        "primary_symptom_group": "abdominal",
    }
    assert registry.select_protocol(answers) == "abdominal"


def test_chest_breathing_cross_cluster_is_identical_and_asked_once_per_protocol() -> None:
    chest = [cluster for cluster in CHEST_PAIN_PROTOCOL.clusters if cluster.id == "CP-03"]
    breathing = [cluster for cluster in BREATHING_PROTOCOL.clusters if cluster.id == "BR-03"]
    assert len(chest) == len(breathing) == 1
    assert chest[0].fields == breathing[0].fields
    assert chest[0].script_hint == breathing[0].script_hint


def test_disambiguation_probe_is_static_and_does_not_close_a_clinical_cluster() -> None:
    cluster = screening_groups.routing_disambiguation_cluster(("headache", "abdominal"))
    assert cluster.id == screening_groups.ROUTING_DISAMBIGUATION_ID
    assert cluster.fields == ("primary_symptom_group",)
    assert cluster.id not in {item.id for item in registry.PROTOCOL_REGISTRY["headache"].clusters}


def test_keyword_relevance_follows_unextracted_user_text() -> None:
    protocol = CHEST_PAIN_PROTOCOL
    cp_01 = next(cluster for cluster in protocol.clusters if cluster.id == "CP-01")
    cp_02 = next(cluster for cluster in protocol.clusters if cluster.id == "CP-02")
    context = ranking.RankingContext(recent_text="Đau lan xuống cánh tay trái")
    assert ranking.score_cluster(protocol, cp_01, {}, context) > ranking.score_cluster(protocol, cp_02, {}, context)
