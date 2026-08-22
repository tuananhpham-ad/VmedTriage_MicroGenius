"""Field registry + question clusters cho agent fever, theo đúng
`docs/medical_knowledge/fever-knowledge-model.md` (KM) Part 3 và
`docs/medical_knowledge/fever-conversation-specification.md` (CS) Part 3.

KHÔNG tự đặt tên field/mã cụm khác đi — mọi `key` chép nguyên văn cột "Field name" của KM §3.2-3.11
(loại các field metadata/derived ở §3.12: `session_id`, `triage_level`, `data_gap`... vì đó là output
của rule engine, không phải câu hỏi hội thoại). Mọi `QuestionCluster.id` chép nguyên văn mã câu hỏi
(`Q0-01`...`Q5-07`) trong CS Part 3, đúng thứ tự xuất hiện trong tài liệu.

`tri_state`: KM §3.1 điểm 1 quy định tri-state (`true|false|unknown`) áp dụng cho field có kiểu dữ
liệu "tri-state"/"boolean" trong cột Data type — KHÔNG áp dụng cho field enum/number/date/array dù
tier là M0/M1 (vd `consciousness_level` là M0 nhưng là enum, không phải tri-state). `tri_state=True`
được gán đúng theo cột Data type của KM, không suy theo tier.

`allowed_values`: chép nguyên văn `enum` trong JSON Schema KM §7 (nguồn chuẩn duy nhất - bảng §3.x có
chỗ ghi rút gọn kèm "..."). Chỉ điền cho field enum VÔ HƯỚNG; field `array[enum]` (`dehydration_signs`,
`seizure_features`, `chronic_conditions`, `immunocompromise_cause`, `indwelling_device`,
`outbreak_exposure`, `animal_water_exposure`, `obstetric_red_flags`) để rỗng vì `_coerce_enum` lọc theo
giá trị đơn, chưa lọc theo từng phần tử mảng - lọc nửa vời sẽ xoá cả mảng hợp lệ. Field số/ngày/mô tả
tự do (`age_value`, `temp_c`, `caregiver_concern_level`, `current_medications`...) đương nhiên để rỗng.

`FeverField`/`QuestionCluster` là alias của kiểu generic ở `symptom_protocol.models` (engine dùng
chung cho mọi symptom_group, xem `_guidance/fever-detect-agent-task.md` mục "kế thừa được") - file
này chỉ còn là DATA (field/cụm cụ thể của fever), không định nghĩa kiểu riêng nữa.
"""

from __future__ import annotations

from typing import Literal

from src.services.symptom_protocol.common_safety import clusters as common_clusters
from src.services.symptom_protocol.common_safety import fields as common_fields
from src.services.symptom_protocol.models import FieldSpec as FeverField
from src.services.symptom_protocol.models import QuestionCluster

Tier = Literal["M0", "M1", "C", "O", "H"]
Stage = Literal["0", "1", "2", "3A", "3B", "4", "5"]


# ---------------------------------------------------------------------------------------------
# KM §3.2 — Nhóm PATIENT
#
# Nhân khẩu + safety-netting lấy từ `common_safety/fields.py`: chúng không phải kiến thức về SỐT
# ("bao nhiêu tuổi", "sống một mình") nên mọi protocol dùng chung một định nghĩa. Ở lại đây chỉ
# `weight_kg` vì lý do tồn tại của nó trong protocol này là cảnh báo quá liều paracetamol.
# ---------------------------------------------------------------------------------------------
_PATIENT_FIELDS: tuple[FeverField, ...] = (
    common_fields.DEMOGRAPHIC_FIELDS
    + (FeverField("weight_kg", "Cân nặng (kg)", "O", "Chỉ dùng cảnh báo quá liều paracetamol", tri_state=False),)
    + common_fields.SAFETY_NETTING_FIELDS
)

# ---------------------------------------------------------------------------------------------
# KM §3.3 — Nhóm FEVER
# ---------------------------------------------------------------------------------------------
_FEVER_FIELDS: tuple[FeverField, ...] = (
    FeverField("fever_reported", "Người dùng khai có sốt", "M0", "Cổng vào toàn bộ protocol sốt"),
    FeverField("fever_status", "Loại sốt", "M0", "objective/subjective/none - điều hướng nhánh dữ liệu thiếu", tri_state=False, allowed_values=("objective", "subjective", "none",)),
    FeverField("temp_c", "Nhiệt độ đo được (°C)", "M0", "Đầu vào rule ngưỡng theo tuổi; M0 khi fever_status=objective", tri_state=False),
    FeverField("temp_site", "Vị trí đo", "M0", "axillary/oral/rectal/tympanic/temporal - quyết định ngưỡng áp dụng", tri_state=False, allowed_values=("axillary", "oral", "rectal", "tympanic", "temporal", "unknown",)),
    FeverField("temp_measured_at", "Thời điểm đo", "C", "Số đo cũ -> độ tin cậy thấp hơn", tri_state=False),
    FeverField("temp_device_type", "Loại nhiệt kế", "O", "Gán measurement_confidence", tri_state=False, allowed_values=("digital", "infrared_ear", "infrared_forehead", "mercury_glass", "chemical_dot", "unknown",)),
    FeverField("temp_max_24h_c", "Nhiệt độ cao nhất 24h qua (°C)", "O", "Bắt đỉnh sốt bị thuốc che", tri_state=False),
    FeverField("fever_onset_at", "Thời điểm bắt đầu sốt", "M0", "Tính fever_duration_days - mốc 5/7 ngày", tri_state=False),
    FeverField("fever_pattern", "Kiểu sốt", "O", "continuous/intermittent/relapsing - giá trị hạn chế", tri_state=False, allowed_values=("continuous", "intermittent", "relapsing", "unknown",)),
    FeverField("rigors", "Rét run dữ dội", "M0", "Amber NICE; gợi ý nhiễm khuẩn huyết/sốt rét"),
    FeverField("hypothermia_reported", "Nhiệt độ < 36°C", "C", "Red flag ở nhóm nguy cơ, kích hoạt theo tuổi/miễn dịch"),
    FeverField("antipyretic_taken", "Đã dùng thuốc hạ sốt", "M0", "Nhiệt độ hiện tại có thể bị che"),
    FeverField("antipyretic_drug", "Tên hoạt chất hạ sốt", "C", "Sàng lọc NSAID trong bối cảnh SXHD", tri_state=False, allowed_values=("paracetamol", "ibuprofen", "aspirin", "other", "unknown",)),
    FeverField("antipyretic_total_24h_mg", "Tổng liều 24h (mg)", "O", "Cảnh báo quá liều paracetamol", tri_state=False),
    FeverField("antipyretic_response", "Đáp ứng sau khi uống thuốc", "O", "Không dùng để loại trừ bệnh nặng", tri_state=False, allowed_values=("resolved", "partial", "none", "unknown",)),
    FeverField("worse_after_defervescence", "Mệt/khó chịu hơn dù đã hạ sốt", "M0", "Dấu hiệu khám lại ngay theo QĐ 2760 (RF-29)"),
)

# ---------------------------------------------------------------------------------------------
# KM §3.4-§3.8 — GENERAL / RESPIRATORY / CIRCULATION / NEUROLOGICAL / SKIN & BLEEDING
#
# Toàn bộ 5 nhóm này là dấu hiệu "người bệnh đang nguy kịch", không phải kiến thức về sốt: tím tái,
# co giật, sốc, ban không mất khi ấn kính đúng y như vậy với mọi than phiền. Định nghĩa nằm ở
# `common_safety/fields.py` để protocol thứ hai KHÔNG phải import từ fever (sai chiều phụ thuộc) và
# cũng không phải chép lại (hai bản sao sẽ lệch nhau).
# ---------------------------------------------------------------------------------------------
_GENERAL_FIELDS = common_fields.GENERAL_FIELDS
_RESPIRATORY_FIELDS = common_fields.RESPIRATORY_FIELDS
_CIRCULATION_FIELDS = common_fields.CIRCULATION_FIELDS
_NEUROLOGICAL_FIELDS = common_fields.NEUROLOGICAL_FIELDS
_SKIN_FIELDS = common_fields.SKIN_BLEEDING_FIELDS

# ---------------------------------------------------------------------------------------------
# KM §3.9 — Nhóm ASSOCIATED SYMPTOMS
#
# Phần dùng chung + 4 field riêng của fever: 3 field "ổ nhiễm khuẩn lành tính" (đau họng/đau tai/ho)
# chỉ có nghĩa khi đang tìm NGUỒN của cơn sốt, và bộ đau cơ/đau hốc mắt là chỉ điểm bệnh virus lưu
# hành - cả hai đều là suy luận về sốt, không phải dấu hiệu nguy kịch phổ quát.
# ---------------------------------------------------------------------------------------------
_ASSOCIATED_FIELDS: tuple[FeverField, ...] = common_fields.ASSOCIATED_FIELDS + (
    FeverField("sore_throat", "Đau họng", "O", "Định hướng ổ nhiễm khuẩn lành tính hơn"),
    FeverField("ear_pain", "Đau tai", "O", "Định hướng ổ nhiễm khuẩn lành tính hơn"),
    FeverField("cough", "Ho", "O", "Định hướng ổ nhiễm khuẩn lành tính hơn"),
    FeverField("myalgia_retroorbital_pain", "Đau cơ, đau hốc mắt", "O", "Bộ triệu chứng gợi ý bệnh virus lưu hành VN"),
)

# ---------------------------------------------------------------------------------------------
# KM §3.10 — Nhóm RISK
#
# Phần dùng chung (bệnh nền, suy giảm miễn dịch, thai sản, phẫu thuật/thiết bị lưu) + phần DỊCH TỄ
# của riêng fever: sốt rét, SXHD, ổ dịch, tiêm chủng - đây là suy luận về NGUYÊN NHÂN gây sốt.
# ---------------------------------------------------------------------------------------------
_RISK_FIELDS: tuple[FeverField, ...] = common_fields.RISK_CONTEXT_FIELDS + (
    FeverField("travel_history_12m", "Du lịch gần đây", "C", "Vùng sốt rét lưu hành = nguy cơ cao (RF-35)", tri_state=False),
    FeverField("malaria_risk_area", "Vùng đến có sốt rét lưu hành", "C", "Cấp cứu tiềm tàng (RF-35)"),
    FeverField("outbreak_exposure", "Ổ dịch quanh khu vực/gia đình", "H", "Thay đổi xác suất nền", tri_state=False),
    FeverField("mosquito_exposure", "Bị muỗi đốt/vùng có SXHD", "C", "Kích hoạt bộ câu hỏi cảnh báo SXHD"),
    FeverField("animal_water_exposure", "Tiếp xúc động vật/lội nước lũ", "O", "Bệnh lây từ động vật, Leptospira", tri_state=False),
    FeverField("sick_contact", "Tiếp xúc người bệnh tương tự", "O", "Dịch tễ"),
    FeverField("immunization_status", "Tình trạng tiêm chủng", "C", "up_to_date/incomplete/unknown; kích hoạt tuổi <5", tri_state=False, allowed_values=("up_to_date", "incomplete", "unknown",)),
    FeverField("recent_vaccination_48h", "Tiêm chủng trong 48 giờ", "C", "Yếu tố nhiễu khi diễn giải sốt; kích hoạt tuổi <5"),
)

# ---------------------------------------------------------------------------------------------
# KM §3.11 — Nhóm MEDICATION
# ---------------------------------------------------------------------------------------------
_MEDICATION_FIELDS: tuple[FeverField, ...] = (
    FeverField("current_medications", "Thuốc đang dùng", "O", "Sốt do thuốc; tương tác an toàn", tri_state=False),
    FeverField("nsaid_use", "Đang dùng NSAID/aspirin", "C", "Cảnh báo an toàn bắt buộc trong bối cảnh SXHD (R-G-03)"),
    FeverField("anticoagulant_use", "Đang dùng chống đông", "O", "Diễn giải chảy máu khác đi"),
    FeverField("antibiotic_current", "Đang dùng kháng sinh", "H", "Sốt dai dẳng dù dùng KS = tín hiệu cần khám"),
    FeverField("new_medication_6w", "Thuốc mới trong 6 tuần", "O", "Sốt do thuốc"),
    FeverField("drug_allergies", "Dị ứng thuốc", "O", "An toàn cho tuyến sau", tri_state=False),
)

FEVER_FIELDS: tuple[FeverField, ...] = (
    _PATIENT_FIELDS
    + _FEVER_FIELDS
    + _GENERAL_FIELDS
    + _RESPIRATORY_FIELDS
    + _CIRCULATION_FIELDS
    + _NEUROLOGICAL_FIELDS
    + _SKIN_FIELDS
    + _ASSOCIATED_FIELDS
    + _RISK_FIELDS
    + _MEDICATION_FIELDS
)

FIELDS_BY_KEY: dict[str, FeverField] = {field.key: field for field in FEVER_FIELDS}


# ---------------------------------------------------------------------------------------------
# CS Part 3 — Question clusters, đúng thứ tự xuất hiện trong tài liệu (Q0-01 -> Q5-07)
# ---------------------------------------------------------------------------------------------
QUESTION_CLUSTERS: tuple[QuestionCluster, ...] = (
    # --- Stage E — Quét cấp cứu PHỔ QUÁT, trước cả nhân khẩu (2026-08-22) ---
    # Chỉ dấu hiệu không phụ thuộc tuổi/giới nên hỏi được khi chưa biết người bệnh là ai.
    *common_clusters.critical_scan_clusters("E"),
    # --- Stage 0 — Xác định đối tượng (CS §3.0) ---
    *common_clusters.demographic_clusters("0"),
    # --- Stage 1 — Phát hiện sốt (CS §3.1) ---
    QuestionCluster("Q1-01", "1", ("fever_reported",), script_hint="Hiện có đang sốt/cảm thấy nóng người không"),
    QuestionCluster("Q1-02", "1", ("fever_status", "temp_c", "temp_site", "temp_measured_at"), script_hint="Đã đo nhiệt độ chưa - bao nhiêu độ, đo ở đâu, cách đây bao lâu"),
    QuestionCluster("Q1-03", "1", ("fever_status", "temp_device_type"), script_hint="Hiện có nhiệt kế để đo thử ngay không"),
    # --- Stage 2 — Đặc điểm sốt (CS §3.2) ---
    QuestionCluster("Q2-01", "2", ("fever_onset_at",), script_hint="Bắt đầu sốt từ khi nào - mấy ngày rồi"),
    QuestionCluster("Q2-02", "2", ("rigors",), script_hint="Sốt có kèm rét run dữ dội, đắp chăn không đỡ không"),
    QuestionCluster("Q2-03", "2", ("antipyretic_taken", "antipyretic_drug", "antipyretic_response"), script_hint="Đã dùng thuốc hạ sốt chưa - thuốc gì, uống lúc nào, có đỡ không"),
    QuestionCluster("Q2-04", "2", ("worse_after_defervescence",), script_hint="Sau khi hạ sốt có thấy mệt hơn/lừ đừ hơn hay đỡ hơn"),
    QuestionCluster("Q2-05", "2", ("hypothermia_reported",), script_hint="Có lúc nào đo/cảm thấy người lạnh bất thường không"),
    # --- Stage 3A — Emergency scan (CS §3.3A), batch-negation ---
    *common_clusters.emergency_scan_clusters("3A"),
    # --- Stage 3B — Early/self-care scan (CS §3.3B), batch-negation ---
    *common_clusters.early_visit_scan_clusters("3B"),
    # --- Stage 4 — Đánh giá quần thể nguy cơ (CS §3.4) ---
    # `malaria_risk_area` nối thêm vào câu sàng lọc gộp Q4-00: nó là field DỊCH TỄ của riêng fever,
    # không nằm trong bộ nguy cơ phổ quát.
    *common_clusters.risk_context_clusters(
        "4",
        screening_extra_fields=("malaria_risk_area",),
        screening_hint="Câu sàng lọc rủi ro gộp: mang thai, hóa trị, bệnh mạn tính, phẫu thuật/ống thông, đi vùng sốt rét",
    ),
    QuestionCluster("Q4-06", "4", ("travel_history_12m", "malaria_risk_area"), script_hint="1-3 tháng gần đây có đi vùng sốt rét lưu hành không"),
    QuestionCluster("Q4-07", "4", ("outbreak_exposure", "mosquito_exposure"), script_hint="Xung quanh có ai bị SXHD/cúm/sởi/tay chân miệng không, có bị muỗi đốt nhiều không"),
    common_clusters.safety_netting_cluster("4"),
    # --- Stage 5 — Thu thập phần còn lại (CS §3.5) ---
    QuestionCluster("Q5-01", "5", ("urinary_symptoms",), script_hint="Có tiểu buốt, tiểu rắt, đau vùng hông lưng không"),
    QuestionCluster("Q5-02", "5", ("joint_limb_swelling", "non_weight_bearing"), script_hint="Có sưng đau khớp/chi nào không - có chịu đi lại được không"),
    QuestionCluster("Q5-03", "5", ("sore_throat", "ear_pain", "cough"), script_hint="Có đau họng, đau tai, ho, sổ mũi không"),
    QuestionCluster("Q5-04", "5", ("diarrhea", "bloody_stool"), script_hint="Có tiêu chảy không - phân có lẫn máu không"),
    *common_clusters.medication_clusters("5"),
    QuestionCluster("Q5-06", "5", ("immunization_status", "recent_vaccination_48h"), script_hint="Đã tiêm chủng đầy đủ theo lịch chưa, có tiêm vắc-xin trong 48 giờ gần đây không"),
    QuestionCluster("Q5-07", "5", ("myalgia_retroorbital_pain",), script_hint="Có đau nhức người, đau cơ, đau phía sau hốc mắt không"),
)

CLUSTERS_BY_ID: dict[str, QuestionCluster] = {cluster.id: cluster for cluster in QUESTION_CLUSTERS}


def clusters_for_stage(stage: Stage) -> tuple[QuestionCluster, ...]:
    return tuple(cluster for cluster in QUESTION_CLUSTERS if cluster.stage == stage)
