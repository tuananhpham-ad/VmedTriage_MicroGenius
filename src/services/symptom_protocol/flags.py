"""Công tắc ngắt cho các cơ chế hội thoại thêm vào ở P2-P3 (§9 P4 mục 5).

VÌ SAO TỒN TẠI. P0-P3 đổi hành vi trên chính đường người bệnh đang đi - thứ tự câu hỏi, cách diễn
đạt, và (từ P2.4) quyền xoá dữ kiện đã khai. Trước file này, cách duy nhất để quay lui khi một cơ chế
hành xử sai trong thực tế là deploy lại. Với một hệ y tế thì đó là quãng thời gian sai quá dài.

BỐN CÔNG TẮC RIÊNG, KHÔNG PHẢI MỘT CỜ "FLOW CŨ". Một cờ tổng nghe gọn hơn nhưng nó tắt cả những cơ
chế đang chạy đúng, nên trên thực tế không ai dám bật - và một đường quay lui không ai dám dùng thì
không phải đường quay lui. Mỗi công tắc dưới đây rơi về một nhánh ĐÃ CÓ SẴN và đã được test, chứ
không mở thêm nhánh code thứ hai.

KHÔNG CÓ CÔNG TẮC CHO TẦNG AN TOÀN. `text_safety_signals` (L0), `common_safety/rules`, `rule_engine`,
`escalation_lock`, `output_guard` (L5) và bước quét sót không được phép tắt - đó là "loại 1" của §8.1,
thứ khiến hệ thống audit được. Một công tắc tắt được lớp bảo vệ là một công tắc sẽ bị bật nhầm lúc
3 giờ sáng.

ĐỌC MỖI LẦN GỌI, không cache vào hằng số module. Nói cho đúng mức: `get_settings()` vẫn được
`lru_cache` giữ, nên **đổi biến môi trường vẫn cần khởi động lại tiến trình** - công tắc này rút quy
trình từ "sửa code + review + deploy" xuống "đổi biến + restart", không phải xuống "bật tắt nóng".
Cái mà việc đọc-mỗi-lần-gọi thật sự mua được là hai thứ: cờ đổi được trong một tiến trình đang chạy
(bài test làm đúng việc này qua `monkeypatch`), và không có hằng số module nào đóng băng giá trị ở
thời điểm import - thứ tự import khi đó sẽ quyết định hành vi, và đó là loại lỗi rất khó nhìn ra.
"""

from __future__ import annotations

from src.config import get_settings


def ranking_enabled() -> bool:
    """Xếp hạng cụm tất định (§8.3). Tắt ⇒ first-fit thuần thứ tự khai báo, tức hành vi trước P3.2.

    Độ phủ KHÔNG phụ thuộc công tắc này: `mandatory_fields_covered` đọc tier field, còn xếp hạng chỉ
    sắp lại thứ tự trong tập cụm VỐN ĐÃ hợp lệ."""
    return get_settings().agent_ranking_enabled


def synthesis_enabled() -> bool:
    """Bước diễn đạt câu hỏi bằng model (L4). Tắt ⇒ phát nguyên văn `script_hint`.

    Nhánh này luôn được test sẵn vì nó cũng đúng là đường `output_guard` rơi về khi model viết sai
    (§6.5) - tắt công tắc chỉ là đi thẳng vào đó."""
    return get_settings().agent_synthesis_enabled


def retraction_confirmation_enabled() -> bool:
    """Cổng xác nhận trước khi xoá dây chuyền (§5 quy tắc 5). Tắt ⇒ đính chính rủi ro được áp NGAY.

    Đánh đổi có hai chiều thật, nên công tắc mới đáng có: bật thì rủi ro là hỏi lại thừa một lượt
    (người bệnh có thể bỏ giữa chừng); tắt thì rủi ro là "bé không sốt xuất huyết" xoá sạch phần
    nhiệt độ đã khai."""
    return get_settings().agent_retraction_confirmation_enabled


def unset_operation_enabled() -> bool:
    """`operation: "unset"` của bộ trích xuất (§4.1). Tắt ⇒ bỏ qua, hồ sơ chỉ bị xoá qua đường phủ
    định field cha như trước P2.4.

    Đây là cơ chế MỚI NHẤT và ít giờ chạy thật nhất, mà lại là cơ chế duy nhất cho model một đường
    XOÁ dữ kiện - đúng loại rủi ro mà một công tắc tồn tại để bù."""
    return get_settings().agent_unset_operation_enabled
