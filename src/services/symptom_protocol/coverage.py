"""Sổ sách độ phủ của một phiên - THUẦN code, không model.

Lý do tồn tại: §8 nới thứ tự hỏi từ first-fit sang xếp hạng, tức là hệ thống được phép HOÃN một cụm
để đi theo mạch người bệnh đang kể. Hoãn mà không có sổ sách thì "linh hoạt" biến thành "quên hỏi",
và quên một field M0/M1 là quên đúng thứ rule engine cần để kết luận an toàn.

Vì vậy ledger phải có TRƯỚC ranking (§9 P3 mục 1), không phải sau. Nó trả lời được ba câu:

- còn field bắt buộc nào chưa có căn cứ? (`mandatory_remaining`)
- cụm nào đã bị đẩy lùi bao nhiêu lượt? (`deferred`)
- cụm nào đã hỏi rồi mà người bệnh không trả lời được? (`asked_but_unanswered`)

Câu thứ ba KHÔNG phải nợ. "Không biết" là một kết quả hợp lệ (`unknown`); hỏi lại lần thứ ba câu
người ta vừa nói không biết là lỗi trải nghiệm nặng hơn là thiếu một field tier O. Vì thế tập này
được lấy từ `session.unresolved_cluster_ids` (nguồn thật đã có) chứ không đếm lại ở đây - hai bộ đếm
song song sẽ lệch nhau.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.services.symptom_protocol.protocol import SymptomProtocol
from src.services.symptom_protocol.stage_machine import MANDATORY_TIERS, field_is_settled

DEFERRAL_LIMIT = 3
"""Số lượt một cụm được phép bị hoãn trước khi nó chắc chắn thắng ở lượt kế tiếp.

Đây là cơ chế chống BỎ SÓT, không phải chống hoãn: hoãn là hành vi mong muốn (đi theo mạch người
bệnh), chỉ hoãn vô hạn mới là lỗi."""


def mandatory_remaining(protocol: SymptomProtocol, answers: dict[str, object]) -> tuple[str, ...]:
    """Field tier M0/M1 chưa có căn cứ, theo đúng thứ tự khai báo của protocol.

    Dùng chung định nghĩa "đã có căn cứ" với `stage_machine.field_is_settled` (điền thật HOẶC không
    áp dụng vì field cha đã bị phủ định) - `mandatory_fields_covered` chính là hàm này rỗng."""
    return tuple(
        key for key, spec in protocol.fields_by_key.items()
        if spec.tier in MANDATORY_TIERS and not field_is_settled(protocol, key, answers)
    )


@dataclass(slots=True)
class CoverageLedger:
    """Trạng thái sổ sách MỚI mà phiên phải nhớ. Cố ý chỉ có ĐÚNG MỘT thứ: bộ đếm hoãn.

    `mandatory_remaining` tính lại được từ `answers` bất cứ lúc nào, `asked_but_unanswered` đã nằm ở
    `session.unresolved_cluster_ids`. Lưu thêm bản sao của chúng ở đây là tạo hai nguồn sự thật cho
    cùng một dữ kiện - đúng thứ làm sổ sách sai mà không ai phát hiện."""

    deferred: dict[str, int] = field(default_factory=dict)
    """`cluster_id -> số lượt đã bị hoãn`. Khoá là mã cụm TRẦN (không kèm protocol) vì ledger chỉ
    được đọc trong phạm vi protocol đang chạy; đổi protocol thì gọi `reset()`."""

    def record_turn(self, chosen_id: str | None, deferred_ids: frozenset[str]) -> None:
        """Ghi kết quả một lượt chọn cụm: cụm được chọn về 0, cụm bị bỏ qua tăng 1.

        `deferred_ids` là những cụm ĐỦ ĐIỀU KIỆN hỏi nhưng thua điểm - không phải mọi cụm chưa hỏi.
        Cụm bị skip theo tuổi/giới/nhánh không phải nợ, nó là câu hỏi vô nghĩa với người bệnh này."""
        for cluster_id in deferred_ids:
            self.deferred[cluster_id] = self.deferred.get(cluster_id, 0) + 1
        if chosen_id is not None:
            self.deferred.pop(chosen_id, None)

    def deferral_count(self, cluster_id: str) -> int:
        return self.deferred.get(cluster_id, 0)

    def overdue_ids(self) -> frozenset[str]:
        """Cụm đã chạm trần hoãn - phải được hỏi ở lượt kế tiếp."""
        return frozenset(
            cluster_id for cluster_id, count in self.deferred.items() if count >= DEFERRAL_LIMIT
        )

    def reset(self) -> None:
        """Đổi protocol giữa chừng: nợ của protocol cũ không chuyển sang protocol mới - mã cụm dùng
        chung giữa các protocol nên giữ lại sẽ gán nợ nhầm cụm (cùng lý do
        `Session.cluster_key` phải kèm tên protocol)."""
        self.deferred.clear()

    def snapshot(self, protocol: SymptomProtocol, answers: dict[str, object], *, unresolved: frozenset[str]) -> dict:
        """Bản đọc được của sổ sách, cho log/debug - "vì sao agent hỏi câu này" phải trả lời được
        bằng số liệu chứ không bằng suy đoán (§8.5)."""
        return {
            "mandatory_remaining": list(mandatory_remaining(protocol, answers)),
            "deferred": dict(sorted(self.deferred.items())),
            "asked_but_unanswered": sorted(unresolved),
        }
