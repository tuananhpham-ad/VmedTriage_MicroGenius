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
