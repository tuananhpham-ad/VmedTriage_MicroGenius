"""L0 `text_safety_signals` — tầng an toàn chạy trên TEXT THÔ, TRƯỚC mọi lời gọi model.

Lý do tồn tại (khoảng trống defense-in-depth): escalation của luồng chuẩn hiện chỉ đến từ
`common_safety/rules.py` chạy trên field ĐÃ được LLM trích xuất. Model trả JSON hỏng, timeout, hoặc
provider chết ⇒ không còn lớp tất định nào quan sát lời người bệnh vừa gõ. Tầng này lấp đúng chỗ đó:
KHÔNG gọi model, không phụ thuộc JSON parse được hay không.

**Vì sao không nối thẳng `detect_text_red_flags` vào `EMERGENCY`.** Matcher trong
`engines/red_flag_text_rules.py` chỉ so khớp substring, nên cả ba câu phủ định sau đều "khớp red
flag": "Tôi không co giật", "Bé không khó thở nặng", "Không có môi tím hay co giật". Biến một match
trần thành cấp cứu là dạy người bệnh bỏ qua cảnh báo của hệ thống.

Vì vậy output của tầng này là TÍN HIỆU ỨNG VIÊN có trạng thái, không phải `reason_codes` chính thức:

- `CONFIRMED_POSITIVE` — dương tính rõ, đang diễn ra, không bị guard nào loại. Chỉ những mã nằm
  trong `SHORT_CIRCUIT_CODES` mới được short-circuit bằng thông điệp tĩnh.
- `NEEDS_CONFIRMATION` — có nhắc tới dấu hiệu nhưng còn mơ hồ (tiền sử, người khác, giả định, không
  chắc). KHÔNG tự kết luận, nhưng cũng KHÔNG được im lặng bỏ qua: caller phải đẩy cụm xác nhận red
  flag lên trước.
- `SUPPRESSED` — đã bị guard phủ định loại. Chỉ để audit.

Ba guard tất định, chạy trên chuỗi đã chuẩn hoá (bỏ dấu, casefold) của `normalize_red_flag_text`:

1. **Polarity** — hạt phủ định đứng TRƯỚC cụm khớp, trong cùng một mệnh đề (`_NEGATION_WINDOW` ký
   tự, cắt tại dấu câu và tại liên từ đối lập). Phủ định lan qua liên từ liệt kê ("hay", "và") nên
   "không có môi tím hay co giật" loại được cả hai mã.
2. **Temporality** — mốc thời gian quá khứ/tiền sử ⇒ hạ xuống `NEEDS_CONFIRMATION` (KHÔNG loại hẳn:
   "hôm qua bé co giật" vẫn đáng hỏi lại). Dấu hiệu "đang/hiện tại/bây giờ" trong cùng mệnh đề ghi
   đè guard này.
3. **Subject** — nói về người khác ("bạn tôi", "hàng xóm", "đọc trên mạng") ⇒ `NEEDS_CONFIRMATION`.
   KHÔNG tính người nhà đang được tư vấn hộ ("con tôi", "bé") là chủ thể khác — đó chính là bệnh
   nhân trong phần lớn ca nhi.

Danh mục luật dùng chung `TEXT_RED_FLAG_RULES` (`engines/red_flag_text_rules.py`) — một danh mục,
không nhân bản. Module này chỉ thêm tầng guard + phân loại trạng thái quanh nó.

**`SHORT_CIRCUIT_CODES` cần clinical governance ký duyệt trước khi chạy production.** Danh sách cố ý
hẹp: mỗi mã trong đó là một đường đi thẳng từ substring match tới thông điệp gọi 115.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from src.services.engines.red_flag_text_rules import (
    TEXT_RED_FLAG_RULES,
    normalize_red_flag_text,
)


class SignalStatus(str, Enum):
    CONFIRMED_POSITIVE = "confirmed_positive"
    NEEDS_CONFIRMATION = "needs_confirmation"
    SUPPRESSED = "suppressed"


# Guard nào đã đổi trạng thái của tín hiệu — ghi lại để log/audit trả lời được "vì sao câu này không
# escalate", thay vì để người đọc log tự đoán.
GUARD_NONE = ""
GUARD_NEGATED = "negated"
GUARD_UNCERTAIN = "uncertain"
GUARD_OTHER_SUBJECT = "other_subject"
GUARD_HYPOTHETICAL = "hypothetical"
GUARD_INTERROGATIVE = "interrogative"
GUARD_HISTORICAL = "historical"
GUARD_NOT_REVIEWED = "not_reviewed"
"""Dương tính rõ nhưng mã CHƯA nằm trong danh sách được duyệt short-circuit ⇒ đi đường xác nhận."""


SHORT_CIRCUIT_CODES: frozenset[str] = frozenset({
    # Ý thức và thần kinh cấp
    "loss_of_consciousness",
    "cannot_be_woken",
    "seizure",
    "ongoing_seizure",
    "child_convulsion",
    "child_lethargic",
    # Đường thở và hô hấp
    "not_breathing",
    "gasping",
    "severe_breathing",
    "cyanosis",
    "child_blue_lips",
    "choking",
    "stridor",
    "tongue_swelling",
    "coughing_blood",
    # Tim mạch
    "severe_chest_pain",
    "chest_pain_radiating",
    "chest_pain_sweating",
    "cardiac_arrest_report",
    # Chảy máu
    "vomiting_blood",
    "heavy_bleeding",
    "uncontrolled_wound_bleeding",
    "postpartum_heavy_bleeding",
    "pregnancy_heavy_bleeding",
    # Sản khoa
    "pregnancy_seizure",
    # Ngộ độc, tự hại, tai nạn
    "poison_ingestion",
    "medication_overdose",
    "drug_overdose",
    "self_harm_imminent",
    "drowning",
    "electrical_injury",
    "snakebite",
    "severe_allergic_reaction",
})
"""Mã được phép short-circuit thẳng ra thông điệp tĩnh khi `CONFIRMED_POSITIVE`.

Tiêu chí chọn: cụm từ đặc hiệu (khó khớp nhầm trong câu chuyện thường ngày) VÀ nguy hiểm tức thì
theo phút. Cố ý LOẠI những mã có cụm từ đời thường: `throat_swelling` ("sưng họng") gặp ở mọi ca
viêm họng thường; `severe_abdominal_rigidity` ("đau bụng không chịu nổi") là mô tả mức độ chủ quan.
Những mã đó vẫn sinh tín hiệu, nhưng đi đường `NEEDS_CONFIRMATION`."""


_RULES_BY_CODE = {text_rule.code: text_rule for text_rule in TEXT_RED_FLAG_RULES}


_NEGATION_WINDOW = 60
"""Số ký tự tối đa lùi về trước cụm khớp để tìm hạt phủ định.

Có trần vì phủ định tiếng Việt là tiền-vị-ngữ và bám sát vị ngữ nó phủ định. Không có trần thì
"tôi không sốt gì cả mà tự nhiên chiều nay co giật" bị coi là phủ định co giật — mất đúng tín hiệu
mà tầng này sinh ra để bắt."""

_SEGMENT_BOUNDARY = ".;!?\n,"
"""Ranh giới mệnh đề cho guard phủ định. Dấu PHẨY tính là ranh giới: "không có môi tím, co giật từ
sáng" hiểu theo hướng nhạy hơn (không suy diễn rằng phủ định lan sang vế sau)."""

_SENTENCE_BOUNDARY = ".;!?\n"
"""Ranh giới câu cho guard thời gian/chủ thể — hai loại cue này thường đứng ở đầu câu, cách cụm khớp
một hoặc vài mệnh đề ("Hôm qua bé sốt, tối thì co giật")."""


def _cue_pattern(*cues: str) -> re.Pattern[str]:
    """Khớp theo RANH GIỚI TỪ trên chuỗi đã bỏ dấu — `\\b` không đủ vì cue có khoảng trắng bên trong.

    Sắp theo độ dài giảm dần để cue dài thắng cue ngắn ("chưa từng" trước "chưa")."""
    joined = "|".join(re.escape(normalize_red_flag_text(cue)) for cue in sorted(cues, key=len, reverse=True))
    return re.compile(rf"(?<![a-z0-9])(?:{joined})(?![a-z0-9])")


# CỐ Ý không có "chả", "hông", "đâu có": sau khi bỏ dấu chúng va vào từ thường gặp trong chính
# ngữ cảnh này — "chả"/"cha" (bố), "hông"/"họng" ("đau họng"), "đâu có"/"đau cổ". Một cue phủ định
# khớp nhầm là một dấu hiệu đỏ bị nuốt mất, nên danh sách này chỉ nhận cue không mơ hồ khi bỏ dấu.
_NEGATION_CUES = _cue_pattern("không", "ko", "k", "chẳng", "chưa", "hết", "làm gì có")
_NEGATION_EXCEPTIONS = _cue_pattern(
    # "không phải X mà Y": phủ định trọng tâm, KHÔNG phủ định vị ngữ đứng sau ("không phải tôi mà
    # con tôi bị co giật"). "hết sức" là từ nhấn mạnh ("hết sức khó thở"), ngược hẳn với "hết sốt".
    # Các cue còn lại là bất định, không phải phủ định.
    "không phải", "không biết", "không rõ", "không chắc", "không hiểu", "chưa rõ", "chưa biết",
    "hết sức",
)
_CONTRAST_CUES = _cue_pattern(
    # Cắt phạm vi phủ định: vế sau liên từ đối lập là một khẳng định mới.
    "nhưng", "mà", "tuy nhiên", "thế nhưng", "còn", "rồi", "sau đó", "đến khi",
)
_UNCERTAIN_CUES = _cue_pattern(
    "không biết", "không rõ", "không chắc", "chưa rõ", "chưa biết", "hình như", "có vẻ", "chắc là",
    "hay là", "nghi", "sợ là", "không hiểu",
)
_OTHER_SUBJECT_CUES = _cue_pattern(
    # CỐ Ý không có "con tôi", "bé", "cháu": người nhà được tư vấn hộ CHÍNH LÀ bệnh nhân.
    "bạn tôi", "bạn mình", "bạn em", "người quen", "hàng xóm", "đồng nghiệp", "người ta",
    "trong phim", "trên mạng", "nghe nói", "đọc báo", "bệnh nhân khác", "sếp tôi", "thầy tôi",
)
_HYPOTHETICAL_CUES = _cue_pattern(
    "nếu", "giả sử", "có phải", "liệu", "có nguy hiểm", "có sao không", "là bệnh gì",
    "dấu hiệu của", "triệu chứng của", "thế nào là", "tư vấn giúp", "hỏi về", "phòng ngừa",
)
_HISTORICAL_CUES = _cue_pattern(
    "hôm qua", "hôm kia", "tuần trước", "tháng trước", "năm ngoái", "năm trước", "trước đây",
    "trước kia", "trước đó", "hồi nhỏ", "lúc nhỏ", "hồi bé", "tiền sử", "đã từng", "từng bị",
    "ngày xưa", "đã khỏi", "khỏi rồi", "đã hết", "hết rồi", "đỡ rồi",
)
_PRESENT_CUES = _cue_pattern(
    "đang", "hiện tại", "hiện giờ", "bây giờ", "lúc này", "ngay lúc này", "vừa xong", "vừa rồi",
    "nãy giờ", "hôm nay", "sáng nay", "chiều nay", "tối nay", "này", "liên tục", "vẫn",
)
_INTERROGATIVE_TAIL = re.compile(r"(?<![a-z0-9])(khong|ko)\s*\?*\s*$")
"""Đuôi nghi vấn "... không?" — người bệnh đang HỎI về dấu hiệu, không phải khai báo nó. Chỉ nhận
đúng dạng đuôi câu; dấu "?" đơn thuần KHÔNG tính, vì "bé đang co giật, phải làm sao?" là một ca cấp
cứu thật kèm câu hỏi."""


@dataclass(frozen=True, slots=True)
class TextSafetySignal:
    """Một tín hiệu ứng viên. KHÔNG phải kết luận lâm sàng, KHÔNG phải chẩn đoán."""

    code: str
    label: str
    phrase: str
    """Cụm từ trong danh mục đã khớp — bằng chứng để audit."""
    status: SignalStatus
    guard: str = GUARD_NONE
    evidence: str = ""
    """Mệnh đề chứa cụm khớp (dạng đã chuẩn hoá), để đọc log không phải dựng lại ngữ cảnh."""

    @property
    def reason_code(self) -> str:
        """Mã lý do khi tín hiệu này tạo escalation. Có tiền tố `TEXT_SIGNAL_` để không lẫn với
        `reason_codes` do `rule_engine` sinh từ field đã trích xuất — hai nguồn khác nhau, mức tin
        cậy khác nhau."""
        return f"TEXT_SIGNAL_{self.code.upper()}"


@dataclass(frozen=True, slots=True)
class TextSafetyScan:
    signals: tuple[TextSafetySignal, ...] = ()

    @property
    def short_circuit(self) -> tuple[TextSafetySignal, ...]:
        """Tín hiệu được phép dừng phiên NGAY bằng thông điệp tĩnh."""
        return tuple(
            signal for signal in self.signals
            if signal.status is SignalStatus.CONFIRMED_POSITIVE and signal.code in SHORT_CIRCUIT_CODES
        )

    @property
    def needs_confirmation(self) -> tuple[TextSafetySignal, ...]:
        """Tín hiệu phải được hỏi cho rõ trước khi đi tiếp — gồm cả dương tính rõ nhưng chưa duyệt."""
        return tuple(signal for signal in self.signals if signal.status is SignalStatus.NEEDS_CONFIRMATION)

    @property
    def suppressed(self) -> tuple[TextSafetySignal, ...]:
        return tuple(signal for signal in self.signals if signal.status is SignalStatus.SUPPRESSED)

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return tuple(signal.reason_code for signal in self.short_circuit)

    @property
    def short_circuit_labels(self) -> list[str]:
        """Nhãn của riêng tín hiệu đã escalate — dùng cho log, không gồm tín hiệu bị guard loại."""
        return [signal.label for signal in self.short_circuit]


_STATUS_RANK = {
    SignalStatus.CONFIRMED_POSITIVE: 2,
    SignalStatus.NEEDS_CONFIRMATION: 1,
    SignalStatus.SUPPRESSED: 0,
}


def scan_text_safety_signals(*texts: str) -> TextSafetyScan:
    """Quét text thô, trả tín hiệu ứng viên đã qua guard.

    Một mã khớp nhiều lần thì giữ lần có trạng thái MẠNH NHẤT ("hôm qua bé co giật, giờ vẫn đang co
    giật" ⇒ dương tính). Đây là hướng thiên về độ nhạy có chủ đích: bỏ sót một dấu hiệu đỏ đắt hơn
    một câu hỏi xác nhận thừa."""
    normalized = normalize_red_flag_text(" ".join(text for text in texts if text))
    if not normalized:
        return TextSafetyScan()

    strongest: dict[str, TextSafetySignal] = {}
    for text_rule in TEXT_RED_FLAG_RULES:
        for phrase in text_rule.phrases:
            needle = normalize_red_flag_text(phrase)
            if not needle:
                continue
            for match in re.finditer(re.escape(needle), normalized):
                status, guard = _classify(normalized, match.start(), match.end())
                if status is SignalStatus.CONFIRMED_POSITIVE and text_rule.code not in SHORT_CIRCUIT_CODES:
                    status, guard = SignalStatus.NEEDS_CONFIRMATION, GUARD_NOT_REVIEWED
                signal = TextSafetySignal(
                    code=text_rule.code, label=text_rule.label, phrase=phrase, status=status,
                    guard=guard, evidence=_segment(normalized, match.start(), match.end(), _SENTENCE_BOUNDARY),
                )
                current = strongest.get(text_rule.code)
                if current is None or _STATUS_RANK[signal.status] > _STATUS_RANK[current.status]:
                    strongest[text_rule.code] = signal

    ordered = tuple(strongest[code] for code in (r.code for r in TEXT_RED_FLAG_RULES) if code in strongest)
    return TextSafetyScan(signals=ordered)


def confirmation_question(codes: Sequence[str]) -> str:
    """Câu hỏi xác nhận TĨNH cho tín hiệu mơ hồ — không đi qua model.

    Đây là đường dự phòng khi model không trả về gì: người bệnh vừa nhắc tới một dấu hiệu nguy hiểm
    mà hệ thống không được phép im lặng bỏ qua. Câu hỏi chỉ NHẮC LẠI nhãn dấu hiệu, không suy diễn
    thêm chi tiết y khoa nào."""
    if not codes:
        return ""
    labels = ", ".join(dict.fromkeys(rule_label(code).lower() for code in codes[:3]))
    return (
        f"Trước khi hỏi tiếp, mình cần xác nhận một ý quan trọng: hiện tại có {labels} không? "
        "Nếu đang xảy ra ngay lúc này, bạn hãy gọi 115 hoặc đến cơ sở y tế gần nhất."
    )


def _classify(normalized: str, start: int, end: int) -> tuple[SignalStatus, str]:
    """Trạng thái của MỘT lần khớp. Thứ tự guard là thứ tự ưu tiên và không đổi được tuỳ tiện:
    phủ định là guard duy nhất được phép LOẠI tín hiệu, mọi guard còn lại chỉ hạ xuống mức xác nhận."""
    segment_start, segment_end = _bounds(normalized, start, end, _SEGMENT_BOUNDARY)
    sentence_start, sentence_end = _bounds(normalized, start, end, _SENTENCE_BOUNDARY)
    segment = normalized[segment_start:segment_end]
    sentence = normalized[sentence_start:sentence_end]
    prefix = _negation_prefix(normalized, start, segment_start)

    if _has_negation(prefix):
        return SignalStatus.SUPPRESSED, GUARD_NEGATED
    if _UNCERTAIN_CUES.search(prefix):
        return SignalStatus.NEEDS_CONFIRMATION, GUARD_UNCERTAIN
    if _OTHER_SUBJECT_CUES.search(sentence):
        return SignalStatus.NEEDS_CONFIRMATION, GUARD_OTHER_SUBJECT
    if _HYPOTHETICAL_CUES.search(sentence):
        return SignalStatus.NEEDS_CONFIRMATION, GUARD_HYPOTHETICAL
    tail = _INTERROGATIVE_TAIL.search(sentence)
    if tail is not None and sentence_start + tail.start() >= end:
        return SignalStatus.NEEDS_CONFIRMATION, GUARD_INTERROGATIVE
    if _HISTORICAL_CUES.search(sentence) and not _PRESENT_CUES.search(segment):
        return SignalStatus.NEEDS_CONFIRMATION, GUARD_HISTORICAL
    return SignalStatus.CONFIRMED_POSITIVE, GUARD_NONE


def _bounds(normalized: str, start: int, end: int, boundary: str) -> tuple[int, int]:
    """Vị trí đầu/cuối của mệnh đề (hoặc câu) chứa đoạn `[start, end)`."""
    left = max((normalized.rfind(char, 0, start) for char in boundary), default=-1)
    right_candidates = [pos for pos in (normalized.find(char, end) for char in boundary) if pos != -1]
    right = min(right_candidates) if right_candidates else len(normalized)
    return left + 1, right


def _segment(normalized: str, start: int, end: int, boundary: str) -> str:
    left, right = _bounds(normalized, start, end, boundary)
    return normalized[left:right].strip()


def _negation_prefix(normalized: str, start: int, segment_start: int) -> str:
    """Phần văn bản mà hạt phủ định phải nằm trong đó mới được tính: cùng mệnh đề, trong cửa sổ
    `_NEGATION_WINDOW`, và SAU liên từ đối lập gần nhất."""
    prefix = normalized[max(segment_start, start - _NEGATION_WINDOW):start]
    contrasts = list(_CONTRAST_CUES.finditer(prefix))
    return prefix[contrasts[-1].end():] if contrasts else prefix


def _has_negation(prefix: str) -> bool:
    """Có hạt phủ định THẬT trong prefix không.

    Một cue chỉ tính khi nó không mở đầu một cụm ngoại lệ: "không phải" là phủ định trọng tâm,
    "không biết/không rõ" là bất định — cả hai đều không phủ định vị ngữ đứng sau."""
    for match in _NEGATION_CUES.finditer(prefix):
        exception = _NEGATION_EXCEPTIONS.match(prefix, match.start())
        if exception is None:
            return True
    return False


def all_mentions_negated(text: str, keywords: Sequence[str]) -> bool:
    """Mọi lần `keywords` xuất hiện trong `text` đều nằm sau một hạt phủ định?

    Dành cho các chỗ khác cũng so khớp substring trên text thô - cụ thể là
    `intake_agent.scan_opportunistic_fields`, nơi "tôi không co giật" từng ghi thẳng
    `seizure_occurred=true` vào hồ sơ. Cùng một guard, một chỗ định nghĩa: nếu polarity được sửa ở
    đây thì mọi tầng so khớp thô cùng được sửa.

    Trả `False` khi không có lần xuất hiện nào - "không nhắc tới" khác "nhắc tới rồi phủ định", và
    caller chỉ gọi hàm này sau khi đã biết là có khớp."""
    normalized = normalize_red_flag_text(text)
    seen = False
    for keyword in keywords:
        needle = normalize_red_flag_text(keyword)
        if not needle:
            continue
        for match in re.finditer(re.escape(needle), normalized):
            seen = True
            segment_start, _ = _bounds(normalized, match.start(), match.end(), _SEGMENT_BOUNDARY)
            if not _has_negation(_negation_prefix(normalized, match.start(), segment_start)):
                return False
    return seen


def rule_label(code: str) -> str:
    """Nhãn tiếng Việt của một mã luật — cho log/phiếu bàn giao, tránh caller tự tra danh mục."""
    text_rule = _RULES_BY_CODE.get(code)
    return text_rule.label if text_rule is not None else code
