"""Ý bị bỏ qua trong một lượt hỏi GỘP (§4.8 + §7.4 `_guidance/what_to_do_next.md`).

Yêu cầu ban đầu là "hỏi một đống câu, người dùng bỏ qua cái nào thì cho cái đấy là False luôn". Phần
đó chỉ được thực hiện cho tier O/H. Lý do phải khác cho M0/M1/C là một LỖI IM LẶNG, và đó là thứ cả
file này canh: suy `false` cho một field an toàn tạo ra phiếu ghi "người bệnh phủ nhận ngất" trong
khi CHƯA AI hỏi họ về ngất - điều dưỡng đọc phiếu đó không có cách nào biết sự khác nhau.
"""

from __future__ import annotations

import pytest

from src.services.engines.fever_protocol import FEVER_PROTOCOL
from src.services.symptom_protocol import batching, stage_machine
from src.services.symptom_protocol.models import QuestionCluster

ADULT: dict[str, object] = {
    "age_value": "30", "age_unit": "year", "sex": "male", "reporter_type": "self",
}

# Field thật của fever, chọn để phủ đúng bốn tier cần phân biệt. Đọc tier từ protocol thay vì viết
# cứng vào test: nếu một field bị đổi tier trong tài liệu lâm sàng thì test phải đi theo, không được
# tiếp tục khẳng định một điều không còn đúng.
MANDATORY_FIELD = "rigors"          # M0
SAFETY_FIELD = "worse_after_defervescence"  # M0 + nằm trong `safety_signal_fields`
OPTIONAL_FIELD = "cough"            # O
HANDOFF_FIELD = "antibiotic_current"  # H
PROTOCOL_FIELD = "antipyretic_drug"   # C


def test_the_fields_this_file_relies_on_still_have_the_tiers_it_assumes():
    """Canh chính giả định của file. Không có test này thì việc đổi tier một field sẽ làm mọi bài
    dưới đây xanh vì lý do sai."""
    tiers = FEVER_PROTOCOL.fields_by_key
    assert tiers[MANDATORY_FIELD].tier in stage_machine.MANDATORY_TIERS
    assert tiers[SAFETY_FIELD].tier in stage_machine.MANDATORY_TIERS
    assert SAFETY_FIELD in FEVER_PROTOCOL.safety_signal_fields
    assert tiers[OPTIONAL_FIELD].tier == "O"
    assert tiers[HANDOFF_FIELD].tier == "H"
    assert tiers[PROTOCOL_FIELD].tier == "C"


def _batch_cluster(*fields: str) -> QuestionCluster:
    return batching.batch_cluster("4", (QuestionCluster("Q-TEST", "4", fields, script_hint="hỏi gộp"),))


def _defaults(*fields: str, answers: dict[str, object] | None = None, information_gain: bool = True):
    return batching.skipped_field_defaults(
        FEVER_PROTOCOL, _batch_cluster(*fields), dict(answers or ADULT),
        information_gain=information_gain,
    )


# --- §7.4 mục 1: chỉ tier O/H mới được suy `false` -----------------------------------------------


def test_optional_and_handoff_fields_skipped_in_a_batch_become_false():
    """Đúng như yêu cầu: chi phí sai thấp, lợi ích tốc độ thật."""
    assert _defaults(OPTIONAL_FIELD, HANDOFF_FIELD) == {
        OPTIONAL_FIELD: "false", HANDOFF_FIELD: "false",
    }


def test_a_mandatory_field_skipped_in_a_batch_stays_unknown():
    """Im lặng không phải phủ định - và ở tier M0/M1 thì đây đúng là chỗ đắt nhất để suy diễn."""
    assert MANDATORY_FIELD not in _defaults(MANDATORY_FIELD, OPTIONAL_FIELD)


def test_a_safety_field_is_never_inferred_even_if_its_tier_changes():
    """Hai lớp chặn chồng lên nhau, cố ý: tier VÀ `safety_signal_fields`. Field an toàn bị hạ tier
    trong một lần sửa checklist vẫn không được suy diễn."""
    assert SAFETY_FIELD not in _defaults(SAFETY_FIELD, OPTIONAL_FIELD)


def test_a_protocol_specific_field_stays_unknown_and_is_only_reported_as_missing():
    """Tier C: giữ `unknown`, không hỏi lại - ghi vào `missing_information` là đủ."""
    assert PROTOCOL_FIELD not in _defaults(PROTOCOL_FIELD, OPTIONAL_FIELD)


# --- điều kiện kích hoạt --------------------------------------------------------------------------


def test_nothing_is_inferred_when_the_patient_answered_none_of_the_batch():
    """Im lặng TOÀN PHẦN có thể là chưa đọc, chưa hiểu, hoặc đã bỏ cuộc - không đọc được thành "những
    cái kia thì không". Chỉ khi họ đã trả lời một phần thì phần bỏ qua mới có nghĩa."""
    assert _defaults(OPTIONAL_FIELD, HANDOFF_FIELD, information_gain=False) == {}


def test_a_field_the_patient_already_answered_is_left_alone():
    answers = dict(ADULT, cough="true")

    assert OPTIONAL_FIELD not in _defaults(OPTIONAL_FIELD, HANDOFF_FIELD, answers=answers)


def test_a_single_cluster_turn_is_never_touched():
    """Cơ chế này chỉ áp cho lượt hỏi GỘP: một cụm hỏi riêng mà người bệnh không trả lời thì đường
    lùi đúng là hỏi lại, không phải suy ra giá trị."""
    plain = QuestionCluster("Q5-01", "5", (OPTIONAL_FIELD, HANDOFF_FIELD), script_hint="hỏi lẻ")

    assert batching.is_batch(plain) is False


# --- §7.4 mục 4: trần ý mỗi lượt ------------------------------------------------------------------


@pytest.mark.parametrize("stage,first_id", [("2", "Q2-01")])
def test_a_real_batch_never_exceeds_the_idea_cap(stage: str, first_id: str):
    from src.services.checklists.fever_checklist import CLUSTERS_BY_ID

    clusters = batching.next_batch(FEVER_PROTOCOL, stage, dict(ADULT), CLUSTERS_BY_ID[first_id])
    packed = batching.batch_cluster(stage, clusters)

    assert len(packed.fields) <= batching.MAX_FIELDS_PER_BATCH
