"""Người bệnh đính chính "tôi không sốt" thì mọi cụm đặc điểm sốt phải bị bỏ qua.

Lỗi thật trong transcript `logs/fever/a421eb5f-...` (xem `_guidance/need_to_check_agent.md`): người
dùng nói "à tôi nhầm, tôi không bị sốt" nhưng hệ thống vẫn hỏi tiếp "sốt bao lâu rồi", "có rét run
không", "đã uống thuốc hạ sốt chưa" — vì Stage 2 không có cụm nào khai báo skip condition.

Test ở tầng `stage_machine` (thuần rule, không LLM) nên chạy nhanh và không phụ thuộc model.
"""

from __future__ import annotations

import pytest

from src.services.engines.fever_protocol import FEVER_PROTOCOL
from src.services.symptom_protocol import stage_machine

_FEVER_DETAIL_CLUSTERS = ("Q1-02", "Q1-03", "Q2-01", "Q2-02", "Q2-03", "Q2-04", "Q2-05")

# Hồ sơ đủ để không bị vướng skip condition theo tuổi/giới của các cụm khác.
_BASE = {"age_value": "30", "age_unit": "year", "sex": "male", "reporter_type": "self"}


@pytest.mark.parametrize("no_fever", [{"fever_reported": "false"}, {"fever_status": "none"}])
@pytest.mark.parametrize("cluster_id", _FEVER_DETAIL_CLUSTERS)
def test_fever_detail_clusters_are_skipped_once_no_fever_is_confirmed(no_fever, cluster_id):
    answers = {**_BASE, **no_fever}
    cluster = next(c for c in FEVER_PROTOCOL.clusters if c.id == cluster_id)
    assert FEVER_PROTOCOL.skip_rule(cluster, answers) is True


@pytest.mark.parametrize("cluster_id", ["Q1-02", "Q2-01", "Q2-02", "Q2-03", "Q2-04"])
def test_fever_detail_clusters_are_still_asked_while_fever_is_unknown(cluster_id):
    """`unknown` KHÔNG phải "không sốt".

    Nếu coi `unknown` là phủ định thì toàn bộ Stage 2 bị skip ngay lượt đầu khi chưa hỏi gì — hệ
    thống sẽ không bao giờ khai thác được đặc điểm sốt của ca sốt thật."""
    cluster = next(c for c in FEVER_PROTOCOL.clusters if c.id == cluster_id)
    assert FEVER_PROTOCOL.skip_rule(cluster, dict(_BASE)) is False


def test_stage_2_is_walked_past_entirely_when_no_fever():
    """Không còn cụm nào của Stage 2 được chọn — đây mới là điều người dùng nhìn thấy."""
    answers = {**_BASE, "fever_reported": "false"}
    assert stage_machine.next_cluster(FEVER_PROTOCOL, "2", answers) is None


def test_stage_2_still_has_questions_for_a_real_fever_case():
    answers = {**_BASE, "fever_reported": "true", "fever_status": "objective"}
    cluster = stage_machine.next_cluster(FEVER_PROTOCOL, "2", answers)
    assert cluster is not None
    assert cluster.id == "Q2-01"  # "Bắt đầu sốt từ khi nào"


def test_red_flag_clusters_are_not_skipped_by_a_no_fever_correction():
    """Rút lại lời khai sốt KHÔNG được làm im lặng màn quét dấu hiệu nguy hiểm.

    Không sốt không có nghĩa là không nguy hiểm — co giật, tím tái, li bì vẫn phải hỏi. Q3-13 là
    ngoại lệ đã chốt sau transcript 2026-08-22: chỉ hỏi đau bụng khi người bệnh đã khai dấu hiệu bụng,
    để ca sốt thuần không bị chuyển mạch sang bụng."""
    answers = {**_BASE, "fever_reported": "false"}
    for cluster in FEVER_PROTOCOL.clusters:
        if cluster.stage == "3A" and cluster.id != "Q3-13":
            assert FEVER_PROTOCOL.skip_rule(cluster, answers) is False


def test_abdominal_red_flag_cluster_is_skipped_for_plain_fever():
    answers = {**_BASE, "fever_reported": "true", "fever_status": "subjective"}
    cluster = next(c for c in FEVER_PROTOCOL.clusters if c.id == "Q3-13")
    assert FEVER_PROTOCOL.skip_rule(cluster, answers) is True


@pytest.mark.parametrize(
    "abdominal_evidence",
    [
        {"abdominal_pain_severity": "mild"},
        {"abdominal_pain_severity": "severe"},
        {"abdominal_guarding": "true"},
        {"abdominal_pain_location": "hạ vị"},
    ],
)
def test_abdominal_red_flag_cluster_is_asked_when_abdominal_symptom_was_reported(abdominal_evidence):
    answers = {**_BASE, "fever_reported": "true", "fever_status": "subjective", **abdominal_evidence}
    cluster = next(c for c in FEVER_PROTOCOL.clusters if c.id == "Q3-13")
    assert FEVER_PROTOCOL.skip_rule(cluster, answers) is False
