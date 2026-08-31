"""Đăng ký protocol + chọn protocol theo lời khai của người bệnh.

Đây là chỗ DUY NHẤT biết danh sách protocol tồn tại. `session.py`/`intake_agent.py` không được
import `fever_protocol`/`generic_protocol` trực tiếp - chúng chỉ làm việc với `SymptomProtocol` bất kỳ.

Vì sao cần lượt mở + chọn protocol: hội thoại bắt đầu bằng một câu tự do của người bệnh, lúc đó chưa
biết đây là ca sốt hay ca gì khác. Bắt đầu thẳng bằng protocol sốt tạo ra đúng cảnh đã gặp: người
nhắn "tôi đau ngực từ sáng, đi vài bước là hụt hơi" bị hỏi "bé hay người lớn, bao nhiêu tuổi" rồi đi
hết bộ câu hỏi về sốt.
"""

from __future__ import annotations

import unicodedata
from dataclasses import replace
from hashlib import sha256

from src.services.engines.abdominal_protocol import ABDOMINAL_PROTOCOL
from src.services.engines.breathing_protocol import BREATHING_PROTOCOL
from src.services.engines.chest_pain_protocol import CHEST_PAIN_PROTOCOL
from src.services.engines.fever_protocol import FEVER_PROTOCOL
from src.services.engines.generic_protocol import GENERIC_PROTOCOL
from src.services.engines.headache_protocol import HEADACHE_PROTOCOL
from src.services.symptom_protocol.common_safety.predicates import as_float, is_true
from src.services.symptom_protocol.models import FieldSpec, QuestionCluster
from src.services.symptom_protocol.protocol import SymptomProtocol

PROTOCOL_REGISTRY: dict[str, SymptomProtocol] = {
    CHEST_PAIN_PROTOCOL.name: CHEST_PAIN_PROTOCOL,
    BREATHING_PROTOCOL.name: BREATHING_PROTOCOL,
    HEADACHE_PROTOCOL.name: HEADACHE_PROTOCOL,
    ABDOMINAL_PROTOCOL.name: ABDOMINAL_PROTOCOL,
    FEVER_PROTOCOL.name: FEVER_PROTOCOL,
    GENERIC_PROTOCOL.name: GENERIC_PROTOCOL,
}

DEFAULT_PROTOCOL_NAME = GENERIC_PROTOCOL.name
"""Than phiền chưa nhận diện được đi theo protocol generic - nó KHÔNG kết luận an toàn bao giờ, nên
chọn nhầm sang generic chỉ tốn thêm một lượt bàn giao, còn chọn nhầm sang một protocol chuyên biệt
là hỏi sai hướng suốt cả phiên."""


def protocol_for(name: str | None) -> SymptomProtocol:
    return PROTOCOL_REGISTRY.get(name or "", PROTOCOL_REGISTRY[DEFAULT_PROTOCOL_NAME])


# Ngưỡng "có sốt" theo KM §2 - dùng để NHẬN DIỆN protocol, không phải để kết luận lâm sàng.
_FEVER_TEMP_THRESHOLD_C = 38.0
PRIMARY_SYMPTOM_FIELD = FieldSpec(
    "primary_symptom_group", "Nhóm triệu chứng khó chịu nhất", "O",
    "Nhóm mà người bệnh kể là khó chịu NHẤT. Ghi khi lời khai đủ rõ để xếp nhóm, dù họ diễn đạt "
    "theo cách nào (\"đau tức vùng ngực trái\" -> chest_pain). Kể nhiều thứ thì chọn thứ họ nhấn "
    "mạnh nhất; không rõ thì để \"unknown\" - KHÔNG đoán theo triệu chứng phụ",
    tri_state=False,
    allowed_values=("chest_pain", "breathing", "headache", "abdominal", "fever", "unknown"),
)
"""Nhóm triệu chứng do MODEL gọi tên - đây là `symptom_group_router` của `INVARIANTS.md` §1 (L2).

Trước 2026-08-28 field này chỉ được cụm phân định `ROUTE-DISAMBIG` ghi, tức chỉ có giá trị khi phiên
đã đi được vài lượt - đúng lúc nó không còn cần thiết. Lượt mở, lượt DUY NHẤT quyết định phiên chạy
protocol nào, thì không có nó, nên việc chọn nhóm rơi hết vào `_complaint_text` khớp chuỗi thô.

`INVARIANTS.md` §5 cho phép gọi router model ở đúng 4 trigger, trigger thứ nhất là lượt mở. Điền field
này ở lượt mở KHÔNG tốn thêm lời gọi nào: nó đi kèm chính lời gọi `extract_turn` đã có, nên ngân sách
"2 lời gọi chính mỗi lượt" giữ nguyên."""


def select_protocol(answers: dict[str, object], current: str | None = None) -> str:
    """Protocol nào nên chạy với hồ sơ hiện tại.

    Chỉ chuyển khi có căn cứ DƯƠNG TÍNH rõ ràng. Không có căn cứ thì GIỮ NGUYÊN protocol đang chạy -
    một hồ sơ chưa nhắc tới sốt không phải là bằng chứng "không sốt", và đổi protocol giữa chừng vì
    im lặng sẽ vứt bỏ cả nhánh câu hỏi đang dở."""
    candidates = protocol_candidates(answers)
    if candidates:
        preferred = answers.get(PRIMARY_SYMPTOM_FIELD.key)
        if isinstance(preferred, str) and preferred in candidates:
            return preferred
        return candidates[0]
    if current in PROTOCOL_REGISTRY and not _protocol_ruled_out(current, answers):
        return current
    return DEFAULT_PROTOCOL_NAME


PROTOCOL_PRIORITY: tuple[str, ...] = (
    CHEST_PAIN_PROTOCOL.name,
    BREATHING_PROTOCOL.name,
    HEADACHE_PROTOCOL.name,
    ABDOMINAL_PROTOCOL.name,
    FEVER_PROTOCOL.name,
)


def protocol_candidates(answers: dict[str, object]) -> tuple[str, ...]:
    """Mọi nhóm có căn cứ dương tính, xếp theo ưu tiên lâm sàng F09 §3.8."""
    evidence = {
        CHEST_PAIN_PROTOCOL.name: _has_chest_pain_evidence(answers),
        BREATHING_PROTOCOL.name: _has_breathing_evidence(answers),
        HEADACHE_PROTOCOL.name: _has_headache_evidence(answers),
        ABDOMINAL_PROTOCOL.name: _has_abdominal_evidence(answers),
        FEVER_PROTOCOL.name: _has_fever_evidence(answers),
    }
    return tuple(name for name in PROTOCOL_PRIORITY if evidence[name])


def _fold_text(value: object) -> str:
    text = str(value or "").casefold().replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def _complaint_text(answers: dict[str, object]) -> str:
    return " ".join(_fold_text(answers.get(key)) for key in ("chief_complaint", "complaint_site"))


_PAIN_WORDS: tuple[str, ...] = (
    "dau", "tuc", "nang", "nhoi", "that", "de ep", "bop nghet", "kho chiu", "rat", "quan",
)
"""Từ chỉ CẢM GIÁC khó chịu. Ghép với một từ chỉ VỊ TRÍ mới thành bằng chứng.

Ghép hai chiều thay vì liệt kê từng cụm hoàn chỉnh: bản cũ khớp đúng 3 chuỗi (`"dau nguc"`,
`"tuc nguc"`, `"nang nguc"`) nên `"đau tức vùng ngực trái"` trượt sạch - không cụm nào trong ba cụm đó
là chuỗi con của nó. Người bệnh không nói theo từ điển; có vô số cách chen chữ vào giữa ("đau ở giữa
ngực", "tức phía sau lồng ngực", "nhói bên ngực trái")."""


def _mentions(text: str, sites: tuple[str, ...]) -> bool:
    """Lời khai có nhắc tới một VỊ TRÍ kèm một cảm giác khó chịu không."""
    return any(site in text for site in sites) and any(word in text for word in _PAIN_WORDS)


def _stated_group(answers: dict[str, object], name: str) -> bool:
    """Model đã gọi ĐÍCH DANH nhóm này ở `primary_symptom_group` chưa.

    Đây là căn cứ MẠNH NHẤT trong ba loại: nó đến từ model đọc nguyên tin nhắn tự do, thay vì từ một
    bảng chuỗi con viết tay không bao giờ đuổi kịp cách người ta nói. Nhưng nó vẫn thua một lời PHỦ
    ĐỊNH tường minh - `_protocol_ruled_out` đứng chặn ở đây, để "tôi không đau ngực" ở lượt sau không
    bị một nhãn model gán từ lượt trước ghi đè."""
    return answers.get(PRIMARY_SYMPTOM_FIELD.key) == name and not _protocol_ruled_out(name, answers)


_CHEST_SITES: tuple[str, ...] = ("nguc", "long nguc", "xuong uc", "vung tim")
_BREATHING_MARKERS: tuple[str, ...] = (
    "kho tho", "hut hoi", "nghet tho", "nghen tho", "tuc tho", "tho gap", "tho nhanh",
    "thieu khong khi", "khong tho duoc", "tho khong ra hoi", "len con hen", "kho ho hap",
)
_HEADACHE_MARKERS: tuple[str, ...] = (
    "dau dau", "nhuc dau", "dau nua dau", "dau nua ben dau", "dau nua so", "buot dau",
    "dau o dau", "dau vung tran", "dau vung gay", "dau dinh dau", "dau thai duong", "migraine",
    "nang dau", "choang dau",
)
_ABDOMEN_SITES: tuple[str, ...] = (
    "bung", "da day", "thuong vi", "ha suon", "ho chau", "quanh ron", "vung ron", "ruot",
)
"""Từ vựng dự phòng khi model chết hoặc trả `unknown` cho `primary_symptom_group`.

Đây là LƯỚI ĐỠ, không phải cơ chế chính - `_stated_group` mới là cơ chế chính. Giữ chúng vì
`INVARIANTS.md` §5 đòi "tắt hoàn toàn SLM thì hệ thống vẫn phải chạy đúng": router rơi về rule."""


def _has_chest_pain_evidence(answers: dict[str, object]) -> bool:
    if _stated_group(answers, CHEST_PAIN_PROTOCOL.name):
        return True
    if is_true(answers.get("chest_pain")):
        return True
    if any(answers.get(key) not in (None, "", "unknown", "none", "false") for key in (
        "chest_pain_character", "chest_pain_radiation", "chest_pain_duration_min",
    )):
        return True
    return _mentions(_complaint_text(answers), _CHEST_SITES)


def _has_breathing_evidence(answers: dict[str, object]) -> bool:
    if _stated_group(answers, BREATHING_PROTOCOL.name):
        return True
    if answers.get("breathing_difficulty") in {"mild", "severe"}:
        return True
    if is_true(answers.get("dyspnea_at_rest")) or answers.get("dyspnea_onset_mode") in {"sudden", "gradual"}:
        return True
    text = _complaint_text(answers)
    return any(marker in text for marker in _BREATHING_MARKERS)


def _has_headache_evidence(answers: dict[str, object]) -> bool:
    if _stated_group(answers, HEADACHE_PROTOCOL.name):
        return True
    if is_true(answers.get("severe_headache")) or is_true(answers.get("thunderclap_onset")):
        return True
    if any(answers.get(key) not in (None, "", "unknown", "false") for key in (
        "headache_severity", "headache_progressive", "headache_different_from_usual",
    )):
        return True
    text = _complaint_text(answers)
    return any(marker in text for marker in _HEADACHE_MARKERS)


def _has_abdominal_evidence(answers: dict[str, object]) -> bool:
    if _stated_group(answers, ABDOMINAL_PROTOCOL.name):
        return True
    if answers.get("abdominal_pain_severity") in {"mild", "moderate", "severe"}:
        return True
    if any(answers.get(key) not in (None, "", "unknown", "none", "false") for key in (
        "abdominal_pain_location", "abdominal_pain_onset_mode", "abdominal_pain_duration_hours",
    )):
        return True
    return _mentions(_complaint_text(answers), _ABDOMEN_SITES)


def _protocol_ruled_out(name: str, answers: dict[str, object]) -> bool:
    if name == FEVER_PROTOCOL.name:
        return _fever_ruled_out(answers)
    if name == CHEST_PAIN_PROTOCOL.name:
        return answers.get("chest_pain") == "false"
    if name == BREATHING_PROTOCOL.name:
        return answers.get("breathing_difficulty") == "none"
    if name == HEADACHE_PROTOCOL.name:
        return answers.get("severe_headache") == "false" and answers.get("headache_severity") in (None, "unknown")
    if name == ABDOMINAL_PROTOCOL.name:
        return answers.get("abdominal_pain_severity") == "none"
    return False


def _has_fever_evidence(answers: dict[str, object]) -> bool:
    if _stated_group(answers, FEVER_PROTOCOL.name):
        return True
    if is_true(answers.get("fever_reported")):
        return True
    if answers.get("fever_status") in ("objective", "subjective"):
        return True
    temp = as_float(answers.get("temp_c"))
    return temp is not None and temp >= _FEVER_TEMP_THRESHOLD_C


def _fever_ruled_out(answers: dict[str, object]) -> bool:
    return answers.get("fever_reported") == "false" or answers.get("fever_status") == "none"


# --- Lượt mở --------------------------------------------------------------------------------------

OPENING_QUESTIONS: tuple[str, ...] = (
    "Bạn hoặc người nhà đang thấy khó chịu thế nào? Bạn cứ kể theo cách dễ nhất với mình nhé.",
    "Mình nghe đây ạ. Bạn hoặc người nhà đang gặp chuyện gì trong người thế?",
    "Bạn kể cho mình nghe đang thấy trong người thế nào nhé - cứ nói theo cách của bạn thôi ạ.",
    "Chào bạn. Hôm nay bạn hoặc người nhà đang thấy khó chịu ở đâu ạ?",
    "Bạn đang thấy trong người có gì không ổn ạ? Bạn cứ kể thoải mái, mình nghe.",
    "Mình có thể giúp gì cho bạn hôm nay? Bạn kể mình nghe đang khó chịu thế nào nhé.",
    "Chào bạn, mình ở đây rồi. Trong người bạn hoặc người nhà đang có gì bất thường ạ?",
    "Bạn đang gặp chuyện gì trong người vậy ạ? Kể mình nghe từ đầu cũng được, không cần vội.",
    "Mình sẵn sàng nghe rồi ạ. Bạn hoặc người nhà đang thấy khó chịu chỗ nào?",
    "Hôm nay có chuyện gì trong người khiến bạn phải nhắn cho mình vậy ạ? Bạn cứ kể tự nhiên nhé.",
)
"""Các bản của câu mở. TĨNH, không qua LLM - nhưng KHÔNG chỉ một bản.

Cả mười bản nói đúng một việc: mời người bệnh kể tự do, một yêu cầu, một lượt. Bản dài hơn (liệt kê
sẵn các thứ cần khai) làm người bệnh trả lời theo mẫu thay vì kể tự nhiên, mà kể tự nhiên mới là thứ
lượt mở cần - nên các bản chỉ khác NHỊP và cách xưng hô, không khác nội dung.

**Vì sao phải có nhiều bản.** Trước đây đây là một hằng số duy nhất, nên mọi phiên của mọi người dùng
mở đầu bằng đúng một chuỗi ký tự - và người dùng quay lại lần thứ hai nhận ra ngay mình đang nói
chuyện với một cái máy trả lời tự động. Đắt hơn thế: lượt chào-thuần (`session.py`) cũng phát lại
đúng câu ấy, nên người bệnh chào xong đọc lại y nguyên câu vừa đọc.

Vẫn TĨNH chứ không nhờ LLM viết: đây là câu đầu tiên người bệnh đọc, nó phải đọc được cả khi provider
chết, và nó không được phép trôi ra ngoài phạm vi "mời kể" qua một lần diễn đạt lại."""

OPENING_QUESTION = OPENING_QUESTIONS[0]
"""Bản mặc định - dùng cho `OPENING_CLUSTER.script_hint` (nội dung cụm phải tất định) và làm đường
lui khi không có seed nào."""


def opening_question(seed: object = "", *, avoid: str = "") -> str:
    """Một bản câu mở, chọn TẤT ĐỊNH theo `seed`.

    Tất định theo seed chứ không `random`: cùng một `session_id` luôn cho cùng một câu, nên log đọc
    lại được và test không phải mock bộ sinh ngẫu nhiên. Người dùng vẫn thấy khác nhau vì seed thật
    là `session_id`, mỗi phiên một khác.

    `avoid` là câu VỪA phát ra ở lượt trước - truyền vào thì hàm không bao giờ trả lại đúng nó. Đây
    là chỗ dùng ở lượt chào-thuần: người bệnh chào, và câu đáp không được là bản sao của câu họ vừa
    đọc."""
    pool = tuple(q for q in OPENING_QUESTIONS if q != avoid.strip()) or OPENING_QUESTIONS
    key = str(seed)
    if not key:
        return pool[0]
    return pool[sha256(key.encode("utf-8")).digest()[0] % len(pool)]

OPENING_HARVEST_EXTRA_FIELDS: tuple[str, ...] = (
    "reporter_type",
    # Dấu hiệu đỏ tier C: kể co giật/ban ngay câu đầu là phải chốt đỏ ngay câu đầu, không đợi tới
    # stage quét.
    "seizure_active_now", "rash_present", "rash_type", "chest_pain", "is_pregnant",
    # Triệu chứng hay được kể thành danh sách ngay lượt mở.
    "nausea_present", "myalgia_retroorbital_pain", "abdominal_pain_location",
    # Lưới hứng cho thứ không field nào đỡ. Lượt mở là lượt CẦN nó nhất: người bệnh kể tự do, chưa
    # ai định hướng, nên đây là lượt sinh ra nhiều dữ kiện ngoài schema nhất.
    "other_conditions",
    # Router nhóm triệu chứng. Lượt mở là lượt DUY NHẤT quyết định phiên chạy protocol nào, nên nó
    # cũng là lượt bắt buộc phải có field này - xem docstring `PRIMARY_SYMPTOM_FIELD`.
    PRIMARY_SYMPTOM_FIELD.key,
)
"""Field tier C/O/H được nhặt thêm ở lượt mở, NGOÀI bộ M0/M1 tự động bên dưới.

Đây là danh sách chép tay, và nó phải ngắn: đó là ngoại lệ, không phải quy tắc. Mọi field mà tài liệu
lâm sàng đã đánh M0/M1 vào thẳng schema qua `_tiered_harvest_fields()`."""


def _tiered_harvest_fields() -> tuple[str, ...]:
    """Mọi field M0/M1 của MỌI protocol đã đăng ký.

    **Đây là cơ chế chống bắt trượt, và nó thay cho một danh sách chép tay.** Bản cũ liệt kê tay ~50
    key, nên thêm một field mới vào checklist KHÔNG tự đưa nó vào schema lượt mở - người bệnh kể chi
    tiết đó ngay tin nhắn đầu thì không có ô nào để ghi, dữ kiện rơi im lặng, và tới lúc hội thoại đi
    đến đúng cụm đó thì agent hỏi lại nguyên văn thứ họ vừa nói. Bug đau ngực 2026-08-28 là đúng cơ
    chế này: `chest_pain_character`/`_radiation`/`_duration_min` đều là M0 nhưng không ai chép chúng
    vào đây, nên ca "đau ngực đè ép lan tay trái 20 phút" chỉ còn lại một chữ "đau ngực".

    Lấy theo TIER chứ không theo tên nhóm: tier là thứ tài liệu lâm sàng đã chấm ("M0 = không có thì
    không phân loại được"), nên field nào đáng hỏi thì cũng đúng là field đáng nhặt khi người bệnh
    tự khai. Ai thêm field M0/M1 mới không phải nhớ sửa file này.

    CÁI GIÁ: schema lượt mở rộng hơn (~86 field) nên prompt dài hơn. Đánh đổi giống hệt
    `SAFETY_LOOKAHEAD_CLUSTERS = 0`: đổi token lấy việc không đánh rơi lời người bệnh. Rủi ro model
    "điền bừa cho đủ" (lỗi C1) KHÔNG tăng theo độ rộng schema, vì lượt mở chạy `evidence="unasked"` -
    mọi giá trị xác định đều phải trích được nguyên văn lời người bệnh mới được ghi."""
    return tuple(
        key for key, spec in _merged_fields().items() if spec.tier in _HARVEST_TIERS
    )


_HARVEST_TIERS = frozenset({"M0", "M1"})


def _opening_harvest_fields() -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for key in _tiered_harvest_fields() + OPENING_HARVEST_EXTRA_FIELDS:
        seen.setdefault(key, None)
    return tuple(seen)


SWITCH_DETECTION_FIELDS: tuple[str, ...] = (
    "chest_pain", "chest_pain_character", "chest_pain_radiation", "chest_pain_duration_min",
    "breathing_difficulty", "dyspnea_onset_mode", "dyspnea_at_rest", "functional_impact", "leg_swelling",
    "severe_headache", "thunderclap_onset", "headache_severity", "headache_different_from_usual",
    "headache_progressive", "abdominal_pain_severity", "abdominal_pain_location",
    "abdominal_pain_onset_mode", "abdominal_pain_duration_hours", "fever_reported", "fever_status", "temp_c",
)
"""Field đủ để NHẬN RA phiên nên đổi sang protocol khác (xem `select_protocol`).

Vì sao cần khai riêng: field của protocol nào chỉ nằm trong registry của protocol đó. Một phiên đang
chạy `general` không có `temp_c` trong schema, nên câu "bé sốt 39.2 độ" ở lượt thứ ba KHÔNG có chỗ
nào để ghi - và `select_protocol` không bao giờ thấy bằng chứng sốt. Đo được khi chạy LLM thật: phiên
kẹt ở `general` suốt dù người bệnh khai nhiệt độ rõ ràng.

KHÔNG dùng quét từ khoá thay cho việc này: từ "sốt" có trong cả "không bị **sốt** xuất huyết" (tên
bệnh), và `scan_opportunistic_fields` chỉ biết gán `"true"` - đúng bằng cách tái tạo lại bug C2."""


def with_switch_detection(protocol: SymptomProtocol) -> SymptomProtocol:
    """Bản mở rộng của `protocol` có thêm field nhận diện protocol khác trong schema trích xuất.

    CHỈ dùng cho lượt trích xuất, KHÔNG lưu vào `session.protocol_name` và không đi vào phiếu bàn
    giao: `symptom_case_bridge` resolve protocol từ registry nên JSON gửi bên triage vẫn đúng bộ field
    của protocol thật."""
    extra = {key: spec for key, spec in _merged_fields().items() if key in SWITCH_DETECTION_FIELDS}
    extra[PRIMARY_SYMPTOM_FIELD.key] = PRIMARY_SYMPTOM_FIELD
    missing = {key: spec for key, spec in extra.items() if key not in protocol.fields_by_key}
    if not missing:
        return protocol
    return replace(
        protocol,
        fields_by_key={**protocol.fields_by_key, **missing},
        safety_signal_fields=protocol.safety_signal_fields + tuple(missing),
    )


def _merged_fields() -> dict[str, FieldSpec]:
    """Field spec gộp của MỌI protocol - lượt mở chưa biết sẽ đi protocol nào nên phải hiểu được cả
    từ vựng của cả hai. Trùng key thì bản của protocol đăng ký trước thắng; hiện các key trùng đều
    đến từ `common_safety` nên là CÙNG một object."""
    merged: dict[str, FieldSpec] = {}
    for protocol in PROTOCOL_REGISTRY.values():
        for key, spec in protocol.fields_by_key.items():
            merged.setdefault(key, spec)
    return merged


OPENING_HARVEST_FIELDS: tuple[str, ...] = _opening_harvest_fields()
"""Schema trích xuất của lượt mở: toàn bộ field M0/M1 + vài field tier C/O hay được kể sớm.

Dựng bằng CODE chứ không chép tay - xem `_tiered_harvest_fields()` cho lý do."""


OPENING_CLUSTER = QuestionCluster(
    "OPEN", "", tuple(OPENING_HARVEST_FIELDS), batch_negation=False, script_hint=OPENING_QUESTION,
)
"""`batch_negation=False` là BẮT BUỘC ở lượt mở: người bệnh chưa được hỏi gì cả, nên không có "cụm"
nào để một câu phủ định gộp áp vào. Cho phép ở đây tức là mở lại đúng lỗ hổng C1 ở quy mô lớn nhất."""

OPENING_PROTOCOL: SymptomProtocol = replace(
    GENERIC_PROTOCOL,
    name="opening",
    fields_by_key={**_merged_fields(), PRIMARY_SYMPTOM_FIELD.key: PRIMARY_SYMPTOM_FIELD},
    clusters=(OPENING_CLUSTER,),
)
"""Protocol GIẢ chỉ dùng cho một lượt duy nhất: nó cho `intake_agent` đủ thứ cần để trích xuất
(`fields_by_key`) mà không phải biết trước sẽ đi protocol nào. Không bao giờ được gán vào
`session.protocol_name` - sau lượt mở, `select_protocol` chọn protocol THẬT."""
