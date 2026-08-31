"""Bất biến DỮ LIỆU của mọi protocol: field bắt buộc phải có đường thu thập (§8, §1 mục 8).

Bài này bắt một lớp lỗi IM LẶNG mà không test nào khác chạm tới: khai một field là tier M0/M1 rồi
quên viết cụm câu hỏi cho nó. Không lỗi nào nổ ra - hệ thống chạy bình thường, chỉ là field đó vĩnh
viễn `unknown`, `mandatory_unasked` không bao giờ về 0, và gate độ phủ của §8 không bao giờ qua được.

Đo được ngày 2026-08-19: `GENERIC_PROTOCOL` khai `diarrhea` là M1 mà không cụm nào hỏi tới - 9/10
phiên generic trong log ngày 17/08 đều thiếu đúng field đó. Generic là protocol mà 4/5 nhóm triệu
chứng MVP đang rơi vào, nên nó không phải một góc khuất.
"""

from __future__ import annotations

import pytest

from src.services.symptom_protocol import registry
from src.services.symptom_protocol.protocol import SymptomProtocol
from src.services.symptom_protocol.stage_machine import MANDATORY_TIERS

PROTOCOLS = sorted(registry.PROTOCOL_REGISTRY.items())


@pytest.mark.parametrize("name,protocol", PROTOCOLS, ids=[name for name, _ in PROTOCOLS])
def test_every_mandatory_field_has_a_cluster_that_asks_it(name: str, protocol: SymptomProtocol):
    """Field M0/M1 phải nằm trong `fields` của ít nhất MỘT cụm, hoặc được khai là DẪN XUẤT.

    Hai lối thoát duy nhất, và cả hai đều phải TƯỜNG MINH:

    - có cụm hỏi nó;
    - nằm trong `protocol.derived_field_keys` (được TÍNH ra từ field khác, vd
      `complaint_duration_days` từ `complaint_onset_at`).

    Suy "field không thuộc cụm nào thì chắc là dẫn xuất" KHÔNG dùng được - đó đúng là dấu hiệu của
    lỗi thật, và một quy tắc suy đoán như vậy sẽ nuốt luôn cả lỗi lẫn thiết kế."""
    asked = {key for cluster in protocol.clusters for key in cluster.fields}
    orphans = sorted(
        key
        for key, spec in protocol.fields_by_key.items()
        if spec.tier in MANDATORY_TIERS
        and key not in asked
        and key not in protocol.derived_field_keys
    )

    assert orphans == [], (
        f"protocol {name!r} khai {orphans} là tier M0/M1 nhưng không cụm nào hỏi tới. "
        "Hoặc thêm cụm hỏi, hoặc hạ tier, hoặc khai vào `derived_field_keys` nếu nó được tính ra."
    )


@pytest.mark.parametrize("name,protocol", PROTOCOLS, ids=[name for name, _ in PROTOCOLS])
def test_declared_derived_fields_actually_exist(name: str, protocol: SymptomProtocol):
    """`derived_field_keys` là lối thoát khỏi bài trên, nên nó phải được canh: khai một key gõ sai
    vào đó sẽ âm thầm không miễn trừ gì cả, mà cũng không ai biết."""
    unknown = sorted(key for key in protocol.derived_field_keys if key not in protocol.fields_by_key)

    assert unknown == [], f"protocol {name!r} khai `derived_field_keys` chứa field không tồn tại: {unknown}"


@pytest.mark.parametrize("name,protocol", PROTOCOLS, ids=[name for name, _ in PROTOCOLS])
def test_a_declared_derived_field_is_never_also_asked_by_a_cluster(name: str, protocol: SymptomProtocol):
    """Một field vừa được TÍNH vừa được HỎI là hai nguồn sự thật cho cùng một ô - đúng lớp lỗi mà
    reducer tồn tại để tránh. Nếu thật sự cần cả hai thì đó là quyết định phải viết ra, không phải
    một trùng lặp lọt qua review."""
    asked = {key for cluster in protocol.clusters for key in cluster.fields}
    both = sorted(set(protocol.derived_field_keys) & asked)

    assert both == [], f"protocol {name!r}: {both} vừa được tính vừa được hỏi"


# --- Chiều NGƯỢC LẠI: cụm/nhóm trỏ tới field có thật không (2026-08-26) ----------------------------
#
# Các bài trên kiểm chiều `field -> cụm` ("field M0/M1 có ai hỏi tới không"). Chiều còn lại KHÔNG có
# ai canh, và chính nó mới là chiều làm SẬP request: `intake_agent._field_specs` tra
# `protocol.fields_by_key[key]` cho từng field của cụm đang hỏi, nên một mã field gõ sai ném
# `KeyError` giữa lượt, `routes.py` bắt lại thành 500 "Không xử lý được tin nhắn." và người bệnh
# không bao giờ đi qua được cụm đó.
#
# Đã xảy ra thật ngày 2026-08-26: `abdominal` cụm `AB-02` khai `complaint_onset_at` (field riêng của
# `general`), `breathing` cụm `BR-01`/`BR-03` khai `complaint_onset_at`/`diaphoresis`/`palpitations`.
# Cả ba lọt qua toàn bộ 804 test đang xanh.


@pytest.mark.parametrize("name,protocol", PROTOCOLS, ids=[name for name, _ in PROTOCOLS])
def test_every_cluster_field_exists_in_the_field_registry(name: str, protocol: SymptomProtocol):
    """Mọi field mà một cụm hỏi phải có `FieldSpec`. Thiếu = `KeyError` giữa lượt hội thoại."""
    unknown = sorted(
        {
            f"{cluster.id}.{key}"
            for cluster in protocol.clusters
            for key in cluster.fields
            if key not in protocol.fields_by_key
        }
    )

    assert unknown == [], (
        f"protocol {name!r} có cụm hỏi field không tồn tại: {unknown}. "
        "`_field_specs` sẽ ném KeyError và lượt đó trả 500 cho người bệnh."
    )


@pytest.mark.parametrize("name,protocol", PROTOCOLS, ids=[name for name, _ in PROTOCOLS])
def test_safety_signal_fields_all_exist(name: str, protocol: SymptomProtocol):
    """`safety_signal_fields` được nối thẳng vào schema trích xuất mỗi lượt - cùng đường vỡ như trên."""
    unknown = sorted(key for key in protocol.safety_signal_fields if key not in protocol.fields_by_key)

    assert unknown == [], f"protocol {name!r} khai `safety_signal_fields` không tồn tại: {unknown}"


@pytest.mark.parametrize("name,protocol", PROTOCOLS, ids=[name for name, _ in PROTOCOLS])
def test_field_dependencies_reference_real_fields(name: str, protocol: SymptomProtocol):
    """Cả khoá lẫn field phụ thuộc phải có thật, nếu không phần phụ thuộc đó âm thầm không chạy."""
    unknown = sorted(
        {
            key
            for parent, children in (protocol.field_dependencies or {}).items()
            for key in (parent, *children)
            if key not in protocol.fields_by_key
        }
    )

    assert unknown == [], f"protocol {name!r} khai `field_dependencies` trỏ tới field không tồn tại: {unknown}"


@pytest.mark.parametrize("name,protocol", PROTOCOLS, ids=[name for name, _ in PROTOCOLS])
def test_screening_groups_reference_real_clusters(name: str, protocol: SymptomProtocol):
    """Mã cụm lạ trong `ScreeningGroup` bị `clusters_of` bỏ qua IM LẶNG - nhóm mất một cụm mà không
    ai biết, và câu sàng lọc gộp đóng thiếu."""
    cluster_ids = {cluster.id for cluster in protocol.clusters}
    unknown = sorted(
        {
            f"{group.id}.{cluster_id}"
            for group in protocol.screening_groups
            for cluster_id in group.cluster_ids
            if cluster_id not in cluster_ids
        }
    )

    assert unknown == [], f"protocol {name!r} có `ScreeningGroup` trỏ tới cụm không tồn tại: {unknown}"
