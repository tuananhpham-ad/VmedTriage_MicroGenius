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

**NỘI DUNG của câu hỏi thăm là tất định; chỉ CÁCH NÓI mới đi qua model.** Nhãn được nhắc tới do
`_ranked_complaints` chốt ở đây, rồi `followup_writer` (`ROLE_FOLLOWUP_QUESTION`) diễn đạt lại nó -
với đầu vào chỉ có nhãn và một guard bằng code ở đầu ra. Mọi đường thất bại rơi về câu tĩnh của
`greeting`. Ranh giới đó tồn tại vì đúng cái rủi ro cũ: một câu model tự do viết có thể thêm chi tiết
lâm sàng mà không phiên nào từng ghi nhận.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone

from src.config import get_settings
from src.services.sessions import followup_writer
from src.services.stores.conversation_store import (
    GUEST_USER_ID,
    PastConversation,
    conversation_store,
)
from src.services.stores.followup_store import followup_store

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
    ranked = _ranked_complaints(entries)
    if not ranked:
        return ""
    complaint, occurrences = ranked[0]
    if occurrences >= 2:
        # Than phiền LẶP LẠI là thứ duy nhất trong ba phiếu đáng được hỏi khác đi: một đợt ốm đã kể
        # hai lần thì câu đáng hỏi không còn là "đỡ chưa" mà là "nó cứ quay lại phải không".
        return (
            f"Mấy lần gần đây bạn có nhắc tới {complaint} {occurrences} lần rồi. "
            "Tình trạng đó vẫn còn hay đã đỡ hẳn rồi ạ?"
        )
    return f"Lần trước bạn có nhắc tới {complaint}. Tình trạng đó giờ đã đỡ hơn chưa?"


def refresh_for_user(user_id: int, *, store=followup_store) -> str:
    """Chắt lọc 3 phiếu gần nhất thành MỘT câu hỏi thăm rồi ghi sẵn vào DB. Trả về câu vừa ghi.

    Gọi ở chỗ RẢNH - ngay sau khi một phiên đóng và phiếu bàn giao của nó vừa được lưu
    (`routes._remember_nurse_summary`) - chứ không ở lượt mở hội thoại. Lượt mở là lượt duy nhất
    người bệnh phải chờ mà chưa nhận lại được gì; đặt một truy vấn 3 hàng cộng một phép chắt lọc vào
    đó là bắt họ trả phí cho một câu xã giao.

    Ghi cả khi kết quả RỖNG (`save` vẫn tạo hàng rỗng): "đã chắt lọc, không có gì để hỏi" là một câu
    trả lời, và nó khiến lượt mở lần sau không phải chắt lọc lại để tìm ra đúng câu trả lời ấy.

    Không bao giờ ném - nó chạy ở đuôi một lượt đã xong việc, và không được phép làm hỏng lượt đó."""
    if not get_settings().long_memory_enabled or user_id == GUEST_USER_ID:
        return ""
    try:
        entries = recall(user_id)
        question = _write_question(entries)
        store.save(
            user_id, question, source_ids=[entry.conversation_id for entry in entries],
        )
        return question
    except Exception as error:
        logger.warning("followup refresh failed user=%s: %s", user_id, error)
        return ""


def _write_question(entries: tuple[PastConversation, ...]) -> str:
    """Câu hỏi thăm cuối cùng: model viết (`ROLE_FOLLOWUP_QUESTION`) trên nội dung code đã chốt.

    Phân vai cố ý: **code chọn NÓI VỀ CÁI GÌ, model chọn NÓI THẾ NÀO.** `_ranked_complaints` quyết
    định nhãn nào được nhắc tới - đó là một quyết định về dữ liệu bệnh nhân và nó phải tất định; còn
    cách nói thì câu tĩnh làm dở, vì lần thứ ba đọc đúng một khuôn câu thì nó thành tiếng ồn.

    `greeting(entries)` vừa là fallback vừa là mốc so sánh: tắt cờ, model chết hoặc trượt guard đều
    trả về đúng nó."""
    static = greeting(entries)
    ranked = _ranked_complaints(entries)
    if not ranked:
        return static
    complaint, occurrences = ranked[0]
    return followup_writer.compose(
        entries, complaint=complaint, occurrences=occurrences, fallback=static,
    )


def greeting_for_user(user_id: int, *, store=followup_store) -> str:
    """Câu hỏi thăm cho lượt mở - đây là thứ được tiêm vào `ProtocolSessionStore`.

    Đọc câu ĐÃ CHẮT LỌC SẴN thay vì chắt lọc tại chỗ: một `SELECT` theo khoá chính thay cho một
    truy vấn 3 hàng. Mặt tiếp xúc của store với M3 vẫn đúng bằng một hàm `(int) -> str` - store không
    bao giờ cầm trong tay một `PastConversation`, nên nó không có gì để nhét nhầm vào snapshot.

    **Hỏi đúng MỘT LẦN cho mỗi câu được sinh ra** (`mark_asked`). Lặp lại đúng câu hỏi thăm đó ở mọi
    lần mở hội thoại biến một câu quan tâm thành một dòng chào tự động, và người bệnh sẽ học cách bỏ
    qua nó - kể cả những lần nó đáng đọc.

    Nhánh chắt lọc bù (`exists()` sai) chỉ chạy đúng một lần cho mỗi người dùng: nó có mặt vì những
    người đã có lịch sử từ TRƯỚC khi bảng này tồn tại, và vì lần đầu bật `LONG_MEMORY_ENABLED`."""
    settings = get_settings()
    if not settings.long_memory_enabled or user_id == GUEST_USER_ID:
        return ""
    if not store.exists(user_id):
        refresh_for_user(user_id, store=store)
    pending = store.pending(user_id, max_age_days=_RECALL_MAX_AGE_DAYS)
    if pending is None:
        return ""
    store.mark_asked(user_id)
    return pending.question


def _ranked_complaints(entries: tuple[PastConversation, ...]) -> list[tuple[str, int]]:
    """Các than phiền chính trong 3 phiếu, xếp theo (số lần lặp, mới nhất trước).

    Đây là toàn bộ phần "chắt lọc": ba phiếu vào, một nhãn ra. Đọc cả ba nhãn cho người bệnh nghe là
    mở đầu bằng một bản tóm tắt hồ sơ chứ không phải một câu hỏi thăm - nên `_MAX_MENTIONED` vẫn là
    trần, và thứ ba phiếu đóng góp là BẰNG CHỨNG để chọn nhãn nào, không phải thêm nhãn để đọc.

    So khớp bằng chữ thường đã chuẩn hoá khoảng trắng, KHÔNG bằng đồng nghĩa lâm sàng ("sốt cao" và
    "sốt" là hai nhãn khác nhau ở đây). Gộp đồng nghĩa là suy luận lâm sàng, và làm nó bằng một bảng
    tra trong module xã giao là đúng chỗ để nó sai mà không ai kiểm."""
    counts: Counter[str] = Counter()
    first_seen: dict[str, int] = {}
    for index, entry in enumerate(entries):
        label = " ".join(entry.chief_complaint.lower().split()).strip(" .!?,;:")
        if not label:
            continue
        counts[label] += 1
        first_seen.setdefault(label, index)
    return sorted(counts.items(), key=lambda item: (-item[1], first_seen[item[0]]))[:_MAX_MENTIONED]


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
