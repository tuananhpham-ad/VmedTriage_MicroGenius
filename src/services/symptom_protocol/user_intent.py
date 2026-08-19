"""Ý ĐỊNH của người bệnh về việc DỪNG phiên - THUẦN code, KHÔNG model (§3.3 P3.9, §4.7).

`stage_machine.should_stop` đã có tham số `user_can_continue` từ lâu nhưng chưa ai suy nó ra từ tin
nhắn: "tóm tắt cho tôi đi" hay "tôi không muốn trả lời nữa" không có đường nào tác động vào việc
dừng phiên. Module này là đầu vào còn thiếu đó - không phải một hàm dừng mới.

**Vì sao là bảng cụm từ chứ không phải một "Stop Agent" bằng LLM.** Một model nhận state rồi trả
`CONTINUE`/`SUMMARIZE` sẽ dừng khác nhau giữa các lần chạy trên cùng một state, không test được
bằng fake LLM, và nó chuyển một quyết định AN TOÀN từ code sang model. Cùng mô hình với
`registry.select_protocol` và `text_safety_signals`: tất định trước, model sau (nếu bao giờ cần).

**Bốn ràng buộc, tất cả đều nằm ở tầng gọi chứ không ở đây:**

1. Kết quả của module này CHỈ được dùng để dựng `stage_machine.StopSignals`. Không chọn cụm, không
   đổi protocol, không hạ escalation.
2. Không bao giờ vượt qua nhánh red flag - `should_stop` xét `RED_FLAG` TRƯỚC mọi nhánh ý định.
3. Dừng vì ý định phải đánh phiếu là CHƯA ĐẦY ĐỦ (`HandoffSummary.is_complete`).
4. **Chửi tục đơn lẻ không phải tín hiệu dừng.** Người đang đau và sợ thì nói năng không dễ chịu -
   đó là bối cảnh y tế bình thường. `profanity` chỉ được ĐẾM khi đi kèm việc không trả lời
   (`UncooperativeTracker`), không bao giờ tự nó bật `wants_to_stop`.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_WANTS_TO_STOP_PHRASES: tuple[str, ...] = (
    "khong muon tra loi nua",
    "khong tra loi nua",
    "khong muon tra loi",
    "khong khai nua",
    "khong noi nua",
    "toi muon dung",
    "minh muon dung",
    "dung lai di",
    "dung o day",
    "dung hoi nua",
    "dung hoi di",
    "thoi dung hoi",
    "khoi hoi nua",
    "ket thuc di",
    "ket thuc o day",
    "tom tat cho toi",
    "tom tat giup toi",
    "tom tat di",
    "tong hop cho toi",
    "tong hop giup toi",
    "chot luon di",
    "chot lai di",
    "cho toi ket qua luon",
)
"""Người bệnh nói RÕ là họ muốn dừng, hoặc muốn đi thẳng tới phiếu tóm tắt.

Cả hai đều ra cùng một hành động - đóng phiên và giao phiếu CHƯA ĐẦY ĐỦ cho điều dưỡng - nên không
tách hai mã. Cụm từ đều là mệnh lệnh đủ dài để không đụng phải câu kể bình thường: "dừng" một mình
KHÔNG có ở đây vì "tôi bị đau khi dừng lại" cũng chứa nó."""

_NO_MORE_SYMPTOMS_PHRASES: tuple[str, ...] = (
    "khong con gi nua",
    "khong con gi khac",
    "khong con trieu chung nao khac",
    "khong con trieu chung gi khac",
    "khong con dau hieu nao khac",
    "het roi do",
    "chi co the thoi",
    "chi vay thoi",
    "co the thoi",
    "the thoi a",
    "khong con gi de ke",
)
"""Người bệnh khẳng định đã kể hết. Tín hiệu MỀM - xem `should_stop`: còn cụm chưa hỏi mang field
M0/M1 thì vẫn hỏi tiếp, chỉ khác là phải nói rõ vì sao còn hỏi thêm."""

_PROFANITY_TOKENS: frozenset[str] = frozenset(
    {
        "dm", "dmm", "vcl", "vl", "cc", "clm", "cmm", "dcm", "vkl",
        "deo", "đéo", "cak", "lon", "cut", "shit", "fuck", "damn",
    }
)
"""Danh sách CỐ TÌNH ngắn và chỉ khớp NGUYÊN TỪ. Nó không phải bộ lọc nội dung - nó chỉ là một trong
ba tín hiệu đếm bất hợp tác, và bắt nhầm ở đây (`"lon"` trong "lớn") sẽ đẩy một người bệnh đang hợp
tác vào nhánh dừng. Vì thế khớp sau khi đã bỏ dấu VÀ tách theo ranh giới từ."""

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _fold(text: str) -> str:
    """Bỏ dấu + hạ chữ thường. Người bệnh gõ điện thoại rất hay không bỏ dấu ("khong tra loi nua"),
    nên bảng cụm từ được viết sẵn ở dạng không dấu và mọi tin nhắn đều được quy về dạng đó."""
    lowered = (text or "").casefold()
    lowered = lowered.replace("đ", "d")
    stripped = unicodedata.normalize("NFD", lowered)
    return "".join(char for char in stripped if unicodedata.category(char) != "Mn")


@dataclass(frozen=True, slots=True)
class UserIntent:
    """Ý định đọc được từ ĐÚNG MỘT tin nhắn. Không giữ lịch sử - phần đếm liên tiếp là việc của
    `UncooperativeTracker`, để một hàm thuần vẫn test được bằng một chuỗi đầu vào."""

    wants_to_stop: bool = False
    no_more_symptoms: bool = False
    profanity: bool = False
    matched: tuple[str, ...] = ()
    """Cụm từ đã khớp - đi vào log để trả lời được "vì sao phiên này dừng" bằng dữ liệu."""


def classify(message: str) -> UserIntent:
    """Tin nhắn -> ý định. THUẦN: không state, không I/O, không model."""
    folded = _fold(message)
    if not folded.strip():
        return UserIntent()

    matched = tuple(phrase for phrase in _WANTS_TO_STOP_PHRASES if phrase in folded)
    no_more = tuple(phrase for phrase in _NO_MORE_SYMPTOMS_PHRASES if phrase in folded)
    tokens = set(_TOKEN_RE.findall(folded))
    return UserIntent(
        wants_to_stop=bool(matched),
        no_more_symptoms=bool(no_more),
        profanity=bool(tokens & _PROFANITY_TOKENS),
        matched=matched + no_more,
    )


UNCOOPERATIVE_STREAK_LIMIT = 2
"""Số lượt liên tiếp vừa lạc đề vừa KHÔNG thu được field mới trước khi agent hỏi lại một lần (§4.7b).

2 chứ không phải 1: một lượt lạc đề đơn lẻ là chuyện bình thường trong hội thoại y tế - người bệnh
hỏi ngược, kể lan man, hoặc bực. Dừng ngay ở lượt đầu là bỏ ca."""


@dataclass(slots=True)
class UncooperativeTracker:
    """Bộ đếm bất hợp tác của MỘT phiên. Đếm ba tín hiệu như §4.7b, không nhiều hơn.

    Máy trạng thái đúng ba nấc, và nấc giữa là điểm mấu chốt - agent HỎI MỘT LẦN trước khi bỏ cuộc:

        hợp tác ──(lạc đề + không thu được field mới) x2──> đã hỏi lại ──(vẫn vậy)──> DỪNG

    Bất kỳ lượt nào thu được field mới đều đưa bộ đếm về 0 và gỡ cờ đã-hỏi-lại: người bệnh quay lại
    hợp tác thì phiên tiếp tục bình thường, không mang theo "án tích" của mấy lượt trước."""

    streak: int = 0
    prompted: bool = False
    """Đã phát câu hỏi xác nhận "bạn muốn dừng ở đây không" chưa. Chỉ hỏi ĐÚNG một lần cả phiên -
    hỏi mãi một câu là cách chắc chắn nhất để người bệnh bỏ giữa chừng (cùng lý do với
    `Session.asked_safety_signal_codes`)."""

    def record_turn(self, *, off_topic: bool, information_gain: bool) -> None:
        """Ghi kết quả một lượt.

        `information_gain` là "lượt vừa rồi có thu được field nào mới không" - lấy từ kết quả trích
        xuất thật, không phải từ nhãn `dialogue_act` của model. Một lượt có thu được field thì dù
        model gán nhãn gì cũng KHÔNG tính là bất hợp tác: đó là dữ liệu lâm sàng thật đi vào phiếu."""
        if information_gain or not off_topic:
            self.streak = 0
            self.prompted = False
            return
        self.streak += 1

    @property
    def should_prompt(self) -> bool:
        """Đã tới lúc hỏi một lần "bạn có muốn dừng không" chưa - CHƯA phải lúc dừng."""
        return self.streak >= UNCOOPERATIVE_STREAK_LIMIT and not self.prompted

    @property
    def should_stop(self) -> bool:
        """Đã hỏi rồi mà vẫn không hợp tác thêm một lượt nữa."""
        return self.prompted and self.streak > UNCOOPERATIVE_STREAK_LIMIT


UNCOOPERATIVE_PROMPT = (
    "Nếu bạn không muốn bổ sung thêm, mình có thể tổng hợp những gì đã có. "
    "Bạn muốn dừng ở đây không?"
)
"""Câu hỏi TĨNH, không qua LLM - cùng lý do với `session.CATCH_ALL_QUESTION`: đây là câu quyết định
phiên còn chạy hay không, nên nó không được diễn đạt lại khác nhau giữa các lượt."""
