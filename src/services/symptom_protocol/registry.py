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
    "Chỉ ghi khi người bệnh chọn rõ một nhóm sau câu hỏi phân định",
    tri_state=False,
    allowed_values=("chest_pain", "breathing", "headache", "abdominal", "fever", "unknown"),
)


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


def _has_chest_pain_evidence(answers: dict[str, object]) -> bool:
    if is_true(answers.get("chest_pain")):
        return True
    if any(answers.get(key) not in (None, "", "unknown", "none", "false") for key in (
        "chest_pain_character", "chest_pain_radiation", "chest_pain_duration_min",
    )):
        return True
    text = _complaint_text(answers)
    return "dau nguc" in text or "tuc nguc" in text or "nang nguc" in text


def _has_breathing_evidence(answers: dict[str, object]) -> bool:
    if answers.get("breathing_difficulty") in {"mild", "severe"}:
        return True
    if is_true(answers.get("dyspnea_at_rest")) or answers.get("dyspnea_onset_mode") in {"sudden", "gradual"}:
        return True
    text = _complaint_text(answers)
    return any(marker in text for marker in ("kho tho", "hut hoi", "nghet tho"))


def _has_headache_evidence(answers: dict[str, object]) -> bool:
    if is_true(answers.get("severe_headache")) or is_true(answers.get("thunderclap_onset")):
        return True
    if any(answers.get(key) not in (None, "", "unknown", "false") for key in (
        "headache_severity", "headache_progressive", "headache_different_from_usual",
    )):
        return True
    return "dau dau" in _complaint_text(answers)


def _has_abdominal_evidence(answers: dict[str, object]) -> bool:
    if answers.get("abdominal_pain_severity") in {"mild", "moderate", "severe"}:
        return True
    if any(answers.get(key) not in (None, "", "unknown", "none", "false") for key in (
        "abdominal_pain_location", "abdominal_pain_onset_mode", "abdominal_pain_duration_hours",
    )):
        return True
    text = _complaint_text(answers)
    return "dau bung" in text or "dau da day" in text


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
)
"""Các bản của câu mở. TĨNH, không qua LLM - nhưng KHÔNG chỉ một bản.

Cả sáu bản nói đúng một việc: mời người bệnh kể tự do, một yêu cầu, một lượt. Bản dài hơn (liệt kê
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

OPENING_HARVEST_FIELDS: tuple[str, ...] = (
    # nhận diện đối tượng
    "age_value", "age_unit", "sex", "reporter_type",
    # than phiền (generic) + lõi sốt (để chọn được protocol ngay sau lượt này)
    "chief_complaint", "complaint_site", "complaint_onset_at", "complaint_severity",
    "fever_reported", "fever_status", "temp_c", "temp_site", "fever_onset_at",
    # dấu hiệu đỏ phổ quát - kể co giật/tím tái ngay câu đầu là phải chốt đỏ ngay câu đầu
    "consciousness_level", "seizure_occurred", "seizure_active_now", "neck_stiffness",
    "focal_neuro_deficit", "breathing_difficulty", "cyanosis", "stridor_or_drooling",
    "cold_clammy_skin", "capillary_refill_ge_3s", "non_blanching_rash", "mucosal_bleeding",
    "gi_bleeding", "urine_output", "feeding_intake", "vomiting_severity",
    "abdominal_pain_severity", "chest_pain",
    "thunderclap_onset", "headache_severity", "headache_different_from_usual",
    "headache_progressive", "abdominal_pain_onset_mode", "abdominal_pain_duration_hours",
    "dyspnea_onset_mode", "dyspnea_at_rest", "functional_impact", "leg_swelling",
    # triệu chứng hay được kể thành danh sách ngay lượt mở; thiếu chúng khỏi schema sẽ làm rơi dữ kiện
    "severe_headache", "nausea_present", "rash_present", "rash_type",
    "myalgia_retroorbital_pain",
    # bối cảnh nguy cơ hay được kể ngay ("tôi đang mang thai", "tôi bị tiểu đường")
    "chronic_conditions", "immunocompromised", "is_pregnant", "recent_surgery_30d",
)
"""~35 field. KHÔNG đưa cả registry vào: schema càng rộng thì model càng có xu hướng điền bừa cho đủ,
và đó chính là cơ chế của lỗi C1 (bịa "không" cho hàng loạt dấu hiệu chưa ai hỏi tới)."""


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
