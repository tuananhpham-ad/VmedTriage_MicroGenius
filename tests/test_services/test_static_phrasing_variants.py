"""Ba câu TĨNH của agent có mười bản diễn đạt mỗi loại — và mỗi bản vẫn phải làm đủ việc của nó.

VÌ SAO BỘ TEST NÀY ĐÁNG GIÁ HƠN VẺ NGOÀI CỦA NÓ. Thêm biến thể cho một câu là việc chép-dán, và
chép-dán là chỗ một nghĩa vụ lặng lẽ rơi mất: bản thứ bảy quên mất chỉ dẫn gọi 115, bản thứ tư quên
đòi trả lời "đúng"/"không". Lỗi đó KHÔNG bao giờ lộ ra khi chạy tay, vì bộ chọn tất định theo seed -
máy của người kiểm thử có thể không bao giờ rơi vào đúng bản hỏng. Nó chỉ lộ ra ở 1/10 số ca thật.

Vì thế mọi bài ở đây quét TOÀN BỘ tập biến thể, không lấy mẫu.

Câu số 1 là câu nguy hiểm nhất trong ba: nó chạy đúng lúc tầng model đã hỏng, tức lúc hệ thống còn ít
khả năng nhất để bắt kịp một ca cấp cứu.
"""

from __future__ import annotations

import pytest

from src.services.symptom_protocol import phrasing, session as session_mod, user_intent
from src.services.symptom_protocol.common_safety import text_safety_signals

SAFETY = text_safety_signals.CONFIRMATION_TEMPLATES
RETRACTION = session_mod.RETRACTION_TEMPLATES
UNCOOPERATIVE = user_intent.UNCOOPERATIVE_PROMPTS
ALL_SETS = {"an toàn": SAFETY, "đính chính": RETRACTION, "không hợp tác": UNCOOPERATIVE}


@pytest.mark.parametrize("name", sorted(ALL_SETS))
def test_each_set_has_ten_distinct_variants(name: str) -> None:
    """Mười bản, và mười bản KHÁC NHAU. Chép-dán sót một dòng thì tập co lại mà không ai báo."""
    variants = ALL_SETS[name]

    assert len(variants) == 10, name
    assert len(set(variants)) == 10, f"{name}: có bản trùng nhau"


@pytest.mark.parametrize("template", SAFETY)
def test_every_safety_variant_keeps_its_two_duties(template: str) -> None:
    """BÀI QUAN TRỌNG NHẤT.

    Câu xác nhận dấu hiệu nguy hiểm có đúng hai nghĩa vụ, và mất bất kỳ cái nào cũng là mất một cơ
    hội bắt ca cấp cứu - ở đúng lượt mà model đã không trả về được gì."""
    assert "{labels}" in template, "không nêu nhãn dấu hiệu thì người bệnh không biết đang hỏi gì"
    assert "115" in template, "mất chỉ dẫn gọi cấp cứu"
    assert "cơ sở y tế" in template


@pytest.mark.parametrize("template", RETRACTION)
def test_every_retraction_variant_names_the_field_and_asks_yes_no(template: str) -> None:
    """Xoá nhầm lời khai là mất dữ kiện lâm sàng, nên câu này phải nêu ĐÚNG field sắp bị xoá."""
    assert '"{label}"' in template, "nhãn field phải nằm trong ngoặc kép, nguyên văn"
    assert '"đúng"' in template and '"không"' in template, "mất hướng dẫn trả lời có/không"


@pytest.mark.parametrize("variant", UNCOOPERATIVE)
def test_every_uncooperative_variant_ends_with_the_same_yes_no_question(variant: str) -> None:
    """`stop_prompt_confirmation` đọc CÂU TRẢ LỜI, nhưng câu hỏi phải rõ ràng là có/không thì mới có
    câu trả lời để đọc. Cả mười bản dùng chung câu chốt - phần đổi chỉ là vế mở đầu."""
    assert variant.endswith("Bạn muốn dừng ở đây không?"), variant


def test_the_stop_prompt_is_recognised_by_set_not_by_string() -> None:
    """Chỗ nhận diện quyết định một việc rất nặng: coi tin nhắn kế tiếp là câu trả lời cho việc DỪNG
    PHIÊN. Một phép `==` với bản mặc định sẽ trượt 9/10 số lần, và câu "vâng, dừng đi" của người bệnh
    bị đọc như một lời khai triệu chứng."""
    for variant in UNCOOPERATIVE:
        assert user_intent.is_uncooperative_prompt(variant)
    assert not user_intent.is_uncooperative_prompt("Bạn thấy trong người thế nào?")


def test_no_variant_leads_the_patient_towards_an_answer() -> None:
    """Câu xác nhận không được là câu gợi ý.

    "Chắc bạn nhầm rồi phải không" đẩy người bệnh về phía xoá lời khai, mà xoá là chiều MẤT thông
    tin - hệ thống không được nghiêng về phía đó."""
    leading = ("chắc là", "chắc bạn", "có lẽ", "chắc hẳn", "đúng không nhỉ", "nhầm rồi")
    for name, variants in ALL_SETS.items():
        for variant in variants:
            lowered = variant.casefold()
            for phrase in leading:
                assert phrase not in lowered, f"{name}: bản dẫn dắt câu trả lời - {variant!r}"


@pytest.mark.parametrize("name", sorted(ALL_SETS))
def test_the_picker_is_deterministic_and_covers_every_variant(name: str) -> None:
    """Tất định theo seed: log đọc lại được, test không phải mock bộ ngẫu nhiên. Và không bản nào
    nằm chết trong danh sách mà không bao giờ được chọn."""
    variants = ALL_SETS[name]

    assert phrasing.pick(variants, "phien-7") == phrasing.pick(variants, "phien-7")
    assert phrasing.pick(variants, "") == variants[0], "seed rỗng phải tất định, không ngẫu nhiên"
    picked = {phrasing.pick(variants, f"phien-{i}") for i in range(400)}
    assert picked == set(variants), f"{name}: có bản không bao giờ được chọn"


def test_the_seed_changes_between_turns_of_one_session() -> None:
    """Chỉ seed theo `session_id` thì cả phiên nhận đúng một bản - đơn điệu y như trước, chỉ dời từ
    mức "mọi phiên" xuống mức "mọi lượt trong một phiên"."""
    seeds = {phrasing.turn_seed("phien-abc", turn) for turn in range(5)}

    assert len(seeds) == 5
    assert phrasing.turn_seed("phien-abc", 3) == phrasing.turn_seed("phien-abc", 3)


def test_the_safety_question_still_names_the_signal_it_asks_about() -> None:
    """Kiểm trên hàm thật chứ không chỉ trên bảng mẫu: `format` có thể được gọi sai khoá và mọi bài
    trên vẫn xanh."""
    code = text_safety_signals.TEXT_RED_FLAG_RULES[0].code
    label = text_safety_signals.rule_label(code).lower()

    for seed in range(30):
        question = text_safety_signals.confirmation_question([code], seed=f"s{seed}")
        assert label in question
        assert "115" in question
