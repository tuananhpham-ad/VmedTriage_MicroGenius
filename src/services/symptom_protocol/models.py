"""Kiểu dữ liệu dùng chung cho mọi symptom_group - KHÔNG có field/giá trị cụ thể của bệnh nào."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Tier = Literal["M0", "M1", "C", "O", "H"]


@dataclass(frozen=True, slots=True)
class FieldSpec:
    key: str
    label: str
    tier: Tier
    hint: str
    tri_state: bool = True
    # Tập giá trị hợp lệ của field enum (rỗng = tự do: số, ngày, chuỗi mô tả). Không chỉ để nhắc
    # prompt mà còn để LOẠI giá trị lạ sau khi LLM trả về - lỗi thật gặp phải khi test tay: người dùng
    # nói "tỉnh táo bình thường", model lưu nguyên văn tiếng Việt vào `consciousness_level` thay vì mã
    # `alert`, khiến rule engine không bao giờ nhận ra điều kiện an toàn và tự đẩy ca lành tính lên
    # EARLY_VISIT. Nhắc prompt là chưa đủ - phải chặn deterministic bằng code.
    allowed_values: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class QuestionCluster:
    id: str
    stage: str
    fields: tuple[str, ...]
    batch_negation: bool = False
    script_hint: str = ""


TriageLevel = Literal["EMERGENCY", "EARLY_VISIT", "SELF_CARE"]
TimeTarget = Literal["now", "within_4h", "within_24h", "monitor"]

LEVEL_RANK: dict[TriageLevel, int] = {"SELF_CARE": 0, "EARLY_VISIT": 1, "EMERGENCY": 2}
TIME_RANK: dict[TimeTarget, int] = {"now": 0, "within_4h": 1, "within_24h": 2, "monitor": 3}


@dataclass(frozen=True, slots=True)
class RuleMatch:
    rule_id: str
    reason_codes: tuple[str, ...]
    level: TriageLevel
    time_target: TimeTarget
