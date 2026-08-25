"""Model viết CÂU HỎI THĂM mở đầu hội thoại mới — Memory **M3** (`F04_memory.md` §3.1).

Đây là con LLM thứ hai của tầng ký ức, và nó KHÔNG cùng việc với con thứ nhất:

| | `ROLE_CONTEXT_SUMMARY` (M2, `compaction.py`) | `ROLE_FOLLOWUP_QUESTION` (M3, module này) |
| --- | --- | --- |
| Đầu vào | các lượt THÔ của phiên ĐANG chạy | vài nhãn than phiền của các phiên ĐÃ đóng |
| Đầu ra đi tới | model đang hỏi tiếp ở cùng phiên | **thẳng tới người bệnh** |
| Sai thì mất gì | phần đầu bối cảnh của một phiên | một câu y khoa bịa, đọc như lời hệ thống |
| Fallback | bản tóm tắt tất định (ghép nguyên văn) | câu tĩnh `history_recall.greeting` |

Vì cột phải nguy hiểm hơn, module này bị siết ở **cả hai đầu**, và cả hai đều bằng code:

1. **Đầu VÀO chỉ có nhãn.** Model không bao giờ nhìn thấy `narrative` (văn xuôi phiếu bàn giao) hay
   `proposed_priority` (đề xuất đang chờ điều dưỡng duyệt, `CLAUDE.md` nguyên tắc 1). Không đưa vào
   thì không có gì để rò ra - chặn ở đầu vào rẻ hơn và chắc hơn mọi câu dặn trong prompt.
2. **Đầu RA bị `_accept` kiểm.** Đúng một câu hỏi, có đúng nhãn đã chắt lọc, không chữ số, không mức
   ưu tiên, không từ chẩn đoán/kê đơn. Trượt bất kỳ điều kiện nào ⇒ dùng câu tĩnh, KHÔNG sửa chữa
   câu model viết: một câu đã sai ở một chỗ là một câu không rõ còn sai ở đâu nữa.

Thứ model được phép thêm vào so với câu tĩnh đúng bằng một thứ: **cách nói**. Nội dung sự kiện thì
`_ranked_complaints` đã chốt xong trước khi prompt được dựng.
"""

from __future__ import annotations

import logging
import re

from src.config import get_settings
from src.services.infra import provider_router
from src.services.stores.conversation_store import PastConversation

logger = logging.getLogger("vmedtriage.followup_writer")

# Nhiet do cua vai tro nay da chuyen sang `Settings.role_temperature_followup_question` (2026-08-25) de moi vai tro
# chinh duoc mot cho, thay vi rai hang so khap cac module. `provider_router._resolve_temperature`
# doc no theo `role=` da truyen san o loi goi ben duoi.
"""Cao hơn `compaction` (0.0) một chút và chỉ một chút: việc ở đây là ĐỔI CÁCH NÓI cho đỡ máy móc,
nên cần một biên độ; nhưng nội dung đã bị chốt sẵn nên biên độ rộng chỉ mua thêm rủi ro trượt guard."""

_MAX_CHARS = 220
"""Trần độ dài. Câu hỏi thăm đứng TRƯỚC câu hỏi bệnh ở lượt mở; dài hơn hai dòng là đẩy câu hỏi thật
xuống dưới màn hình đầu tiên, và người bệnh chỉ trả lời câu cuối cùng họ đọc."""

_SYSTEM_PROMPT = """Bạn viết MỘT câu hỏi thăm mở đầu cho một ứng dụng tư vấn sức khoẻ tiếng Việt.

Người đọc là chính người bệnh, và họ đọc câu này TRƯỚC khi kể chuyện hôm nay.

QUY TẮC BẮT BUỘC:
- Viết đúng MỘT câu, kết thúc bằng dấu hỏi. Không xuống dòng, không gạch đầu dòng, không markdown.
- CHỈ được nhắc tới đúng triệu chứng được nêu trong phần dữ liệu bên dưới, giữ nguyên chữ của nó.
- TUYỆT ĐỐI không thêm bất kỳ chi tiết y khoa nào: không nhiệt độ, không số ngày, không tên bệnh,
  không tên thuốc, không mức độ nặng nhẹ, không lời khuyên xử trí, không nhắc tới cấp cứu hay đi khám.
- Không dùng chữ số.
- Xưng hô: gọi người đọc là "bạn", tự xưng "mình". Giọng quan tâm, ngắn, tự nhiên như người quen hỏi
  thăm - không trang trọng kiểu bệnh viện, không hỏi dồn.
- Không đặt kỳ vọng bắt buộc trả lời: người bệnh bỏ qua câu này để kể chuyện hôm nay là bình thường."""


def compose(
    entries: tuple[PastConversation, ...], *, complaint: str, occurrences: int, fallback: str,
) -> str:
    """Câu hỏi thăm do model viết, hoặc `fallback` khi tắt cờ / model hỏng / trượt guard.

    `complaint` và `occurrences` là KẾT QUẢ đã chắt lọc của `history_recall`, không phải thứ model tự
    tìm trong dữ liệu: chọn nhãn nào là một quyết định tất định, và để model chọn lại nghĩa là hai
    lần mở hội thoại của cùng một lịch sử có thể hỏi về hai chuyện khác nhau.

    Không bao giờ ném - nó chạy ở đuôi một lượt đã xong việc (`refresh_for_user`)."""
    if not get_settings().followup_question_llm_enabled or not complaint:
        return fallback
    try:
        result = provider_router.complete(
            [{"role": "user", "content": _prompt(complaint, occurrences, entries)}],
            role=provider_router.ROLE_FOLLOWUP_QUESTION,
        )
        text = " ".join(result.text.split()).strip()
    except Exception as error:
        logger.warning("followup writer fallback: %s", error)
        return fallback
    if not _accept(text, complaint):
        logger.warning("followup writer rejected by guard: %r", text[:120])
        return fallback
    return text


def _prompt(complaint: str, occurrences: int, entries: tuple[PastConversation, ...]) -> str:
    """Prompt của lượt user. **Chỉ nhãn và số lần**, không phiếu bàn giao, không văn xuôi.

    `occurrences` nói bằng CHỮ chứ không bằng số, vì `_accept` từ chối chữ số ở đầu ra - đưa vào một
    con số rồi cấm nó xuất hiện là dựng sẵn một cái bẫy cho chính guard của mình."""
    repeated = "có, người bệnh đã nhắc lại chuyện này ở nhiều lần trò chuyện trước" if occurrences >= 2 else "không"
    return (
        f"{_SYSTEM_PROMPT}\n\n"
        "DỮ LIỆU (chỉ có bấy nhiêu, không được suy ra gì thêm):\n"
        f"- Triệu chứng người bệnh đã kể ở lần trò chuyện gần đây: {complaint}\n"
        f"- Chuyện này có lặp lại không: {repeated}\n"
        f"- Số lần trò chuyện đã khép lại được xem tới: {_spell(len(entries))}\n\n"
        "Viết câu hỏi thăm ngay, không giải thích gì thêm."
    )


_FORBIDDEN = (
    "cấp cứu", "khám sớm", "tự theo dõi", "nhập viện", "bệnh viện", "bác sĩ", "chẩn đoán",
    "kê đơn", "thuốc", "uống", "nên đi", "phòng khám", "115",
)
"""Từ bị cấm ở ĐẦU RA, và mỗi nhóm cấm vì một lý do khác nhau: ba mức ưu tiên là đề xuất đang chờ
điều dưỡng duyệt (`CLAUDE.md` nguyên tắc 1); "chẩn đoán"/"thuốc"/"kê đơn" là nguyên tắc 2; "đi khám"/
"bệnh viện"/"115" là hướng xử trí - một câu hỏi thăm gợi ý người bệnh đi đâu là đã phân loại họ rồi.

Khớp theo CHUỖI CON chứ không theo từ: "cấp cứu" nằm trong "cấp cứu ngay" và cả hai đều phải trượt."""

_DIGITS = re.compile(r"\d")


def _accept(text: str, complaint: str) -> bool:
    """Guard đầu ra. Trượt một điều kiện là trượt cả câu - không sửa, không cắt, không hỏi lại model.

    Sửa chữa câu model viết (bỏ chữ số đi rồi dùng tiếp) là chỗ dễ sai nhất: thứ còn lại sau khi cắt
    KHÔNG phải câu model định nói, và không ai đọc lại nó trước khi nó tới người bệnh."""
    if not text or len(text) > _MAX_CHARS:
        return False
    if not text.endswith("?"):
        return False
    if text.count("?") != 1:  # nhiều câu hỏi = hỏi dồn ngay ở câu đầu tiên
        return False
    if _DIGITS.search(text):
        return False
    lowered = text.lower()
    if complaint.lower() not in lowered:
        return False
    return not any(word in lowered for word in _FORBIDDEN)


_NUMBER_WORDS = ("không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín", "mười")


def _spell(value: int) -> str:
    return _NUMBER_WORDS[value] if 0 <= value < len(_NUMBER_WORDS) else "nhiều"
