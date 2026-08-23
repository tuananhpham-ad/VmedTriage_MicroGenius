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
    LOW_CONTENT = "low_content"
    """Tin nhắn chỉ có dấu câu/ký tự rời rạc, chưa đủ để hiểu người dùng cần gì."""
    NO_SYMPTOMS = "no_symptoms"
    """Người dùng nói rõ hiện không có triệu chứng/khó chịu nào cần khai thác."""
    OUT_OF_SCOPE = "out_of_scope"
    """Câu hỏi ngoài phạm vi y tế của trợ lý, ví dụ giao thông/hành chính."""
    LIFESTYLE = "lifestyle"
    """Câu hỏi về sinh hoạt (rượu bia, tập luyện, ăn uống, thuốc đang dùng) KHÔNG kèm triệu chứng."""
    META = "meta"
    """Hỏi về chính hệ thống: "bạn là ai", "dữ liệu của tôi có an toàn không", "bao lâu thì có kết quả"."""
    CHITCHAT = "chitchat"
    """Chào hỏi, cảm ơn, tạm biệt, hỏi vu vơ - tin nhắn KHÔNG mang ý định y tế nào."""


def _fold(text: str) -> str:
    """Bỏ dấu + hạ chữ thường - cùng cách chuẩn hoá với `user_intent`, vì người bệnh gõ điện thoại
    rất hay không bỏ dấu."""
    lowered = (text or "").casefold().replace("đ", "d")
    stripped = unicodedata.normalize("NFD", lowered)
    return "".join(char for char in stripped if unicodedata.category(char) != "Mn")


# ⚠️ **CHITCHAT trước đây cố ý KHÔNG có lane riêng — 2026-08-23 đã đảo lại.** Ghi lại cả hai vế để
# lần sau ai đó muốn gỡ thì biết mình đang gỡ cái gì.
#
# LẬP LUẬN CŨ: lời chào đã có đường đi "đủ dùng" - `controller.build_execution_plan` nhận ra lượt
# không mang dữ kiện lâm sàng và bỏ hẳn lời gọi extractor, còn lượt mở thì `run_open_turn` trả
# `harvested_nothing` và lặp lại `OPENING_QUESTION`. Thêm lane mới là dựng đường thứ hai cho cùng
# một việc.
#
# VÌ SAO ĐẢO: "đủ dùng" chỉ đúng ở vế CHI PHÍ, không đúng ở vế TRẢ LỜI. Đo thật trên phiên có lượt
# mở (2026-08-23):
#
#   "chào bạn"             -> lane none, 0 lời gọi model, trả lời = LẶP LẠI câu mở
#   "hôm nay trời đẹp nhỉ" -> lane none, extractor CHẠY THẬT (~2.530 token), trả lời = LẶP LẠI câu mở
#
# Vế một: người bệnh chào, hệ thống không chào lại mà hỏi lại đúng câu vừa hỏi. Đó không phải "đường
# đi đúng", đó là không có câu trả lời. Vế hai: lớp đỡ của controller KHÔNG kín - một câu về thời
# tiết vẫn nạp trọn schema y tế để trích xuất.
#
# Lane này KHÔNG thay `OPENING_QUESTION`: nó trả lời lời chào RỒI kéo về đúng câu mở đó (xem
# `CHITCHAT_REPLIES`), nên không có hai bản sao của một hành vi.

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

_OUT_OF_SCOPE = (
    "xe buyt", "xe bus", "tuyen so", "tuyen xe", "lo trinh", "tram xe", "ben xe",
    "duong nguyen trai", "nguyen trai", "giao thong", "di qua duong", "con chay qua",
)

_NO_SYMPTOMS = (
    "khong thay kho chiu",
    "khong co kho chiu",
    "khong thay trieu chung",
    "khong co trieu chung",
    "khong bi gi",
    "khong sao ca",
    "van binh thuong",
    "minh binh thuong",
    "toi binh thuong",
    "em binh thuong",
)

_CHITCHAT = (
    "chao ban", "chao anh", "chao chi", "chao em", "xin chao", "hello", "helo", "hi ban",
    "alo", "e oi", "ban oi", "cam on", "cam on ban", "thanks", "thank you", "tks",
    "tam biet", "bye", "ban ten gi", "ban khoe khong", "how are you", "may gio roi",
    "troi dep", "ban dang lam gi", "noi chuyen voi minh",
)
"""Chào hỏi / cảm ơn / tạm biệt / hỏi vu vơ. Danh sách này CỐ Ý ngắn và cố ý không cố phủ hết: nó là
sàn tất định, còn phần đuôi dài của ngôn ngữ tự nhiên là việc của `lane_model` (§4.10 mục 14).

Vẫn giữ dạng cụm từ tiếng Việt KHÔNG DẤU vì `_fold` bỏ dấu trước khi so - người bệnh gõ điện thoại
rất hay không bỏ dấu. Vài cụm tiếng Anh ở đây chỉ là lưới tối thiểu cho trường hợp hay gặp nhất."""

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _matcher(phrases: tuple[str, ...]) -> tuple[tuple[str, re.Pattern[str]], ...]:
    """Biên dịch cụm từ thành mẫu khớp theo RANH GIỚI TỪ.

    ⚠️ Bản trước dùng `phrase in folded` - khớp substring trong lòng từ, và nó sai thật (đo
    2026-08-23):

        "hôm nay trời đẹp nhỉ" -> "hom nay troi dep nhi" khớp marker "om"  (ốm)
        "thôi khỏi"            -> "thoi khoi"            khớp marker "tho" (thở)

    Câu đầu vì thế bị coi là chuyện lâm sàng và nạp trọn schema y tế (~2.530 token) để trích xuất từ
    một câu về thời tiết.

    `\b` chạy được ở đây vì `_fold` đã bỏ dấu, nên chuỗi còn lại thuần ASCII. Cụm nhiều từ
    ("ho ra", "dau bung") vẫn khớp bình thường - ranh giới chỉ đặt ở hai đầu cụm.

    Cái này KHÔNG chữa được ca "bắt đầu" -> "bat dau" khớp "dau", vì `đau` và `đầu` bỏ dấu ra cùng
    một chữ. Đó là giới hạn của việc bỏ dấu, và nó rơi về phía AN TOÀN: thừa một lượt hỏi lâm sàng,
    không phải bỏ sót một triệu chứng."""
    return tuple((phrase, re.compile(rf"\b{re.escape(phrase)}\b")) for phrase in phrases)


def _matches(folded: str, compiled: tuple[tuple[str, re.Pattern[str]], ...]) -> tuple[str, ...]:
    return tuple(phrase for phrase, pattern in compiled if pattern.search(folded))

# Từ khoá cho thấy tin nhắn CÓ nội dung lâm sàng - khi chúng xuất hiện, mọi lane phi lâm sàng bị huỷ.
# Cố ý rộng và cố ý nghiêng về BỎ SÓT lane phi lâm sàng: định tuyến nhầm một câu tán gẫu vào đường
# lâm sàng chỉ tốn một câu hỏi thừa, còn định tuyến nhầm một triệu chứng vào chitchat là bỏ một ca.
_CLINICAL_MARKERS = (
    "dau", "sot", "nong", "ho ra", "kho tho", "tho", "non", "buon non", "tieu chay",
    "chay mau", "mau", "ngat", "co giat", "chong mat", "met", "sung", "phat ban",
    "tuc nguc", "hoa mat", "run", "lanh", "dau bung", "dau dau", "dau nguc",
    "trieu chung", "benh", "om", "kho chiu", "khong khoe",
)


_LIFESTYLE_RE = _matcher(_LIFESTYLE)
_META_RE = _matcher(_META)
_OUT_OF_SCOPE_RE = _matcher(_OUT_OF_SCOPE)
_NO_SYMPTOMS_RE = _matcher(_NO_SYMPTOMS)
_CHITCHAT_RE = _matcher(_CHITCHAT)
_CLINICAL_MARKERS_RE = _matcher(_CLINICAL_MARKERS)
"""Biên dịch MỘT lần lúc import. 74 mẫu × mỗi lượt hội thoại - biên dịch lại mỗi lần gọi là trả tiền
cho cùng một việc ở mọi tin nhắn."""


@dataclass(frozen=True, slots=True)
class NonClinicalVerdict:
    lane: NonClinicalLane = NonClinicalLane.NONE
    matched: tuple[str, ...] = ()
    clinical_markers: tuple[str, ...] = ()
    """Dấu hiệu lâm sàng đã bắt được trong tin nhắn. Chỉ có nghĩa khi `lane is NONE`, và nó phân biệt
    HAI trạng thái mà bản trước gộp làm một:

    - `NONE` + có marker  = "đây CHẮC CHẮN là chuyện lâm sàng" -> chốt, không hỏi ai nữa;
    - `NONE` + không marker = "tầng keyword KHÔNG BIẾT" -> đây mới là chỗ `lane_model` được hỏi.

    Gộp hai trạng thái này lại thì tầng model hoặc bị hỏi cả khi đã có dấu hiệu lâm sàng (nguy hiểm:
    nó có cửa lật một ca thật thành chitchat), hoặc không bao giờ được hỏi (vô dụng)."""
    source: str = "keyword"
    """`"keyword"` | `"model"` - ai ra phán quyết này. Để log và để đo, không nhánh nào đọc nó."""
    score: float = 1.0
    """Điểm tin cậy. Tầng keyword luôn 1.0 (khớp là khớp); tầng model trả điểm thật của nó."""

    @property
    def is_non_clinical(self) -> bool:
        return self.lane is not NonClinicalLane.NONE

    @property
    def is_undecided(self) -> bool:
        """Tầng keyword không quyết được - chưa thấy dấu hiệu lâm sàng nào mà cũng không khớp lane
        nào. Đây là điều kiện DUY NHẤT để tầng model được hỏi tới."""
        return self.lane is NonClinicalLane.NONE and not self.clinical_markers


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
        return NonClinicalVerdict(lane=NonClinicalLane.LOW_CONTENT)
    tokens = tuple(_TOKEN_RE.findall(folded))
    if not tokens:
        return NonClinicalVerdict(lane=NonClinicalLane.LOW_CONTENT, matched=(folded.strip(),))

    no_symptoms = _matches(folded, _NO_SYMPTOMS_RE)
    positive_clinical = tuple(
        marker for marker in _matches(folded, _CLINICAL_MARKERS_RE)
        if marker not in {"kho chiu", "trieu chung", "benh", "khong khoe"}
    )
    if no_symptoms and not positive_clinical:
        return NonClinicalVerdict(lane=NonClinicalLane.NO_SYMPTOMS, matched=no_symptoms)

    markers = _matches(folded, _CLINICAL_MARKERS_RE)
    if markers:
        return NonClinicalVerdict(clinical_markers=markers)

    for lane, compiled in (
        (NonClinicalLane.META, _META_RE),
        (NonClinicalLane.LIFESTYLE, _LIFESTYLE_RE),
        (NonClinicalLane.OUT_OF_SCOPE, _OUT_OF_SCOPE_RE),
        # CHITCHAT xét CUỐI trong nhóm: "cảm ơn, mình uống bia có sao không" vừa mang lời cảm ơn vừa
        # mang câu hỏi lifestyle, và câu hỏi mới là thứ cần trả lời.
        (NonClinicalLane.CHITCHAT, _CHITCHAT_RE),
    ):
        matched = _matches(folded, compiled)
        if matched:
            return NonClinicalVerdict(lane=lane, matched=matched)
    return NonClinicalVerdict()


# --- Handler: văn bản TĨNH, không qua LLM --------------------------------------------------------
#
# Tĩnh vì cùng lý do với `CATCH_ALL_QUESTION` và các thông điệp an toàn: đây là những câu quyết định
# người bệnh có kể tiếp hay không, và một bản diễn đạt lại có thể vô tình thành lời khuyên y tế.

LIFESTYLE_REPLIES = (
    (
        "Câu này liên quan tới sinh hoạt và thuốc men nên mình không tự trả lời được — "
        "nhân viên y tế sẽ xem giúp bạn.\n\n"
        "Để họ trả lời chính xác, bạn cho mình biết: hiện bạn đang dùng thuốc gì, và đang điều trị bệnh gì không?"
    ),
    (
        "Mình chưa tự kết luận được câu này vì còn phụ thuộc thuốc và tình trạng sức khỏe cụ thể. "
        "Bạn cho mình biết bạn đang dùng thuốc gì và đang điều trị bệnh gì để nhân viên y tế xem giúp nhé."
    ),
    (
        "Phần này cần người chuyên môn xem theo thuốc và bệnh nền của bạn. "
        "Bạn mô tả giúp mình thuốc đang dùng và bệnh đang điều trị, mình sẽ ghi lại để chuyển cho nhân viên y tế."
    ),
)
"""Thu thập rồi BÀN GIAO - không đưa lời khuyên. Hai câu hỏi ở đây (thuốc gì, bệnh gì) đúng là hai
thứ mà người trả lời thật sẽ cần, và chúng cũng đi thẳng vào `current_medications` /
`chronic_conditions` của phiếu bàn giao."""

META_REPLIES = (
    (
        "Mình là trợ lý ghi nhận triệu chứng của VMedTriage. Mình không phải bác sĩ và không đưa ra "
        "chẩn đoán — mọi thông tin bạn kể sẽ được nhân viên y tế xem và xác nhận trước khi phản hồi "
        "cho bạn.\n\n"
        "Bạn đang thấy khó chịu thế nào?"
    ),
    (
        "Mình hỗ trợ ghi nhận thông tin sức khỏe ban đầu, không thay bác sĩ chẩn đoán hay kê đơn. "
        "Nếu bạn đang cần hỗ trợ y tế, bạn kể giúp mình triệu chứng hiện tại nhé."
    ),
    (
        "Đây là trợ lý thu thập triệu chứng để nhân viên y tế xem lại. "
        "Bạn có thể bắt đầu bằng điều đang làm bạn khó chịu hoặc lo nhất."
    ),
)

LOW_CONTENT_REPLIES = (
    "Mình chưa nhận được mô tả rõ. Nếu bạn cần hỗ trợ y tế, bạn hãy kể triệu chứng hoặc điều đang làm bạn lo nhất nhé.",
    "Mình chưa hiểu được ý bạn từ tin nhắn vừa rồi. Bạn mô tả ngắn triệu chứng hoặc vấn đề sức khỏe cần hỗ trợ nhé.",
    "Tin nhắn này hơi ít thông tin nên mình chưa ghi nhận được gì. Bạn cho mình biết hiện đang khó chịu ở đâu hoặc thấy bất thường gì nhé.",
)

NO_SYMPTOMS_REPLIES = (
    (
        "Mình hiểu là hiện tại bạn không thấy khó chịu hay có triệu chứng cần hỗ trợ. "
        "Nếu cần đánh giá y tế sau này, bạn chỉ cần mô tả điều bất thường đang gặp nhé."
    ),
    (
        "Vậy hiện tại mình chưa có triệu chứng nào để ghi nhận. "
        "Khi bạn thấy có điều bất thường về sức khỏe, cứ nhắn mô tả ngắn cho mình nhé."
    ),
    (
        "Mình ghi nhận là bạn chưa có vấn đề sức khỏe cụ thể muốn khai báo lúc này. "
        "Nếu tình trạng thay đổi, bạn có thể kể triệu chứng để mình hỗ trợ phân luồng."
    ),
)

OUT_OF_SCOPE_REPLIES = (
    (
        "Mình chỉ hỗ trợ ghi nhận triệu chứng và mức độ khẩn cấp y tế, nên chưa tra được thông tin này. "
        "Nếu bạn cần hỗ trợ sức khỏe, bạn hãy mô tả triệu chứng hoặc điều đang làm bạn lo nhất nhé."
    ),
    (
        "Câu này nằm ngoài phạm vi hỗ trợ y tế của mình, nên mình chưa thể kiểm tra giúp. "
        "Nếu bạn muốn đánh giá vấn đề sức khỏe, bạn kể triệu chứng hiện tại cho mình nhé."
    ),
    (
        "Mình chưa hỗ trợ tra cứu thông tin ngoài y tế như nội dung này. "
        "Còn nếu bạn đang có triệu chứng hoặc lo ngại sức khỏe, bạn mô tả ngắn để mình ghi nhận nhé."
    ),
)

CHITCHAT_REPLIES = (
    (
        "Chào bạn, mình là trợ lý ghi nhận triệu chứng của VMedTriage.\n\n"
        "Bạn hoặc người nhà đang thấy khó chịu thế nào? Bạn cứ kể theo cách dễ nhất với mình nhé."
    ),
    (
        "Mình ở đây rồi, bạn cứ nhắn nhé. Để hỗ trợ được bạn, mình cần biết bạn đang thấy khó chịu ở đâu "
        "hoặc có điều gì bất thường về sức khỏe không?"
    ),
    (
        "Cảm ơn bạn đã nhắn. Mình hỗ trợ ghi nhận triệu chứng để nhân viên y tế xem lại - "
        "bạn kể giúp mình điều đang làm bạn khó chịu hoặc lo nhất nhé."
    ),
)
"""Bản TĨNH của lane chitchat - cũng là bản rơi về khi LLM chết hoặc bị guard từ chối.

Câu đầu kết thúc bằng **nguyên văn `registry.OPENING_QUESTION`**, có chủ đích: đó là câu đã cân nhắc
từng chữ để người bệnh kể tự nhiên, và lane này chào hỏi rồi trả người bệnh về đúng câu đó chứ không
viết một câu mở thứ hai cạnh tranh với nó."""

_REPLIES = {
    NonClinicalLane.LOW_CONTENT: LOW_CONTENT_REPLIES,
    NonClinicalLane.NO_SYMPTOMS: NO_SYMPTOMS_REPLIES,
    NonClinicalLane.OUT_OF_SCOPE: OUT_OF_SCOPE_REPLIES,
    NonClinicalLane.LIFESTYLE: LIFESTYLE_REPLIES,
    NonClinicalLane.META: META_REPLIES,
    NonClinicalLane.CHITCHAT: CHITCHAT_REPLIES,
}


def _variant_index(variant_key: object, size: int) -> int:
    """Chọn biến thể ổn định, không random.

    Caller truyền `turn_count` để cùng một lane ở hai lượt gần nhau không đọc y nguyên một câu. Không
    dùng LLM ở đây vì các câu phi lâm sàng là guard rails: được phép đổi giọng, không được đổi nghĩa.
    """
    if size <= 1:
        return 0
    if isinstance(variant_key, int):
        return variant_key % size
    text = str(variant_key or "")
    return sum((index + 1) * ord(char) for index, char in enumerate(text)) % size


def reply_for(lane: NonClinicalLane, *, variant_key: object = 0) -> str:
    """Câu trả lời của lane. `NONE` -> chuỗi rỗng (caller đi tiếp đường lâm sàng).

    Cả ba câu đều kết thúc bằng một câu hỏi kéo người bệnh về hướng lâm sàng. Trả lời rồi im lặng
    nghĩa là phiên đứng yên, và người bệnh phải tự nghĩ ra việc tiếp theo cần làm."""
    variants = _REPLIES.get(lane, ())
    if not variants:
        return ""
    return variants[_variant_index(variant_key, len(variants))]
