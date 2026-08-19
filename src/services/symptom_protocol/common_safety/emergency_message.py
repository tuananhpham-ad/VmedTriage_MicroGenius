"""Thông điệp an toàn TĨNH, dùng chung cho mọi protocol.

TĨNH là một ràng buộc an toàn (P0-2), không phải lựa chọn tiện tay: đây là những câu duy nhất trong
toàn hệ thống có thể khiến người bệnh gọi 115 hay không, nên chúng không được đi qua LLM. Nội dung
cũng cố ý KHÔNG nêu tên bệnh hay lý do lâm sàng - hệ thống không chẩn đoán, và một lời giải thích sai
ở đây đắt hơn nhiều so với việc không giải thích.

**ADR-007 (2026-08-19) supersede ADR-004 — ba câu, ba thời điểm, ba người nói.**

Hệ thống **không khẳng định cấp cứu**. Nó nêu **nghi ngờ**, đẩy ca lên ưu tiên cao nhất, và điều
dưỡng - trực 24/7 - mới là người kết luận. Đây là nguyên tắc y tế chuẩn: *công cụ sàng lọc nêu nghi
ngờ, lâm sàng viên kết luận.*

| Câu | Ai "nói" | Khi nào |
| --- | --- | --- |
| `SUSPECTED_RED_FLAG_MESSAGE` | hệ thống | t=0, ngay lượt phát hiện |
| `SLA_BREACH_MESSAGE` | hệ thống | quá `SLA_CLINICAL_SECONDS` mà chưa điều dưỡng nào mở ca |
| `EMERGENCY_MESSAGE` | điều dưỡng | SAU khi duyệt - mặc định cho `approved_response` |

`triage_level = "EMERGENCY"` **không đổi** theo ADR-007. Rule engine, `escalation_lock`, thứ tự hàng
đợi giữ nguyên; chỉ đổi thứ bệnh nhân ĐỌC. Đó cũng là lý do thay đổi này rẻ.
"""

from __future__ import annotations

SUSPECTED_RED_FLAG_MESSAGE = (
    "Có một số thông tin bạn vừa mô tả cần nhân viên y tế xem trực tiếp. Ca của bạn đã được chuyển "
    "lên mức ưu tiên cao nhất và sẽ có người liên hệ trong ít phút.\n\n"
    "Trong lúc chờ, nếu bạn thấy tình trạng xấu đi hoặc thấy không ổn, hãy gọi 115 ngay — đừng chờ "
    "phản hồi ở đây."
)
"""Câu phát NGAY tại t=0, cùng lượt phát hiện. Đây là thứ bệnh nhân đọc trong phiên.

Đoạn thứ hai là **lưới an toàn phổ quát**: nó đúng với mọi người bệnh trong mọi tình huống, nên nói
ra không phải là chẩn đoán. Im lặng hoàn toàn về mặt an toàn thì đẩy toàn bộ rủi ro sang thời gian
phản hồi của điều dưỡng - đó là lo ngại thật của ADR-004, và câu này giải nó mà không cần khẳng định
một kết luận lâm sàng nào."""

SLA_BREACH_MESSAGE = (
    "Chưa có nhân viên y tế phản hồi kịp. Để an toàn, vui lòng gọi 115 hoặc đến cơ sở y tế gần nhất "
    "ngay bây giờ."
)
"""Lưới đỡ khi đường chính (HITL) kẹt. Không có nó thì "chờ điều dưỡng" có thể âm thầm trở thành
"chờ vô hạn" khi ca trực quá tải hoặc hệ thống thông báo lỗi."""

EMERGENCY_MESSAGE = (
    "Đây là tình huống cần được cấp cứu ngay bây giờ — vui lòng gọi 115 hoặc đến ngay cơ sở y tế/"
    "khoa cấp cứu gần nhất, không chờ thêm. Thông tin đã được chuyển cho điều dưỡng ưu tiên hỗ trợ."
)
"""Nguyên văn câu cũ, GIỮ NGUYÊN - nó không sai, nó chỉ đang được nói bởi sai người ở sai thời điểm.
Từ ADR-007 nó là mặc định cho `approved_response` ở bước duyệt, tức là câu ĐIỀU DƯỠNG gửi đi."""
