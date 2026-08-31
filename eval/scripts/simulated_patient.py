"""Bệnh nhân mô phỏng - thứ §2.4 lỗ hổng 1 nói là còn thiếu.

VẤN ĐỀ NÓ GIẢI. `data/golden_cases_v1.jsonl` có 120 ca nhưng **mỗi ca đúng 2 lượt bệnh nhân**, trong
khi protocol cần ~10-20 lượt để kết luận. Hệ quả đo được ở baseline P0.2: chỉ nhánh ĐỎ (escalate sớm)
là đo được; `EARLY_VISIT`/`SELF_CARE` không bao giờ đạt tới, và mọi metric trải nghiệm của §12
(`user_led_ratio`, `repeat_question_rate`, số lượt trung vị...) không có dữ liệu để tính.

RANH GIỚI - QUAN TRỌNG HƠN MỌI THỨ KHÁC TRONG FILE NÀY:

1. **Bệnh nhân mô phỏng KHÔNG được biết nhãn.** Nó chỉ nhận lời kể của chính người bệnh
   (`role == "patient"` trong golden case). `expected_triage`, `expected_red_flags`,
   `expected_handoff` KHÔNG bao giờ vào prompt. Cho nó biết đáp án thì nó sẽ lái hội thoại về phía
   đáp án, và bài đo hoá ra đo chính cái đáp án mình vừa đưa vào.
2. **Nó không phải một phần của sản phẩm.** File nằm ở `eval/`, không nằm ở `src/`. Không module nào
   trong `src/` được import nó.
3. **Nó được phép nói "không biết".** Một bệnh nhân mô phỏng luôn trả lời đầy đủ sẽ cho ra chỉ số
   đẹp hơn thực tế - và chỗ hệ thống hay hỏng nhất lại đúng là chỗ người bệnh không trả lời được.

CÁI NÓ ĐO ĐƯỢC VÀ CÁI NÓ KHÔNG. Nó đo được ĐỘ DÀI hội thoại, ĐỘ PHỦ khi đóng, và THỨ TỰ hỏi - đều là
thứ phụ thuộc vào hành vi hệ thống chứ không vào chất lượng diễn xuất của bệnh nhân giả. Nó KHÔNG đo
được độ chính xác triage: nhãn của golden case gắn với 2 lượt gốc, còn 18 lượt sau là do model bịa ra
trong khuôn khổ lời kể, nên một ca có thể hợp lý mà vẫn ra mức khác nhãn. Đừng đọc kết quả chạy ở đây
như một phép đo triage accuracy.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.services.infra import provider_router

logger = logging.getLogger("vmedtriage.eval.simulated_patient")

_SYSTEM = """Bạn đang ĐÓNG VAI một người bệnh (hoặc người nhà) nhắn tin cho tổng đài tư vấn y tế.

ĐÂY LÀ TOÀN BỘ NHỮNG GÌ BẠN BIẾT VỀ TÌNH TRẠNG CỦA MÌNH:
{profile}

QUY TẮC BẮT BUỘC:
- Trả lời câu hỏi của nhân viên tư vấn bằng tiếng Việt tự nhiên, NGẮN (1-2 câu), như nhắn tin thật.
- CHỈ dùng thông tin trong phần trên. Nếu được hỏi điều gì KHÔNG có trong đó, hãy tự trả lời một cách
  hợp lý và NHẤT QUÁN với những gì bạn đã nói ở các lượt trước.
- Nếu là chi tiết bạn không thể biết (số đo chưa đo, tiền sử không rõ), cứ nói thẳng "mình không rõ"
  hoặc "chưa đo". Đừng bịa số liệu chính xác.
- Được phép trả lời "không" cho các dấu hiệu mà phần mô tả của bạn không nhắc tới.
- KHÔNG tự chẩn đoán, KHÔNG nói bạn cần đi cấp cứu hay không - bạn là người bệnh, không phải bác sĩ.
- KHÔNG nhắc tới việc bạn đang đóng vai hay đang trong một bài kiểm thử.
- Chỉ trả về ĐÚNG nội dung tin nhắn, không kèm giải thích, không kèm dấu ngoặc kép."""

_TEMPERATURE = 0.6
"""Cao hơn `fact_extractor` (0) và ngang `synthesis`: một bệnh nhân trả lời y hệt nhau mọi lần sẽ
che mất đúng loại lỗi mà bài đo này tìm - hệ thống xử lý cách diễn đạt lạ ra sao."""

_FALLBACK = "Mình không rõ lắm ạ."
"""Model bệnh nhân chết thì KHÔNG được làm hỏng cả lần chạy: một câu trung tính vẫn là một lượt hợp
lệ, và số lượt bị ảnh hưởng đã được đếm riêng (`fallback_turns`)."""


@dataclass(slots=True)
class SimulatedPatient:
    """Một bệnh nhân giả cho MỘT phiên. Giữ lịch sử để trả lời nhất quán giữa các lượt."""

    profile: str
    history: list[dict[str, str]] = field(default_factory=list)
    fallback_turns: int = 0
    """Số lượt phải dùng câu dự phòng vì model bệnh nhân lỗi. Phải báo cáo kèm kết quả: một lần chạy
    có nhiều lượt fallback là một lần chạy đo hệ thống bằng một bệnh nhân im lặng."""

    def reply(self, agent_message: str) -> str:
        """Trả lời câu hỏi của agent. Không bao giờ ném ra ngoài."""
        self.history.append({"role": "user", "content": agent_message})
        messages = [
            {"role": "system", "content": _SYSTEM.format(profile=self.profile)},
            *self.history,
        ]
        try:
            result = provider_router.complete(messages, temperature=_TEMPERATURE)
            text = result.text.strip().strip('"').strip()
        except Exception:  # noqa: BLE001 - model bệnh nhân lỗi không được làm hỏng cả lần chạy
            logger.warning("simulated patient LLM failed; dung cau du phong", exc_info=True)
            text = ""
        if not text:
            self.fallback_turns += 1
            text = _FALLBACK
        self.history.append({"role": "assistant", "content": text})
        return text


def profile_from_case(case: dict) -> str:
    """Dựng hồ sơ bệnh nhân từ MỘT golden case - chỉ lấy lời kể của chính người bệnh.

    Cố ý KHÔNG đọc `expected_triage`/`expected_red_flags`/`expected_handoff`/`rationale`: đó là nhãn,
    và một bệnh nhân biết trước nhãn sẽ lái hội thoại về phía nhãn đó."""
    lines = [
        str(turn["message"]).strip()
        for turn in case.get("conversation", [])
        if turn.get("role") == "patient" and turn.get("message")
    ]
    return "\n".join(f"- {line}" for line in lines)
