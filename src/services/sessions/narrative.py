"""`summary_text` — bản văn xuôi của phiếu (§4.3 chế độ (a), ADR-006).

Đây là output DUY NHẤT của phần tóm tắt có gọi model. Nó tồn tại vì hai người đọc khác nhau: điều
dưỡng đọc bảng ISBAR có cấu trúc, còn DB/memory cần một đoạn đọc được như người viết.

**Ba ràng buộc, và cả ba đều được thi hành bằng code chứ không bằng prompt:**

1. **Đọc CÙNG MỘT snapshot với `summary_json`.** Không có đường nào để bản văn xuôi lấy dữ kiện từ
   chỗ khác - hàm này nhận `FieldSummary` đã render sẵn, không nhận `answers` thô.
2. **Bản render theo field là BẢN ĐỐI CHỨNG.** Văn xuôi nói một điều mà không field nào đỡ thì nó
   đang bịa; `narrative_is_grounded` bắt ca đó và guard chặn (`VIOLATION_UNGROUNDED`).
3. **Model chết ⇒ rơi về bản tất định**, không rơi về chuỗi rỗng. Phiếu vẫn phải đọc được khi
   provider hỏng - đó cũng là lý do `FieldSummary.as_text()` là fallback chứ không phải một thông
   báo lỗi.

Hàm này KHÔNG bao giờ ném ra ngoài: một lỗi ở tầng tóm tắt không được làm hỏng việc bàn giao ca.
"""

from __future__ import annotations

import logging

from src.services.infra import fever_stage_log as stage_log
from src.services.infra import provider_router
from src.services.sessions.summary_render import (
    FieldSummary,
    narrative_invents_denials,
    narrative_is_grounded,
)
from src.services.symptom_protocol import output_guard

logger = logging.getLogger("vmedtriage.narrative")

_SYSTEM_PROMPT = """Bạn viết lại lời khai của người bệnh thành MỘT đoạn văn xuôi tiếng Việt ngắn cho hồ sơ y tế.

QUY TẮC BẮT BUỘC:
- CHỈ dùng dữ kiện có trong danh sách bên dưới. TUYỆT ĐỐI không thêm chi tiết y khoa nào khác.
- KHÔNG nêu tên bệnh, KHÔNG chẩn đoán, KHÔNG khuyên xử trí, KHÔNG nhắc tới thuốc hay việc đi khám.
- Chỉ viết hai nhóm dữ kiện đã xác định, và TUYỆT ĐỐI KHÔNG trộn chúng vào nhau:
  * mục "Triệu chứng ghi nhận" -> viết là người bệnh CÓ;
  * mục "Người bệnh phủ nhận" -> viết là người bệnh nói KHÔNG CÓ;
- Không viết về field chưa xác định/chưa hỏi tới. Không dùng chữ "unknown" trong đoạn tóm tắt.
- Viết ở ngôi thứ ba ("Người bệnh..."), 3-5 câu, không gạch đầu dòng, không markdown.
- Nếu cùng một thông tin bị đính chính nhiều lần, chỉ dùng giá trị MỚI NHẤT."""

_FALLBACK_REASON_NO_MODEL = "provider_unavailable"


NARRATIVE_SOURCE_LLM = "llm"


def build_narrative(
    summary: FieldSummary,
    *,
    credential: provider_router.LLMCredential | None = None,
    session_id: str = "",
) -> tuple[str, str]:
    """Trả `(narrative, source)`.

    `source` là `"llm"` hoặc một mã lý do đã rơi về bản tất định (`"provider_unavailable"`, hoặc mã
    vi phạm guard). Trả ra thay vì chỉ log: phiếu cần nói được nó đang hiển thị bản nào, và
    `narrative_fallback_rate` là một chỉ số §8 thật chứ không phải chuyện gỡ lỗi."""
    deterministic = summary.as_text()

    def _record(source: str) -> None:
        """Ghi MỘT dòng log cho mỗi lần sinh văn xuôi, để `narrative_fallback_rate` đếm được.

        Phải ghi riêng chứ không nhét vào bản chụp metric của phiên: bản chụp đó được viết lúc
        `_finish()`, còn văn xuôi thì sinh SAU đó (ở `symptom_case_bridge`, khi dựng phiếu) - lúc
        biết được nó fallback hay không thì file meta của phiên đã đóng rồi. Dời việc sinh văn xuôi
        lên trước `_finish()` thì sạch hơn về dữ liệu nhưng đặt một lời gọi LLM vào giữa đường đóng
        phiên, và provider chậm sẽ làm chậm đúng lượt cuối của người bệnh."""
        if session_id:
            stage_log.step(
                session_id, turn=0, stage="SUMMARY", cluster_id=None, event="agent_message",
                input=None, output={"narrative_source": source},
                llm_used=source == NARRATIVE_SOURCE_LLM,
            )

    if not deterministic:
        # Chưa thu được field nào - không có gì để viết lại, và bịa ra một đoạn văn ở đây là đúng
        # thứ nguyên tắc 3 của `CLAUDE.md` cấm.
        _record("empty_record")
        return "", "empty_record"

    try:
        result = provider_router.complete(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": deterministic},
            ],
            temperature=0.2,
            credential=credential,
            role=provider_router.ROLE_SYNTHESIS,
        )
    except Exception as error:  # provider hỏng/timeout - phiếu vẫn phải bàn giao được
        logger.warning("narrative fallback: %s", error)
        _record(_FALLBACK_REASON_NO_MODEL)
        return deterministic, _FALLBACK_REASON_NO_MODEL

    text = (result.text or "").strip()
    # HAI kiểm tra, không phải một. `grounded` bắt ca "văn xuôi nói thứ không có trong hồ sơ";
    # `invented_denials` bắt ca nguy hiểm hơn - văn xuôi nói ĐÚNG field nhưng SAI CỰC, biến một
    # `unknown` thành lời phủ nhận của người bệnh. Ca thứ hai đọc rất thuyết phục nên nó không bao
    # giờ tự lộ ra khi soát bằng mắt.
    verdict = output_guard.check_narrative(
        text,
        grounded=narrative_is_grounded(text, summary),
        invented_denials=tuple(narrative_invents_denials(text, summary)),
    )
    if not verdict.ok:
        logger.warning("narrative rejected by guard: %s", verdict.violations)
        reason = ",".join(verdict.violations)
        _record(reason)
        return deterministic, reason
    _record(NARRATIVE_SOURCE_LLM)
    return text, NARRATIVE_SOURCE_LLM
