"""Kiểu dữ liệu dùng chung cho mọi symptom_group - KHÔNG có field/giá trị cụ thể của bệnh nào."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dataclass_field
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


@dataclass(frozen=True, slots=True)
class ScreeningGroup:
    """Một NHÓM CƠ QUAN được sàng lọc bằng MỘT câu hỏi gộp, thay vì hỏi lần lượt từng cụm bên trong.

    Lý do tồn tại: ca lành tính - nhóm đông nhất và cũng là nhóm ta muốn kết thúc sớm nhất - phải trả
    lời đủ 16 lượt của Stage 3A + 3B chỉ để tất cả cùng ra âm tính (đo được 36 lượt khi chạy LLM
    thật). CS §3.3A cho phép kỹ thuật phủ định gộp và CS §8.4 O1 minh hoạ một câu phủ định trải NHIỀU
    cụm; `QuestionCluster.batch_negation` mới chỉ áp dụng trong phạm vi MỘT cụm.

    Nhóm bị phủ định rõ ràng thì đóng luôn toàn bộ cụm bên trong; nhóm dương tính/chưa rõ mới đào sâu
    từng cụm theo đúng script chuẩn. Không có nhóm nào = protocol chạy y như trước (mặc định rỗng).
    """

    id: str
    stage: str
    cluster_ids: tuple[str, ...]
    """Cụm bị ĐÓNG khi nhóm được phủ định. Cụm mà tài liệu lâm sàng CẤM suy diễn từ phủ định gộp
    (fever: Q3-01 tri giác, Q3-03 co giật - CS §3.3A) không được đưa vào nhóm nào."""

    probe_hint: str
    """Ý cần LIỆT KÊ NGUYÊN VĂN trong câu sàng lọc. Câu hỏi được ghép TĨNH từ các hint này chứ không
    qua LLM diễn đạt lại: một nhóm chỉ được phép đóng khi người bệnh đã thực sự nhìn thấy danh sách
    dấu hiệu của nó, mà LLM diễn đạt lại thì có thể lược mất vài ý trong danh sách."""

    negative_values: dict[str, str] = dataclass_field(default_factory=dict)
    """Field ENUM -> giá trị "âm tính" (`urine_output` -> `normal`). Field tri-state mặc định `false`,
    không cần khai. Field mô tả chi tiết chỉ có nghĩa khi DƯƠNG tính (`rash_type`,
    `abdominal_pain_location`, `seizure_features`) cố ý KHÔNG khai - không có giá trị âm tính nào để
    ghi, và bịa một giá trị vào đó là dựng dữ liệu lâm sàng không ai nói."""


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
