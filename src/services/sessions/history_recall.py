"""Memory **M3** — hỏi thăm 3 phiên gần nhất khi mở hội thoại mới (§4.9, `F04_memory.md` §3).

Thứ nó mở ra là thứ đáng làm: *"Lần trước bạn đau bụng, hiện đã đỡ hơn chưa?"* biến sản phẩm từ một
form hỏi bệnh thành một chỗ có người theo dõi. Nhưng đây là PHI, nên cả module gói gọn trong ba ràng
buộc, và **cả ba đều được thi hành bằng code chứ không bằng prompt**:

1. **Dữ kiện lịch sử KHÔNG tự trở thành dữ kiện hiện tại** (bất biến 9). `previous fever = true`
   không được nạp thành `current fever = true`. Module này không có hàm nào trả về `answers`, không
   import `reducer`, và thứ nó trả ra (`PastConversation`) không cùng hình dạng với snapshot - nên
   không có đường nào để nhét nhầm. Snapshot của phiên mới bắt đầu từ `Null` như mọi phiên khác.
2. **Đọc theo ĐÚNG `user_id` đang đăng nhập.** Truy vấn đi qua `conversation_store` với khoá
   composite `(conversation_id, user_id)`; khách chưa đăng nhập (`user_id == 0`) không có lịch sử -
   `0` là "chưa biết là ai", và gộp chung mọi phiên khách vào một hồ sơ là rò dữ liệu giữa người lạ.
3. **Consent + retention.** `Settings.long_memory_enabled` mặc định **TẮT**. Đây là câu hỏi cho PM
   chứ không cho kỹ thuật, và §6 `F04_memory.md` đòi trả lời **bằng văn bản trước khi** M3 lên
   production. `_RECALL_MAX_AGE_DAYS` là trần tạm cho tới lúc đó.

Câu hỏi thăm là **TĨNH, không qua LLM**: nó phải nói đúng một điều - lần trước người bệnh kể bị gì -
và một câu model viết lại có thể thêm chi tiết lâm sàng mà không phiên nào từng ghi nhận.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from src.config import get_settings
from src.services.stores.conversation_store import (
    GUEST_USER_ID,
    PastConversation,
    conversation_store,
)

logger = logging.getLogger("vmedtriage.history_recall")

_RECALL_MAX_AGE_DAYS = 30
"""Trần tuổi của phiên được hỏi thăm. Hai lý do, và lý do thứ hai mới là lý do chính:

1. Hỏi thăm một đợt ốm từ nửa năm trước không còn là quan tâm, nó là lạc đề.
2. **Đây là chỗ giữ hộ câu trả lời retention của PM.** Chừng nào chưa có chính sách bằng văn bản thì
   một trần cụ thể vẫn tốt hơn "nhớ mãi mãi" - mặc định an toàn hơn là mặc định tiện."""

_MAX_MENTIONED = 1
"""Số phiên được NHẮC TỚI trong câu hỏi thăm, dù lấy về 3. Đọc cho người bệnh nghe một danh sách ba
lần khám trước là mở đầu bằng một bản tóm tắt hồ sơ chứ không phải một câu hỏi thăm; hai phiên còn
lại vẫn ở đó cho điều dưỡng đọc, chỉ không lên câu chào."""

HISTORY_NAMESPACE = "history"
"""Tiền tố của namespace lịch sử. Mọi khoá đi ra từ đây đều là `history.*` - KHÔNG BAO GIỜ trùng với
một khoá field của protocol, nên kể cả khi có ai đó `update()` nhầm nó vào `answers` thì rule engine
cũng không đọc trúng (`fields_by_key` không có khoá nào chứa dấu chấm)."""


def recall(user_id: int, *, store=conversation_store, now: datetime | None = None) -> tuple[PastConversation, ...]:
    """Các phiên đã đóng gần nhất của CHÍNH người dùng này. Rỗng khi cờ tắt hoặc là phiên khách.

    Không bao giờ ném: hỏi thăm là phần thêm vào của lượt mở, còn lượt mở thì không - một lỗi ở đây
    không được phép chặn người bệnh bắt đầu kể bệnh."""
    settings = get_settings()
    if not settings.long_memory_enabled or user_id == GUEST_USER_ID:
        return ()
    try:
        entries = store.recent_summaries_for_user(
            user_id, limit=settings.long_memory_recent_conversations,
        )
    except Exception as error:
        logger.warning("history recall failed user=%s: %s", user_id, error)
        return ()
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=_RECALL_MAX_AGE_DAYS)
    return tuple(entry for entry in entries if _updated_at(entry) >= cutoff)


def greeting(entries: tuple[PastConversation, ...]) -> str:
    """Câu hỏi thăm TĨNH, hoặc chuỗi rỗng khi không có gì để hỏi thăm.

    Chỉ dùng `chief_complaint` - nhãn than phiền chính người bệnh đã tự kể. KHÔNG dùng `narrative`
    (văn xuôi dài, đọc lại nguyên văn cho người bệnh nghe là đọc hồ sơ của họ ra loa) và KHÔNG dùng
    `proposed_priority` (mức ưu tiên là đề xuất cho ĐIỀU DƯỠNG, nhắc lại cho người bệnh là biến một
    đề xuất chờ duyệt thành một kết luận đã tuyên - `CLAUDE.md` nguyên tắc 1)."""
    for entry in entries[:_MAX_MENTIONED]:
        complaint = entry.chief_complaint.strip()
        if complaint:
            return f"Lần trước bạn có nhắc tới {complaint.lower()}. Tình trạng đó giờ đã đỡ hơn chưa?"
    return ""


def greeting_for_user(user_id: int) -> str:
    """`recall` + `greeting` trong một lời gọi - đây là thứ được tiêm vào `ProtocolSessionStore`.

    Gộp hai bước lại để mặt tiếp xúc của store với M3 đúng bằng một hàm `(int) -> str`: store không
    bao giờ cầm trong tay một `PastConversation`, nên nó không có gì để nhét nhầm vào snapshot."""
    return greeting(recall(user_id))


def history_namespace(entries: tuple[PastConversation, ...]) -> dict[str, str]:
    """Dữ kiện lịch sử dưới dạng `history.*` — cho log và cho màn hình điều dưỡng.

    ⚠️ **KHÔNG BAO GIỜ `update()` cái này vào `Session.answers`.** Nó ở namespace riêng đúng như §3
    điều kiện 1 yêu cầu; trộn vào snapshot là biến lời kể của tháng trước thành triệu chứng của hôm
    nay, và rule engine sẽ chấm mức ưu tiên hôm nay bằng dữ kiện đó."""
    if not entries:
        return {}
    latest = entries[0]
    return {
        f"{HISTORY_NAMESPACE}.last_conversation_id": latest.conversation_id,
        f"{HISTORY_NAMESPACE}.last_chief_complaint": latest.chief_complaint,
        f"{HISTORY_NAMESPACE}.last_updated_at": _updated_at(latest).isoformat(),
        f"{HISTORY_NAMESPACE}.conversation_count": str(len(entries)),
    }


def _updated_at(entry: PastConversation) -> datetime:
    """SQLite trả `datetime` NAIVE kể cả với `DateTime(timezone=True)` - so sánh thẳng với một mốc
    aware sẽ ném `TypeError` giữa lượt mở phiên. Coi bản ghi naive là UTC, đúng thứ `save` đã ghi."""
    value = entry.updated_at
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
