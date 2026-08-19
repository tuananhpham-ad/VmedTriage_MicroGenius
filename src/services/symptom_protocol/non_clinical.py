"""Protocol PHI LÂM SÀNG — chitchat, lifestyle, meta (§4.10 `_guidance/what_to_do_next.md`).

**Điểm quan trọng nhất của §4.10: những thứ đang được gọi chung là "protocol" thực ra là hai loại
khác hẳn nhau, và trộn chúng vào một registry sẽ hỏng cả hai.**

| | Protocol LÂM SÀNG | Protocol PHI LÂM SÀNG (module này) |
| --- | --- | --- |
| Ví dụ | fever, bụng, ngực, khó thở, đầu | lifestyle, meta (chitchat: xem ghi chú dưới) |
| Nội dung | field + tier + cụm + skip-rule + luật triage | intent handler, KHÔNG có checklist |
| Ai viết | Data Lead + review lâm sàng | Engineering |
| Quy mô | ~700 dòng logic lâm sàng mỗi nhóm | vài chục dòng |
| Sinh red flag | Có | **Không** |
| Track | PC (§3.2) | P |

Vì thế chúng **không** vào `PROTOCOL_REGISTRY`: một `SymptomProtocol` giả không có field, không có
cụm, không có luật triage sẽ chảy qua `stage_machine`/`rule_engine`/`coverage` và làm mọi chỉ số độ
phủ vô nghĩa (mẫu số phình lên bằng những phiên chưa bao giờ là ca lâm sàng).

**Ba ràng buộc an toàn, và ràng buộc đầu là quan trọng nhất:**

1. **L0 `text_safety_signals` vẫn chạy trên MỌI lượt**, kể cả lượt chitchat. Module này được hỏi tới
   ở tầng ĐỊNH TUYẾN, sau L0 - nó không có cơ hội nuốt một tín hiệu đỏ. "Uống bia có sao không" và
   "uống bia xong tôi nôn ra máu" đi vào cùng một bộ phân loại, nhưng câu thứ hai đã bị L0 chặn từ
   trước.
2. **KHÔNG đưa lời khuyên y tế.** Mọi handler ở đây kết thúc bằng thu thập + bàn giao, không bằng
   một câu trả lời. Đó không phải sự thận trọng thừa mà là `CLAUDE.md` nguyên tắc 2.
3. **Không tự kết luận "không sao".** Trấn an một người rồi để họ đi là một kết luận lâm sàng, chỉ
   mặc một chiếc áo thân thiện.

> **Về ví dụ "uống bia khi đang dùng kháng sinh"** (§4.10): cách xử lý đúng là hỏi **đang dùng thuốc
> gì, điều trị bệnh gì**, rồi bàn giao — KHÔNG hard-code "kháng sinh + bia ⇒ tê liệt thần kinh".
> Tương tác với rượu phụ thuộc thuốc cụ thể, liều, bệnh nền; một luật rộng như vậy vừa sai về y khoa
> vừa đúng dạng "kết luận" mà nguyên tắc 2 cấm.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum


class NonClinicalLane(str, Enum):
    """Lane phi lâm sàng. `NONE` = đây là chuyện lâm sàng, đi tiếp đường protocol bình thường."""

    NONE = "none"
    LIFESTYLE = "lifestyle"
    """Câu hỏi về sinh hoạt (rượu bia, tập luyện, ăn uống, thuốc đang dùng) KHÔNG kèm triệu chứng."""
    META = "meta"
    """Hỏi về chính hệ thống: "bạn là ai", "dữ liệu của tôi có an toàn không", "bao lâu thì có kết quả"."""


def _fold(text: str) -> str:
    """Bỏ dấu + hạ chữ thường - cùng cách chuẩn hoá với `user_intent`, vì người bệnh gõ điện thoại
    rất hay không bỏ dấu."""
    lowered = (text or "").casefold().replace("đ", "d")
    stripped = unicodedata.normalize("NFD", lowered)
    return "".join(char for char in stripped if unicodedata.category(char) != "Mn")


# ⚠️ **CHITCHAT cố ý KHÔNG có lane riêng.** §4.10 liệt kê nó cùng lifestyle/meta, nhưng trong repo
# này lời chào đã có đường đi đúng từ trước: `controller.build_execution_plan` nhận ra lượt không
# mang dữ kiện lâm sàng và bỏ hẳn lời gọi extractor, còn lượt mở thì `run_open_turn` trả về
# `harvested_nothing` và lặp lại `OPENING_QUESTION` tĩnh - thay vì lao vào bộ câu hỏi lâm sàng.
#
# Thêm một lane chitchat ở đây là dựng đường thứ hai cho cùng một việc, và đường mới còn dở hơn: nó
# thay `OPENING_QUESTION` (câu mở đã cân nhắc từng chữ để người bệnh kể tự nhiên) bằng một câu khác
# nói cùng một ý. Hai bản sao của một hành vi là hai chỗ để chúng lệch nhau.

_LIFESTYLE = (
    "uong bia", "uong ruou", "uong con", "hut thuoc", "thuoc la",
    "tap gym", "chay bo", "tap the duc", "an kieng", "giam can",
    "uong ca phe", "thuc khuya", "mat ngu vi",
)

_META = (
    "ban la ai", "ban la gi", "day la ai", "co phai bac si",
    "du lieu cua toi", "co bao mat", "co an toan khong",
    "bao lau thi co ket qua", "ai se xem", "he thong nay",
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Từ khoá cho thấy tin nhắn CÓ nội dung lâm sàng - khi chúng xuất hiện, mọi lane phi lâm sàng bị huỷ.
# Cố ý rộng và cố ý nghiêng về BỎ SÓT lane phi lâm sàng: định tuyến nhầm một câu tán gẫu vào đường
# lâm sàng chỉ tốn một câu hỏi thừa, còn định tuyến nhầm một triệu chứng vào chitchat là bỏ một ca.
_CLINICAL_MARKERS = (
    "dau", "sot", "nong", "ho ra", "kho tho", "tho", "non", "buon non", "tieu chay",
    "chay mau", "mau", "ngat", "co giat", "chong mat", "met", "sung", "phat ban",
    "tuc nguc", "hoa mat", "run", "lanh", "dau bung", "dau dau", "dau nguc",
    "trieu chung", "benh", "om", "kho chiu", "khong khoe",
)


@dataclass(frozen=True, slots=True)
class NonClinicalVerdict:
    lane: NonClinicalLane = NonClinicalLane.NONE
    matched: tuple[str, ...] = ()

    @property
    def is_non_clinical(self) -> bool:
        return self.lane is not NonClinicalLane.NONE


def classify(message: str) -> NonClinicalVerdict:
    """Tin nhắn -> lane. THUẦN: không state, không I/O, **không model**.

    Tất định trước, model sau - cùng mô hình với `registry.select_protocol`, `user_intent` và L0.
    Router bằng model nhỏ (§4.10, mục 14) sẽ đứng SAU hàm này, không thay nó: sàn deterministic chạy
    trước là điều kiện để tắt hết SLM mà hệ thống vẫn đúng.

    **Bất kỳ dấu hiệu lâm sàng nào cũng huỷ lane phi lâm sàng.** "Uống bia xong tôi đau bụng" là ca
    lâm sàng, dù nó bắt đầu bằng một từ khoá lifestyle - và đó chính là ca mà một bộ phân loại cẩu
    thả sẽ bỏ."""
    folded = _fold(message)
    if not folded.strip():
        return NonClinicalVerdict()
    if any(marker in folded for marker in _CLINICAL_MARKERS):
        return NonClinicalVerdict()

    for lane, phrases in (
        (NonClinicalLane.META, _META),
        (NonClinicalLane.LIFESTYLE, _LIFESTYLE),
    ):
        matched = tuple(phrase for phrase in phrases if phrase in folded)
        if matched:
            return NonClinicalVerdict(lane=lane, matched=matched)
    return NonClinicalVerdict()


# --- Handler: văn bản TĨNH, không qua LLM --------------------------------------------------------
#
# Tĩnh vì cùng lý do với `CATCH_ALL_QUESTION` và các thông điệp an toàn: đây là những câu quyết định
# người bệnh có kể tiếp hay không, và một bản diễn đạt lại có thể vô tình thành lời khuyên y tế.

LIFESTYLE_REPLY = (
    "Câu này liên quan tới sinh hoạt và thuốc men nên mình không tự trả lời được — "
    "nhân viên y tế sẽ xem giúp bạn.\n\n"
    "Để họ trả lời chính xác, bạn cho mình biết: hiện bạn đang dùng thuốc gì, và đang điều trị bệnh gì không?"
)
"""Thu thập rồi BÀN GIAO - không đưa lời khuyên. Hai câu hỏi ở đây (thuốc gì, bệnh gì) đúng là hai
thứ mà người trả lời thật sẽ cần, và chúng cũng đi thẳng vào `current_medications` /
`chronic_conditions` của phiếu bàn giao."""

META_REPLY = (
    "Mình là trợ lý ghi nhận triệu chứng của VMedTriage. Mình không phải bác sĩ và không đưa ra "
    "chẩn đoán — mọi thông tin bạn kể sẽ được nhân viên y tế xem và xác nhận trước khi phản hồi "
    "cho bạn.\n\n"
    "Bạn đang thấy khó chịu thế nào?"
)

_REPLIES = {
    NonClinicalLane.LIFESTYLE: LIFESTYLE_REPLY,
    NonClinicalLane.META: META_REPLY,
}


def reply_for(lane: NonClinicalLane) -> str:
    """Câu trả lời tĩnh của lane. `NONE` -> chuỗi rỗng (caller đi tiếp đường lâm sàng).

    Cả ba câu đều kết thúc bằng một câu hỏi kéo người bệnh về hướng lâm sàng. Trả lời rồi im lặng
    nghĩa là phiên đứng yên, và người bệnh phải tự nghĩ ra việc tiếp theo cần làm."""
    return _REPLIES.get(lane, "")
