"""Chọn một bản diễn đạt trong nhiều bản, TẤT ĐỊNH theo seed. Dùng cho các câu TĨNH của agent.

VÌ SAO CÓ NHIỀU BẢN. Một câu viết cứng thì lượt nào cũng ra đúng một chuỗi ký tự, và người bệnh gặp
nó lần thứ hai là nhận ra ngay mình đang nói chuyện với máy trả lời tự động. `registry.OPENING_QUESTIONS`
đã đi trước theo hướng này cho câu mở; module này là phần dùng chung để các câu tĩnh còn lại theo sau
mà không mỗi chỗ tự chép một bộ chọn riêng.

VÌ SAO VẪN TĨNH, KHÔNG NHỜ LLM. Các câu dùng module này đều là câu ĐIỀU KHIỂN: xác nhận một dấu hiệu
nguy hiểm, xác nhận một đính chính, hỏi có dừng phiên không. Chúng phải nêu ĐÚNG thứ hệ thống đang
hỏi - một bản diễn đạt lại có thể biến câu xác nhận thành câu gợi ý, và ở câu số 1 thì nó còn phải
đọc được cả khi provider chết. Nhiều bản viết sẵn cho ta sự đa dạng mà không phải trả giá nào trong
số đó.

TẤT ĐỊNH THEO SEED, KHÔNG `random`. Cùng một seed luôn cho cùng một bản, nên log đọc lại được và test
không phải mock bộ sinh ngẫu nhiên. Người bệnh vẫn thấy khác nhau vì seed thật mang theo cả
`session_id` lẫn số lượt.
"""

from __future__ import annotations

from hashlib import sha256


def pick(variants: tuple[str, ...], seed: object = "") -> str:
    """Một bản trong `variants`, chọn tất định theo `seed`.

    Cùng khuôn với `registry.opening_question` - cố ý, để hai chỗ chọn biến thể trong cùng một
    codebase không hành xử khác nhau. Seed rỗng trả bản đầu: đó là đường lui khi chỗ gọi chưa có gì
    ổn định để làm seed, và nó phải tất định chứ không được rơi về ngẫu nhiên."""
    if not variants:
        return ""
    key = str(seed)
    if not key:
        return variants[0]
    return variants[sha256(key.encode("utf-8")).digest()[0] % len(variants)]


def turn_seed(session_id: str, turn: int) -> str:
    """Seed đổi theo TỪNG LƯỢT trong cùng một phiên.

    Chỉ dùng `session_id` thì cả phiên nhận đúng một bản - đúng cái đơn điệu đang muốn bỏ, chỉ dời
    từ mức "mọi phiên" xuống mức "mọi lượt trong một phiên". Kèm số lượt thì hai lần bị hỏi cùng một
    loại câu trong cùng một phiên cũng đọc ra khác nhau, mà vẫn tái hiện được khi đọc lại log."""
    return f"{session_id}:{turn}"


__all__ = ["pick", "turn_seed"]
