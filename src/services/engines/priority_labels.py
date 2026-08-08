from __future__ import annotations

from src.models.schemas import TriagePriority

# Xếp hạng độ ưu tiên dùng để sắp xếp hàng đợi (số nhỏ hơn = ưu tiên xử lý trước).
PRIORITY_RANK: dict[TriagePriority, int] = {
    TriagePriority.EMERGENCY: 0,
    TriagePriority.URGENT: 1,
    TriagePriority.MANUAL_REVIEW: 1,
    TriagePriority.ROUTINE: 2,
    TriagePriority.SELF_CARE: 3,
}

# Nhãn tiếng Việt hiển thị cho bệnh nhân/điều dưỡng (Cấp cứu / Khám sớm / Tự theo dõi),
# ánh xạ từ enum TriagePriority nội bộ (giữ nguyên enum để không phá vỡ code hiện có).
PRIORITY_LABEL_VI: dict[TriagePriority, str] = {
    TriagePriority.EMERGENCY: "Cấp cứu",
    TriagePriority.URGENT: "Khám sớm",
    TriagePriority.ROUTINE: "Khám sớm",
    TriagePriority.SELF_CARE: "Tự theo dõi",
    TriagePriority.MANUAL_REVIEW: "Cần điều dưỡng xem xét thủ công",
}

_LABEL_TO_PRIORITY: dict[str, TriagePriority] = {label: priority for priority, label in PRIORITY_LABEL_VI.items()}


def priority_label_vi(priority: TriagePriority | str | None) -> str | None:
    """Trả về nhãn tiếng Việt cho một mức ưu tiên (chấp nhận cả enum lẫn string)."""
    if priority is None:
        return None
    if isinstance(priority, str):
        try:
            priority = TriagePriority(priority)
        except ValueError:
            return priority
    return PRIORITY_LABEL_VI.get(priority, priority.value)


def normalize_priority_value(value: str) -> str:
    """Chuẩn hoá một chuỗi priority (English enum hoặc nhãn tiếng Việt) thành giá trị enum hợp lệ."""
    candidate = (value or "").strip()
    try:
        return TriagePriority(candidate).value
    except ValueError:
        pass
    if candidate in _LABEL_TO_PRIORITY:
        return _LABEL_TO_PRIORITY[candidate].value
    raise ValueError(f"Giá trị mức ưu tiên không hợp lệ: {value!r}")
