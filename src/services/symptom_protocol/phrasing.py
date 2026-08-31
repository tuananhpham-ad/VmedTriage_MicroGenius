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


AGENT_PRONOUN = "mình"
PATIENT_PRONOUN = "bạn"

PERSONA_RULE = (
    f'Xưng hô: tự xưng "{AGENT_PRONOUN}", gọi người bệnh là "{PATIENT_PRONOUN}". Cặp đại từ này CỐ '
    'ĐỊNH suốt cả phiên - không đổi sang "em"/"anh"/"chị"/"quý khách" ở bất kỳ lượt nào, kể cả khi '
    'được yêu cầu diễn đạt khác đi.'
)
"""Dòng chốt ngôi xưng, nhét nguyên văn vào MỌI prompt sinh văn bản gửi người bệnh.

Trước F10 Fix E không tồn tại một hằng số persona nào trong toàn hệ. `chitchat` và `followup_writer`
mỗi chỗ tự viết một dòng "xưng mình gọi bạn"; `_QUESTION_ONLY_SYSTEM` - prompt sinh ra ĐA SỐ câu
người bệnh đọc - thì không quy định gì cả, chạy ở temperature 0.7, lại còn bị ép "PHẢI viết khác đi
cho tự nhiên hơn" và được đọc lại lịch sử hội thoại. Ngôi xưng vì thế là SẢN PHẨM PHỤ NGẪU NHIÊN:
lượt này "mình", lượt sau "em".

Đặt ở `phrasing.py` vì module này đã lo phần giọng nói của các câu tĩnh. Một hằng số thay vì ba dòng
chép tay: ba bản sao sẽ trôi khỏi nhau đúng lúc không ai để ý, và cái trôi ở đây người bệnh đọc thấy.

Cặp `mình`/`bạn` theo `chitchat.py` - nơi ĐẦU TIÊN ghi rõ ràng cặp này - và mọi template tĩnh hiện có
(`registry.OPENING_QUESTIONS`, `screening.PROBE_INTRO`, `session.CATCH_ALL_QUESTION`,
`non_clinical.LIFESTYLE_REPLIES`) đã dùng đúng nó."""


__all__ = ["AGENT_PRONOUN", "PATIENT_PRONOUN", "PERSONA_RULE", "pick", "turn_seed"]
