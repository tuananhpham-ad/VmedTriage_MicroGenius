"""Cụm của protocol này bị đem chạy với protocol kia — lỗi production `KeyError: 'complaint_onset_at'`.

ĐƯỜNG ĐI CỦA LỖI, đo được chứ không suy đoán: lượt phát hiện đổi protocol gọi `run_turn` với protocol
CŨ, nên `result.next_cluster` sinh ra từ protocol cũ; ngay sau đó `session.protocol_name` mới được
gán sang tên mới. Lượt kế tiếp ghép cụm cũ với protocol mới, và mọi chỗ tra `protocol.fields_by_key[key]`
vỡ ngay lúc dựng prompt - trước cả lời gọi model, tức ngoài khối `try` mà `extract_turn` dựa vào để
giữ lời hứa "không bao giờ ném".

VÌ SAO NÓ KHÔNG LỘ RA SỚM HƠN: ba protocol (`abdominal`, `breathing`, `general`) khai `complaint_onset_at`,
ba protocol còn lại (`fever`, `chest_pain`, `headache`) thì không. Chỉ những cặp chuyển giữa hai nhóm
đó mới vỡ, nên nó trông như lỗi ngẫu nhiên - và trên UI thì nó chỉ là một dòng "Không xử lý được tin
nhắn." không nói gì về nguyên nhân.

HAI LỚP, KIỂM RIÊNG:

1. `test_extract_turn_survives_a_foreign_cluster` - lời hứa của `extract_turn`. Đây là lớp NGẮT MÁU:
   dù định tuyến có sai kiểu gì thì lượt của người bệnh cũng không được chết giữa chừng.
2. `test_a_foreign_cluster_is_replaced_not_carried` - chữa gốc. Cụm lệch phải bị thay bằng cụm đúng
   của protocol đang chạy, và tuyệt đối KHÔNG được thay bằng `None`: `None` giữa phiên rơi vào
   `FAIL_CLOSED_NO_CLUSTER`, đẩy người bệnh sang bàn giao điều dưỡng vì một lỗi nội bộ.
"""

from __future__ import annotations

import pytest

from src.services.engines.abdominal_protocol import ABDOMINAL_PROTOCOL
from src.services.engines.chest_pain_protocol import CHEST_PAIN_PROTOCOL
from src.services.engines.fever_protocol import FEVER_PROTOCOL
from src.services.engines.headache_protocol import HEADACHE_PROTOCOL
from src.services.infra import provider_router
from src.services.symptom_protocol import intake_agent, registry

AB_02 = next(cluster for cluster in ABDOMINAL_PROTOCOL.clusters if cluster.id == "AB-02")
"""Cụm hỏi kiểu khởi phát cơn đau bụng - đúng cụm đang hỏi lúc lỗi nổ trên production."""

WITHOUT_THE_FIELD = (FEVER_PROTOCOL, CHEST_PAIN_PROTOCOL, HEADACHE_PROTOCOL)


def test_the_field_gap_between_protocols_is_real() -> None:
    """Neo giả định của cả bộ test này vào data thật.

    Nếu một ngày `fever` khai thêm `complaint_onset_at` thì các bài dưới vẫn xanh trong khi không còn
    kiểm gì cả - bài này fail trước và nói rõ vì sao."""
    assert "complaint_onset_at" in ABDOMINAL_PROTOCOL.fields_by_key
    for protocol in WITHOUT_THE_FIELD:
        assert "complaint_onset_at" not in protocol.fields_by_key, protocol.name


@pytest.fixture
def offline_model(monkeypatch):
    """Không lượt nào ở đây được chạm tới provider thật.

    Bản đầu của bài test này gọi thẳng `extract_turn` và nó đi ra Gemini thật - vừa đốt quota vừa làm
    kết quả phụ thuộc mạng, trên đúng một bài test mà thứ cần kiểm (dựng prompt có vỡ không) xảy ra
    TRƯỚC lời gọi model."""
    def _fake(messages, **kwargs):
        return provider_router.CompletionResult(
            text='{"answer_quality": "partial"}', provider="fake", model="fake",
        )

    monkeypatch.setattr(provider_router, "complete", _fake)
    return _fake


@pytest.mark.parametrize("protocol", WITHOUT_THE_FIELD, ids=[p.name for p in WITHOUT_THE_FIELD])
def test_extract_turn_survives_a_foreign_cluster(protocol, offline_model) -> None:
    """`extract_turn` hứa trong docstring là KHÔNG BAO GIỜ ném. Dựng prompt nằm ngoài khối `try` của
    nó, nên đây từng là lỗ thủng của lời hứa đó - và lỗ thủng nằm đúng trên đường phản hồi bệnh nhân."""
    extraction = intake_agent.extract_turn(protocol, AB_02, "đau từ từ", answers={})

    assert extraction is not None
    # Field protocol không biết thì không trích được - đó là hệ quả chấp nhận được. Điều không chấp
    # nhận được là cả lượt chết.
    assert "complaint_onset_at" not in extraction.cluster_fields


def test_a_foreign_cluster_is_replaced_not_carried(monkeypatch) -> None:
    """Chữa GỐC: cụm lệch bị thay bằng cụm thật của protocol đang chạy."""
    from src.services.symptom_protocol.session import ProtocolSessionStore

    store = ProtocolSessionStore(default_protocol=None, persist=None)
    session = store.create(None)
    session.protocol_name = FEVER_PROTOCOL.name
    session.stage = FEVER_PROTOCOL.stage_order[0]
    session.current_cluster = AB_02

    chosen = store._cluster_for_protocol(session, FEVER_PROTOCOL)

    assert chosen is not None, "None giữa phiên = fail-closed, phản ứng nặng hơn hẳn sự cố"
    assert chosen is not AB_02
    assert all(key in FEVER_PROTOCOL.fields_by_key for key in chosen.fields)
    assert session.current_cluster is chosen, "phải ghi lại, nếu không lượt sau lệch y hệt"


def test_a_matching_cluster_is_left_completely_alone() -> None:
    """Đường thuận không được đụng tới. Một guard tự ý chọn lại cụm ở lượt bình thường sẽ làm người
    bệnh bị hỏi nhảy cóc mà không lỗi nào nổ ra để ai biết."""
    from src.services.symptom_protocol.session import ProtocolSessionStore

    store = ProtocolSessionStore(default_protocol=None, persist=None)
    session = store.create(None)
    session.protocol_name = ABDOMINAL_PROTOCOL.name
    session.stage = AB_02.stage
    session.current_cluster = AB_02

    assert store._cluster_for_protocol(session, ABDOMINAL_PROTOCOL) is AB_02


def test_a_synthetic_screening_cluster_is_not_treated_as_foreign() -> None:
    """Cụm sàng lọc (`SCREEN-*`) dựng tại chỗ nên KHÔNG nằm trong `protocol.clusters`.

    Đây là lý do phép kiểm phải theo FIELD chứ không theo mã cụm: lọc theo mã sẽ vứt oan cụm sàng lọc
    ở mọi lượt, tức phá đúng cơ chế phủ định gộp - một lỗi nặng hơn lỗi đang sửa."""
    from src.services.symptom_protocol import screening
    from src.services.symptom_protocol.session import ProtocolSessionStore

    groups = screening.groups_for_stage(FEVER_PROTOCOL, FEVER_PROTOCOL.critical_scan_stage)
    probe = screening.probe_cluster(FEVER_PROTOCOL, FEVER_PROTOCOL.critical_scan_stage, groups)

    store = ProtocolSessionStore(default_protocol=None, persist=None)
    session = store.create(None)
    session.protocol_name = FEVER_PROTOCOL.name
    session.stage = FEVER_PROTOCOL.critical_scan_stage
    session.current_cluster = probe

    assert probe.id not in {cluster.id for cluster in FEVER_PROTOCOL.clusters}
    assert store._cluster_for_protocol(session, FEVER_PROTOCOL) is probe


def test_every_protocol_pair_can_hand_a_cluster_over_without_crashing() -> None:
    """Quét TOÀN BỘ cặp protocol thay vì chỉ cặp đã gặp lỗi.

    `complaint_onset_at` chỉ là field đầu tiên bị bắt gặp. Bài này tìm mọi cặp (protocol đang chạy,
    cụm của protocol khác) mà việc chuyển giao còn làm vỡ - nếu có cặp nào chưa được guard che, nó
    phải lộ ra ở đây chứ không phải trên máy người bệnh."""
    from src.services.symptom_protocol.session import ProtocolSessionStore

    store = ProtocolSessionStore(default_protocol=None, persist=None)
    for running in registry.PROTOCOL_REGISTRY.values():
        for source in registry.PROTOCOL_REGISTRY.values():
            if source.name == running.name:
                continue
            for cluster in source.clusters:
                session = store.create(None)
                session.protocol_name = running.name
                session.stage = running.stage_order[0]
                session.current_cluster = cluster

                chosen = store._cluster_for_protocol(session, running)

                if chosen is not None:
                    assert all(key in running.fields_by_key for key in chosen.fields), (
                        f"{running.name} nhận cụm {cluster.id} của {source.name} "
                        f"-> chọn lại ra {chosen.id} vẫn còn field lạ"
                    )
