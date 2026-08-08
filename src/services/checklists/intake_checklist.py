"""Checklist intake MOCK cho demo hỏi-đáp (Feature #1, phần thu thập thông tin).

PHẠM VI: đây là checklist DEMO do đội dự án tự đặt để chạy thử luồng hỏi-đáp - CHƯA phải bộ trường
chuẩn theo protocol Bộ Y tế VN/WHO. Không dùng để kết luận mức độ ưu tiên thật.

Khác với `REQUIRED_FIELDS_BY_SYMPTOM_GROUP` trong src/config.py (checklist theo từng nhóm bệnh, phục
vụ ProtocolTriageEngine), checklist này là bộ trường hành chính + triệu chứng chung, áp dụng cho mọi
ca, dùng riêng cho demo intake conversation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChecklistField:
    key: str
    label: str
    required: bool
    hint: str
    """Gợi ý ngữ nghĩa cho LLM biết trường này cần trích xuất cái gì (đưa vào prompt extraction)."""


INTAKE_CHECKLIST: tuple[ChecklistField, ...] = (
    ChecklistField(
        key="patient_name",
        label="Họ và tên",
        required=True,
        hint="Tên người bệnh. Nếu người nhắn là người nhà khai hộ thì lấy tên NGƯỜI BỆNH, không phải tên người nhắn.",
    ),
    ChecklistField(
        key="age",
        label="Tuổi",
        required=True,
        hint="Tuổi của người bệnh, dạng số hoặc mô tả (vd '5 tuổi', '62'). Không suy đoán từ ngữ cảnh.",
    ),
    ChecklistField(
        key="onset",
        label="Thời điểm phát bệnh",
        required=True,
        hint="Triệu chứng bắt đầu từ khi nào (vd 'sáng nay', '3 ngày trước', '20/07').",
    ),
    ChecklistField(
        key="main_symptom",
        label="Triệu chứng chính",
        required=True,
        hint="Triệu chứng khiến người bệnh khó chịu nhất (vd 'đau bụng', 'sốt', 'khó thở').",
    ),
    ChecklistField(
        key="symptom_progression",
        label="Diễn tiến triệu chứng",
        required=True,
        hint="Triệu chứng đang nặng lên, giảm đi, hay không đổi kể từ lúc bắt đầu.",
    ),
    ChecklistField(
        key="consciousness",
        label="Tình trạng ý thức",
        required=True,
        hint="Tỉnh táo bình thường / li bì / lơ mơ / đã từng ngất. Đây là trường an toàn, không được suy đoán.",
    ),
    ChecklistField(
        key="associated_symptoms",
        label="Triệu chứng kèm theo",
        required=True,
        hint="Các triệu chứng đi kèm ngoài triệu chứng chính (vd 'nôn, tiêu chảy'). Nếu người bệnh nói rõ là KHÔNG có gì kèm theo thì ghi 'không có'.",
    ),
    ChecklistField(
        key="medical_history",
        label="Tiền sử bệnh / thuốc đang dùng",
        required=False,
        hint="Bệnh nền, thuốc đang dùng, dị ứng. Không bắt buộc.",
    ),
)

FIELDS_BY_KEY: dict[str, ChecklistField] = {field.key: field for field in INTAKE_CHECKLIST}
REQUIRED_KEYS: tuple[str, ...] = tuple(field.key for field in INTAKE_CHECKLIST if field.required)

# Ngưỡng "đủ thông tin" tính trên các trường BẮT BUỘC. 0.85 => cần 6/7 trường required.
# Đặt ở đây thay vì Settings vì đây là tham số demo, không phải cấu hình vận hành.
COMPLETION_THRESHOLD = 0.85


def completion_ratio(answers: dict[str, str | None]) -> float:
    """Tỉ lệ trường BẮT BUỘC đã có giá trị (không tính trường optional)."""
    if not REQUIRED_KEYS:
        return 1.0
    filled = sum(1 for key in REQUIRED_KEYS if _is_filled(answers.get(key)))
    return filled / len(REQUIRED_KEYS)


def missing_required_keys(answers: dict[str, str | None]) -> list[str]:
    return [key for key in REQUIRED_KEYS if not _is_filled(answers.get(key))]


def missing_optional_keys(answers: dict[str, str | None]) -> list[str]:
    return [
        field.key for field in INTAKE_CHECKLIST if not field.required and not _is_filled(answers.get(field.key))
    ]


def is_complete_enough(answers: dict[str, str | None]) -> bool:
    return completion_ratio(answers) >= COMPLETION_THRESHOLD


def _is_filled(value: str | None) -> bool:
    return bool(value and value.strip())
