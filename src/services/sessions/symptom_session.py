"""Store phiên DÙNG CHUNG cho mọi symptom_group - một instance duy nhất của cả hệ thống.

Vì sao MỘT store chứ không phải mỗi bệnh một store:

1. **Lượt mở chưa biết protocol.** Ô chat của bệnh nhân bắt đầu bằng một câu tự do; protocol chỉ chọn
   được sau khi đã trích xuất câu đó. Không có store nào để "đặt phiên vào" trước thời điểm ấy.
2. **`case_id` = `session_id`.** Hàng đợi điều dưỡng, lịch sử bệnh nhân, nút xác nhận phiếu đều tra
   phiên theo `case_id`. Hai store tức là hai không gian id, và `/fever/sessions/{case_id}/confirm`
   sẽ 404 với case mở từ ô chat.
3. **Đổi protocol giữa chừng** (fever -> generic khi người bệnh đính chính "tôi không sốt") không thể
   làm được nếu phiên bị buộc vào store của một protocol.

`default_protocol=None` = mở phiên ở lượt mở. Endpoint chuyên biệt (`/api/v1/fever/*`) vẫn ghim được
protocol của mình bằng `start_session(protocol_name=...)` - xem `fever_session.py`.
"""

from __future__ import annotations

from src.services.symptom_protocol.session import ProtocolSessionStore

session_store = ProtocolSessionStore(default_protocol=None)
