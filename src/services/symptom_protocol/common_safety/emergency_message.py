"""Thông điệp cấp cứu TĨNH, dùng chung cho mọi protocol.

TĨNH là một ràng buộc an toàn (P0-2), không phải lựa chọn tiện tay: đây là câu duy nhất trong toàn hệ
thống có thể khiến người bệnh gọi 115 hay không, nên nó không được đi qua LLM. Nội dung cũng cố ý
KHÔNG nêu tên bệnh hay lý do lâm sàng - hệ thống không chẩn đoán, và một lời giải thích sai ở đây đắt
hơn nhiều so với việc không giải thích.
"""

from __future__ import annotations

EMERGENCY_MESSAGE = (
    "Đây là tình huống cần được cấp cứu ngay bây giờ — vui lòng gọi 115 hoặc đến ngay cơ sở y tế/"
    "khoa cấp cứu gần nhất, không chờ thêm. Thông tin đã được chuyển cho điều dưỡng ưu tiên hỗ trợ."
)
