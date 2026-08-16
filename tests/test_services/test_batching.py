"""Hỏi gộp 2-3 cụm vào một tin nhắn (`symptom_protocol/batching.py`).

Toàn bộ THUẦN, không LLM: `next_batch` là hàm xác định, và đó chính là lý do việc "được gộp hay
không" được chặn bằng CODE chứ không phó mặc cho model tự quyết trong prompt.
"""

from __future__ import annotations

from src.services.checklists.fever_checklist import CLUSTERS_BY_ID
from src.services.engines.fever_protocol import FEVER_PROTOCOL
from src.services.symptom_protocol import batching

ADULT = {"age_value": "30", "age_unit": "year", "sex": "male", "reporter_type": "self"}
STAGE_3A, STAGE_3B = FEVER_PROTOCOL.gate_stages


def _batch(stage: str, first_id: str, answers: dict | None = None, **kwargs):
    return batching.next_batch(
        FEVER_PROTOCOL, stage, dict(answers or ADULT), CLUSTERS_BY_ID[first_id], **kwargs
    )


# --- khi nào được gộp ---------------------------------------------------------------------------


def test_narrative_stage_batches_the_next_few_clusters():
    groups = _batch("2", "Q2-01")

    assert 2 <= len(groups) <= batching.MAX_CLUSTERS_PER_BATCH
    assert groups[0].id == "Q2-01"


def test_gate_stage_is_never_batched():
    """Ràng buộc an toàn, không phải phân công module: CS §3.3A bắt xác nhận riêng từng dấu hiệu
    nguy kịch theo script chuẩn."""
    assert _batch(STAGE_3A, "Q3-01") == ()
    assert _batch(STAGE_3B, "Q3-14") == ()


def test_stage_after_the_gates_is_not_batched():
    """Đo được trên ca H1: gộp ở Stage 4/5 làm hội thoại DÀI thêm một lượt mỗi gói, vì mỗi cụm ở đó
    hỏi một con số/danh sách riêng mà một câu trả lời gộp hiếm khi điền đủ."""
    assert _batch("4", "Q4-06") == ()
    assert _batch("5", "Q5-01") == ()


def test_cluster_bound_to_a_screening_group_is_left_alone():
    """`Q4-00` chia sẻ field với các cụm trong nhóm sàng lọc rủi ro - nó đã có đường rút ngắn riêng."""
    assert _batch("4", "Q4-00") == ()


def test_batch_stops_at_the_length_cap_even_when_more_clusters_are_available():
    """Stage 2 còn nhiều cụm hơn trần, nên cắt phải xảy ra thật chứ không phải "vừa đủ nên không cắt"."""
    uncapped = _batch("2", "Q2-01", max_clusters=99)

    assert len(uncapped) > batching.MAX_CLUSTERS_PER_BATCH
    assert len(_batch("2", "Q2-01")) == batching.MAX_CLUSTERS_PER_BATCH


def test_no_batch_when_only_one_cluster_is_left():
    """Gói một cụm không phải là gói - phải rơi về đường hỏi lẻ như cũ."""
    answers = dict(ADULT, fever_onset_at="2026-08-15", rigors="false")
    remaining = frozenset({"Q2-03", "Q2-04", "Q2-05"})

    assert _batch("2", "Q2-01", answers, asked_ids=remaining) == ()


# --- chống vòng lặp -----------------------------------------------------------------------------


def test_cluster_already_read_out_in_a_batch_is_asked_alone_next_time():
    """Chốt chống vòng lặp. Sổ sách của `session` ghi theo mã GÓI, còn `next_cluster` duyệt theo mã
    cụm THẬT - không có chặn này thì gói y hệt được dựng lại mãi (đo được: hội thoại không kết thúc
    sau 60 lượt)."""
    first = _batch("2", "Q2-01")
    packed = batching.batch_cluster("2", first)

    again = _batch("2", "Q2-01", asked_ids=frozenset({packed.id}))

    assert again == ()


def test_batch_id_round_trips_its_component_ids():
    packed = batching.batch_cluster("2", _batch("2", "Q2-01"))

    assert batching.is_batch(packed)
    assert batching._components_of(packed.id) == tuple(c.id for c in _batch("2", "Q2-01"))


# --- cụm tổng hợp -------------------------------------------------------------------------------


def test_packed_cluster_carries_every_field_of_its_parts():
    parts = _batch("2", "Q2-01")
    packed = batching.batch_cluster("2", parts)

    for part in parts:
        assert set(part.fields) <= set(packed.fields)
    assert len(packed.fields) == len(set(packed.fields))  # không lặp field


def test_packed_question_reads_as_a_sentence_not_a_prompt_fragment():
    """`script_hint` của gói còn là văn bản dự phòng khi LLM lỗi, nên phải đọc lọt tai với người
    bệnh chứ không được là một mẩu prompt lộ ra ngoài."""
    parts = _batch("2", "Q2-01")
    question = batching.batch_question(parts)

    assert question.startswith(batching.BATCH_INTRO)
    for part in parts:
        assert part.script_hint in question


def test_packed_cluster_is_not_a_batch_negation_cluster():
    """Gộp ở đây là hỏi THẲNG. Bật cờ phủ định-cả-cụm sẽ cho phép một câu "không" đóng sạch mọi
    field của 3 cụm khác nhau - đúng lỗ hổng C1 ở quy mô lớn."""
    packed = batching.batch_cluster("2", _batch("2", "Q2-01"))

    assert packed.batch_negation is False
