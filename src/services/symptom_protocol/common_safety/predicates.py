"""Vị từ đọc `answers` dùng chung cho MỌI protocol - không biết bệnh nào, không quyết định gì.

Tách ra khỏi `fever_protocol.py` vì rule đỏ phổ quát (`common_safety/rules.py`) cần đúng những phép
đọc này, và một bản sao thứ hai của `as_float`/`age_in_months` chính là chỗ hai protocol lệch nhau âm
thầm: `_as_float` đã là nguyên nhân của một lỗi an toàn thật (10 rule theo nhiệt độ kiểm
`isinstance(x, (int, float))` trong khi `_coerce_enum` biến mọi giá trị thành CHUỖI, nên "sốt 40°C kèm
rối loạn tri giác" bị xếp nhầm xuống "khám sớm").

Hành vi chép NGUYÊN VẸN từ bản fever trước khi tách - kể cả những chỗ có thể làm chặt hơn (vd
`as_float` không nhận dấu phẩy thập phân). Refactor này không được đổi kết luận triage của bất kỳ ca
nào; muốn siết thì làm ở một thay đổi riêng, có test riêng.
"""

from __future__ import annotations

_MONTHS_PER_YEAR = 12.0
_DAYS_PER_MONTH = 30.0


def is_filled(value: object) -> bool:
    return value is not None and value != "unknown" and value != ""


def is_true(value: object) -> bool:
    return value is True or value == "true"


def is_in(value: object, allowed: frozenset[str]) -> bool:
    return isinstance(value, str) and value in allowed


def array_has_any(value: object, items: frozenset[str]) -> bool:
    if not isinstance(value, (list, tuple, set)):
        return False
    return any(item in items for item in value)


def array_has_non_empty_excluding(value: object, excluded: frozenset[str]) -> bool:
    if not isinstance(value, (list, tuple, set)):
        return False
    return any(item not in excluded for item in value)


def as_float(value: object) -> float | None:
    """Đọc số từ `answers` chấp nhận CẢ chuỗi.

    BẮT BUỘC dùng hàm này thay cho `isinstance(x, (int, float))` trong rule: trên đường agent mọi giá
    trị không-tri-state đi qua `intake_agent._coerce_enum` và về `answers` dưới dạng CHUỖI ("39.0").
    Rule nào kiểm kiểu số trực tiếp sẽ IM LẶNG không bao giờ khớp."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def age_in_months(answers: dict[str, object]) -> float | None:
    """Tuổi quy về THÁNG - mọi ngưỡng tuổi trong rule đều tính bằng tháng để không rule nào phải tự
    phân nhánh theo `age_unit`."""
    value = answers.get("age_value")
    unit = answers.get("age_unit")
    if not is_filled(value) or not is_filled(unit):
        return None
    numeric = as_float(value)
    if numeric is None:
        return None
    if unit == "day":
        return numeric / _DAYS_PER_MONTH
    if unit == "month":
        return numeric
    if unit == "year":
        return numeric * _MONTHS_PER_YEAR
    return None
