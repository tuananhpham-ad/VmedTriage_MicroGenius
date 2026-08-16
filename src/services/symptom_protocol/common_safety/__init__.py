"""Phần AN TOÀN dùng chung cho mọi symptom_group: field đỏ + nhân khẩu, cụm hỏi, rule đỏ phổ quát,
thông điệp cấp cứu.

Chiều phụ thuộc BẮT BUỘC một chiều: `engines/<bệnh>_protocol.py` import từ đây; ở đây KHÔNG được
import bất cứ thứ gì từ `fever_*`/`generic_*`. Vi phạm chiều này là cách nhanh nhất để protocol thứ
hai kéo theo cả kiến thức về sốt.
"""

from src.services.symptom_protocol.common_safety.emergency_message import EMERGENCY_MESSAGE

__all__ = ["EMERGENCY_MESSAGE"]
