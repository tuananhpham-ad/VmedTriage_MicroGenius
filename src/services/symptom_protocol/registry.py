"""Đăng ký protocol + chọn protocol theo lời khai của người bệnh.

Đây là chỗ DUY NHẤT biết danh sách protocol tồn tại. `session.py`/`intake_agent.py` không được
import `fever_protocol`/`generic_protocol` trực tiếp - chúng chỉ làm việc với `SymptomProtocol` bất kỳ.

Vì sao cần lượt mở + chọn protocol: hội thoại bắt đầu bằng một câu tự do của người bệnh, lúc đó chưa
biết đây là ca sốt hay ca gì khác. Bắt đầu thẳng bằng protocol sốt tạo ra đúng cảnh đã gặp: người
nhắn "tôi đau ngực từ sáng, đi vài bước là hụt hơi" bị hỏi "bé hay người lớn, bao nhiêu tuổi" rồi đi
hết bộ câu hỏi về sốt.
"""

from __future__ import annotations

from dataclasses import replace

from src.services.engines.fever_protocol import FEVER_PROTOCOL
from src.services.engines.generic_protocol import GENERIC_PROTOCOL
from src.services.symptom_protocol.common_safety.predicates import as_float, is_true
from src.services.symptom_protocol.models import FieldSpec, QuestionCluster
from src.services.symptom_protocol.protocol import SymptomProtocol

PROTOCOL_REGISTRY: dict[str, SymptomProtocol] = {
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


def select_protocol(answers: dict[str, object], current: str | None = None) -> str:
    """Protocol nào nên chạy với hồ sơ hiện tại.

    Chỉ chuyển khi có căn cứ DƯƠNG TÍNH rõ ràng. Không có căn cứ thì GIỮ NGUYÊN protocol đang chạy -
    một hồ sơ chưa nhắc tới sốt không phải là bằng chứng "không sốt", và đổi protocol giữa chừng vì
    im lặng sẽ vứt bỏ cả nhánh câu hỏi đang dở."""
    if _has_fever_evidence(answers):
        return FEVER_PROTOCOL.name
    if current == FEVER_PROTOCOL.name and _fever_ruled_out(answers):
        # Người bệnh RÚT LẠI lời khai sốt ("à tôi nhầm, tôi không sốt"). Ở lại protocol sốt lúc này
        # nghĩa là tiếp tục hỏi nhiệt độ, thuốc hạ sốt, ngày khởi phát sốt cho một người vừa nói rõ
        # là không sốt. Đây là chiều đổi DUY NHẤT dựa trên phủ định, và nó cần một phủ định TƯỜNG
        # MINH ("false"/"none") chứ không phải im lặng.
        return DEFAULT_PROTOCOL_NAME
    if current in PROTOCOL_REGISTRY:
        return current
    return DEFAULT_PROTOCOL_NAME


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

OPENING_QUESTION = (
    "Bạn hoặc người nhà đang thấy khó chịu thế nào? Bạn cứ kể theo cách dễ nhất với mình nhé."
)
"""Câu mở TĨNH, không qua LLM. Một yêu cầu, một lượt - bản dài hơn (liệt kê sẵn các thứ cần khai) làm
người bệnh trả lời theo mẫu thay vì kể tự nhiên, mà kể tự nhiên mới là thứ lượt mở cần."""

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
    # bối cảnh nguy cơ hay được kể ngay ("tôi đang mang thai", "tôi bị tiểu đường")
    "chronic_conditions", "immunocompromised", "is_pregnant", "recent_surgery_30d",
)
"""~35 field. KHÔNG đưa cả registry vào: schema càng rộng thì model càng có xu hướng điền bừa cho đủ,
và đó chính là cơ chế của lỗi C1 (bịa "không" cho hàng loạt dấu hiệu chưa ai hỏi tới)."""


SWITCH_DETECTION_FIELDS: tuple[str, ...] = ("fever_reported", "fever_status", "temp_c")
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
    fields_by_key=_merged_fields(),
    clusters=(OPENING_CLUSTER,),
)
"""Protocol GIẢ chỉ dùng cho một lượt duy nhất: nó cho `intake_agent` đủ thứ cần để trích xuất
(`fields_by_key`) mà không phải biết trước sẽ đi protocol nào. Không bao giờ được gán vào
`session.protocol_name` - sau lượt mở, `select_protocol` chọn protocol THẬT."""
