"""Kiểm tầng chuẩn hoá văn bản người bệnh: bỏ dấu, viết tắt, khớp mờ.

TRỌNG TÂM LÀ DƯƠNG TÍNH GIẢ, không phải độ phủ. Một red-flag bắt hụt sẽ được các tầng sau (LLM, điều
dưỡng) có cơ hội bắt lại; một red-flag bắt nhầm đẩy thẳng ca lên EMERGENCY và làm loãng hàng đợi -
lặp lại đủ nhiều thì người trực bắt đầu bỏ qua cảnh báo, và lúc đó cả tầng an toàn mất tác dụng.
"""

import pytest

from src.services.engines.red_flag_text_rules import detect_text_red_flags
from src.services.text_norm import expand_chat_shorthand, fold_diacritics

# ---------- bỏ dấu ----------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Khó thở", "kho tho"),
        ("ĐAU NGỰC", "dau nguc"),
        ("Đột ngột", "dot ngot"),
        ("bất tỉnh", "bat tinh"),
        ("", ""),
    ],
)
def test_fold_diacritics(raw: str, expected: str) -> None:
    assert fold_diacritics(raw) == expected


def test_fold_handles_d_stroke_in_both_cases() -> None:
    """`đ`/`Đ` KHÔNG bị NFD tách, nên phải thay tay. Đây là ca mà một bản chép lệch sẽ bỏ sót."""
    assert fold_diacritics("Đau đầu") == "dau dau"


def test_every_lane_folds_identically() -> None:
    """Sáu chỗ gọi phải cho cùng kết quả trên phần LÕI - đó là lý do gom về một hàm.

    Phần đuôi riêng (gộp khoảng trắng, bỏ dấu câu) vẫn được phép khác nhau, nên chỉ so trên chuỗi
    không có khoảng trắng thừa và không có dấu câu."""
    from src.services.agents.intake_agent import strip_diacritics
    from src.services.symptom_protocol.common_safety.rules import _fold_text
    from src.services.symptom_protocol.non_clinical import _fold

    sample = "Đột ngột KHÓ THỞ dữ dội"
    assert strip_diacritics(sample) == _fold_text(sample) == _fold(sample) == fold_diacritics(sample)


# ---------- viết tắt ----------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ko tho duoc", "khong tho duoc"),
        ("k an duoc gi", "khong an duoc gi"),
        ("bs oi em dau nguc", "bac si oi em dau nguc"),
    ],
)
def test_expand_chat_shorthand(raw: str, expected: str) -> None:
    assert expand_chat_shorthand(raw) == expected


@pytest.mark.parametrize("word", ["hong", "khong", "kho", "khoc", "keo"])
def test_shorthand_never_touches_real_vietnamese_words(word: str) -> None:
    """`họng` bỏ dấu ra `hong`. Nếu bảng viết tắt có `hong -> khong` thì "đau họng" thành "đau không".

    Đây là ca đã thật sự lọt vào bản nháp của bảng này và bị bắt lúc đo."""
    assert expand_chat_shorthand(word) == word


def test_shorthand_replaces_whole_tokens_only() -> None:
    """`k -> khong` áp theo chuỗi con sẽ phá mọi từ có chữ k."""
    assert expand_chat_shorthand("kho khan keo dai") == "kho khan keo dai"


# ---------- tích hợp vào tầng red-flag ----------


def test_chat_shorthand_in_a_red_flag_phrase_is_still_caught() -> None:
    codes = {rule.code for rule, _ in detect_text_red_flags("benh nhan ko tho duoc")}
    assert "not_breathing" in codes


BENIGN_MESSAGES = [
    "toi hoi to mo ve thuoc nay",
    "Tôi bị cảm nhẹ, vẫn ăn uống và sinh hoạt bình thường.",
    "Em bị đau họng 2 hôm nay, không sốt, vẫn nuốt được.",
    "toi bi dau hong va ho khan, ko sot",
    "Cháu nhà em hơi sổ mũi, ăn ngủ bình thường, chơi vui vẻ.",
    "Tôi thở nhanh hơn bình thường một chút sau khi chạy bộ.",
    "kho tho nhanh hon khi leo cau thang nhung nghi mot lat la het",
    "Tôi hơi lo âu, khó ngủ mấy hôm nay.",
    "Da tôi hơi hồng lên sau khi tắm nước nóng.",
    "bi dau bung nhe sau khi an do lanh, di ngoai 1 lan",
    "Mắt tôi hơi mờ khi đọc sách lâu, nghỉ thì đỡ.",
    "Tôi bị ngứa nhẹ ở tay, không sưng, không khó thở.",
    "chan toi hoi lanh vao buoi toi nhung khong dau",
    "Tôi ho có đờm trong, không ra máu.",
]


@pytest.mark.parametrize("message", BENIGN_MESSAGES)
def test_benign_messages_raise_no_red_flag(message: str) -> None:
    """Bộ cụm không được bắn trên câu lành tính.

    Bộ 13 câu này được viết ra để đo dương tính giả của một lớp khớp gần-đúng (đã bỏ - xem docstring
    `detect_text_red_flags`). Giữ lại vì nó vẫn có giá trị độc lập: đây là lưới chặn cho chính bộ cụm,
    và nó phủ đúng những câu dễ bắt nhầm nhất - phủ định ("không sưng, không khó thở"), mức độ nhẹ
    ("thở nhanh hơn bình thường một chút"), và những từ mà bỏ dấu xong trông giống cụm red-flag
    ("đau họng", "hơi hồng lên", "tò mò")."""
    assert detect_text_red_flags(message) == []


def test_a_near_miss_phrase_does_not_match() -> None:
    """"khó thở nhanh" và "khó thở nặng" chỉ lệch một từ nhưng là hai tình trạng khác nhau, và chỉ
    một trong hai là red-flag. Đây là ranh giới mà khớp chính xác giữ được còn khớp mờ thì không."""
    assert detect_text_red_flags("kho tho nhanh hon khi leo cau thang") == []
