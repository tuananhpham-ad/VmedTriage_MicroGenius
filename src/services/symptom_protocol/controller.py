"""L1 `controller` — quyết định lượt này GỌI GÌ, bằng code thuần. KHÔNG model.

Đây là phase P2 của `_guidance/what_to_do_next.md`, và tài liệu tự đặt sẵn một cảnh báo cho chính
nó: `session.submit_message` + `stage_machine.advance` + `screening.next_probe` + `batching.next_batch`
**hiện đã là** một controller tất định, nên gói chúng lại dưới một cái tên mới là "một sprint đổi
tên, không phải một thay đổi hành vi".

Vì vậy module này CỐ Ý HẸP. Nó chỉ nhận đúng hai việc mà code cũ chưa có chỗ nào làm, và bỏ qua
phần abstraction không đổi hành vi:

1. **Một chỗ tường minh để quyết "lượt này có gọi extractor không"** (tiêu chí nghiệm thu 1).
   Trước đây mọi lượt đều gọi, kể cả khi người bệnh chỉ gõ "chào bạn" - tốn một lời gọi ~3.8s
   (`eval/baselines/2026-08-17-p0-summary.md`) để trích xuất từ một câu không có dữ kiện lâm sàng nào.
2. **Fail closed khi trạng thái phiên không hợp lệ** (tiêu chí 3). Trước đây `submit_message` lặng lẽ
   `return session` khi không còn cụm nào - người bệnh gõ tin nhắn và KHÔNG nhận được gì. Giờ phiên
   chuyển sang đường bàn giao điều dưỡng. Không bao giờ gọi model để "đoán" nên làm gì.

Tiêu chí 2 (chỗ gắn `coverage_ledger`) **đã được giải quyết trước ở P3.1** theo cách khác: ledger là
`session.ledger`, một `CoverageLedger` riêng chứ không phải vài trường rời rắc trong `Session`. Dời
nó vào một `ExecutionPlan` lúc này là churn thuần - ghi ra đây thay vì lặng lẽ bỏ qua.

**Cổng router** (`should_consult_group_router`) hiện chưa có model nào phía sau: `registry.select_protocol`
thuần luật vẫn là đường quyết định. Cổng tồn tại sớm để (a) đếm được tỉ lệ lượt "đáng gọi router",
và (b) khi có SLM thì điều kiện gọi đã là bốn trigger ĐÓNG của §3.1, không phải "gọi khi thấy cần".
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from src.services.symptom_protocol.dialogue import DialogueAct
from src.services.symptom_protocol.models import QuestionCluster

FAIL_CLOSED_NO_CLUSTER = "no_current_cluster"
FAIL_CLOSED_NO_PROTOCOL = "no_protocol"

HANDOFF_MESSAGE = (
    "Mình xin phép dừng phần hỏi tự động ở đây và chuyển thông tin của bạn cho nhân viên y tế xem "
    "trực tiếp. Nếu bạn thấy nặng lên bất thường, hãy gọi 115 hoặc đến cơ sở y tế gần nhất ngay."
)
"""Thông điệp TĨNH khi fail closed. Không qua model: đúng lúc trạng thái phiên đã lạ là lúc ít có
quyền nhờ model ứng biến nhất."""


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    """Lượt này chạy những gì. Do CODE tạo, không bao giờ nhận từ model."""

    invoke_extractor: bool = True
    forced_act: DialogueAct | None = None
    """Act do code gán khi BỎ extractor - lúc đó không có nhãn `answer_quality` nào để suy ra."""
    fail_closed_reason: str = ""
    """Khác rỗng ⇒ không gọi model nào, đi thẳng đường bàn giao."""

    @property
    def fail_closed(self) -> bool:
        return bool(self.fail_closed_reason)


# Lời chào THUẦN - danh sách ĐÓNG và cố ý ngắn. Mỗi mục ở đây là một lượt hệ thống tự quyết bỏ
# extractor, nên tiêu chí là "không thể chứa dữ kiện lâm sàng", không phải "trông giống lời chào".
# "alo", "ok" nằm ngoài: chúng hay đi kèm nội dung thật ở lượt tiếp và không đáng để nới.
_GREETING_ONLY: frozenset[str] = frozenset({
    "chao", "chao ban", "chao bac si", "xin chao", "hello", "hi", "helo",
    "chao anh", "chao chi", "chao em", "chao co", "chao chu", "a lo",
    "toi chao ban", "minh chao ban", "em chao ban", "em chao bac si", "chao bs",
})

_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)


def _normalize(text: str) -> str:
    lowered = (text or "").casefold().replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", lowered)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", _PUNCTUATION.sub(" ", without_marks)).strip()


def is_greeting_only(message: str) -> bool:
    """Tin nhắn CHỈ là lời chào, không kèm gì khác."""
    return _normalize(message) in _GREETING_ONLY


def build_execution_plan(
    *,
    message: str,
    cluster: QuestionCluster | None,
    protocol_name: str,
    is_opening: bool,
    has_safety_signal: bool,
) -> ExecutionPlan:
    """Kế hoạch cho MỘT lượt. Hàm thuần: cùng input cho cùng output, không side-effect, không model.

    `has_safety_signal`: tầng L0 đã thấy tín hiệu nguy hiểm nào trên text thô chưa. Có tín hiệu thì
    KHÔNG bao giờ bỏ extractor, kể cả khi tin nhắn trông như lời chào - đây là chỗ hai tầng an toàn
    phải nối vào nhau thay vì mỗi tầng tự tin vào phán đoán của mình."""
    if not is_opening:
        # Fail closed. Thứ tự kiểm: thiếu protocol nghiêm trọng hơn thiếu cụm, nên báo trước.
        if not protocol_name:
            return ExecutionPlan(invoke_extractor=False, fail_closed_reason=FAIL_CLOSED_NO_PROTOCOL)
        if cluster is None:
            return ExecutionPlan(invoke_extractor=False, fail_closed_reason=FAIL_CLOSED_NO_CLUSTER)

    if not has_safety_signal and is_greeting_only(message):
        # §7.4: "greeting thuần có thể được guard deterministic xử lý mà không gọi extractor".
        # `off_topic` thì KHÔNG - nhãn đó do model gán và chưa validate, bỏ extractor theo nó là tin
        # vào đúng thứ tầng này sinh ra để không phải tin.
        return ExecutionPlan(invoke_extractor=False, forced_act=DialogueAct.GREETING)

    return ExecutionPlan()


# --- cổng router theo bốn trigger ĐÓNG của §3.1 ---------------------------------------------------

ROUTER_TRIGGER_OPENING = "opening_turn"
ROUTER_TRIGGER_NEW_SYMPTOM = "new_symptom"
ROUTER_TRIGGER_CHIEF_COMPLAINT = "chief_complaint_touched"
ROUTER_TRIGGER_PROTOCOL_RULED_OUT = "protocol_ruled_out"

_GATE_STATS: dict[str, int] = {"turns": 0, "consulted": 0}


def should_consult_group_router(
    *,
    is_opening: bool,
    act: DialogueAct,
    recent_fields: frozenset[str],
    chief_complaint_field: str,
    protocol_ruled_out: bool,
) -> str:
    """Trigger khiến lượt này ĐÁNG hỏi `symptom_group_router`, hoặc rỗng nếu không.

    Bốn trigger, KHÔNG có trường hợp thứ năm (§3.1). "Chỉ gọi khi rule chưa đủ dữ liệu" là mô tả mục
    đích chứ không phải điều kiện implement được - mỗi người hiểu một kiểu và cuối cùng router chạy
    mọi lượt. Điều kiện ở đây tính thuần từ `recent_fields` + trạng thái phiên nên test được và ĐẾM
    được (`router_gate_stats`).

    Hàm này KHÔNG gọi model. Chưa có SLM nào phía sau; `registry.select_protocol` thuần luật vẫn là
    đường quyết định, và nếu không bao giờ có SLM thì cổng này chỉ còn là một chỉ số."""
    _GATE_STATS["turns"] += 1
    trigger = ""
    if is_opening:
        trigger = ROUTER_TRIGGER_OPENING
    elif act is DialogueAct.NEW_SYMPTOM:
        trigger = ROUTER_TRIGGER_NEW_SYMPTOM
    elif chief_complaint_field and chief_complaint_field in recent_fields:
        trigger = ROUTER_TRIGGER_CHIEF_COMPLAINT
    elif protocol_ruled_out:
        trigger = ROUTER_TRIGGER_PROTOCOL_RULED_OUT
    if trigger:
        _GATE_STATS["consulted"] += 1
    return trigger


def router_gate_stats() -> dict[str, int]:
    """Số lượt đã qua cổng và số lượt đáng gọi router.

    Đây là chốt chặn chống việc "chỉ gọi khi cần" âm thầm trôi thành "gọi mọi lượt" (§11 mục 7 của
    nhóm an toàn): lượt trả lời bình thường trong cùng protocol phải KHÔNG kích hoạt trigger nào."""
    return dict(_GATE_STATS)


def reset_router_gate_stats() -> None:
    _GATE_STATS.update({"turns": 0, "consulted": 0})
