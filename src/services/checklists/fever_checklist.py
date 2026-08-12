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
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Tier = Literal["M0", "M1", "C", "O", "H"]
Stage = Literal["0", "1", "2", "3A", "3B", "4", "5"]


@dataclass(frozen=True, slots=True)
class FeverField:
    key: str
    label: str
    tier: Tier
    hint: str
    tri_state: bool = True


@dataclass(frozen=True, slots=True)
class QuestionCluster:
    id: str
    stage: Stage
    fields: tuple[str, ...]
    batch_negation: bool = False
    script_hint: str = ""


# ---------------------------------------------------------------------------------------------
# KM §3.2 — Nhóm PATIENT
# ---------------------------------------------------------------------------------------------
_PATIENT_FIELDS: tuple[FeverField, ...] = (
    FeverField("reporter_type", "Người khai là ai", "H", "self/parent_caregiver/other - độ tin cậy thông tin", tri_state=False),
    FeverField("age_value", "Tuổi (số)", "M0", "Biến phân tầng nguy cơ chính, quyết định toàn bộ ngưỡng/nhánh hỏi", tri_state=False),
    FeverField("age_unit", "Đơn vị tuổi", "M0", "day/month/year - đi kèm age_value", tri_state=False),
    FeverField("sex", "Giới tính sinh học", "M0", "male/female/unknown - điều hướng nhánh sản khoa/tiết niệu", tri_state=False),
    FeverField("weight_kg", "Cân nặng (kg)", "O", "Chỉ dùng cảnh báo quá liều paracetamol", tri_state=False),
    FeverField("lives_alone", "Sống một mình", "M1", "Điều kiện an toàn của SELF_CARE (RF-38)"),
    FeverField("caregiver_available", "Có người theo dõi 24h", "M1", "Điều kiện an toàn của SELF_CARE (RF-38)"),
    FeverField("access_to_care_minutes", "Thời gian tới cơ sở y tế gần nhất (phút)", "O", "Ảnh hưởng ngưỡng thận trọng", tri_state=False),
    FeverField("can_return_for_followup", "Có thể tái khám khi trở nặng", "C", "Tiền đề safety-netting; hiệu lực M1 khi hướng SELF_CARE"),
)

# ---------------------------------------------------------------------------------------------
# KM §3.3 — Nhóm FEVER
# ---------------------------------------------------------------------------------------------
_FEVER_FIELDS: tuple[FeverField, ...] = (
    FeverField("fever_reported", "Người dùng khai có sốt", "M0", "Cổng vào toàn bộ protocol sốt"),
    FeverField("fever_status", "Loại sốt", "M0", "objective/subjective/none - điều hướng nhánh dữ liệu thiếu", tri_state=False),
    FeverField("temp_c", "Nhiệt độ đo được (°C)", "M0", "Đầu vào rule ngưỡng theo tuổi; M0 khi fever_status=objective", tri_state=False),
    FeverField("temp_site", "Vị trí đo", "M0", "axillary/oral/rectal/tympanic/temporal - quyết định ngưỡng áp dụng", tri_state=False),
    FeverField("temp_measured_at", "Thời điểm đo", "C", "Số đo cũ -> độ tin cậy thấp hơn", tri_state=False),
    FeverField("temp_device_type", "Loại nhiệt kế", "O", "Gán measurement_confidence", tri_state=False),
    FeverField("temp_max_24h_c", "Nhiệt độ cao nhất 24h qua (°C)", "O", "Bắt đỉnh sốt bị thuốc che", tri_state=False),
    FeverField("fever_onset_at", "Thời điểm bắt đầu sốt", "M0", "Tính fever_duration_days - mốc 5/7 ngày", tri_state=False),
    FeverField("fever_pattern", "Kiểu sốt", "O", "continuous/intermittent/relapsing - giá trị hạn chế", tri_state=False),
    FeverField("rigors", "Rét run dữ dội", "M0", "Amber NICE; gợi ý nhiễm khuẩn huyết/sốt rét"),
    FeverField("hypothermia_reported", "Nhiệt độ < 36°C", "C", "Red flag ở nhóm nguy cơ, kích hoạt theo tuổi/miễn dịch"),
    FeverField("antipyretic_taken", "Đã dùng thuốc hạ sốt", "M0", "Nhiệt độ hiện tại có thể bị che"),
    FeverField("antipyretic_drug", "Tên hoạt chất hạ sốt", "C", "Sàng lọc NSAID trong bối cảnh SXHD", tri_state=False),
    FeverField("antipyretic_total_24h_mg", "Tổng liều 24h (mg)", "O", "Cảnh báo quá liều paracetamol", tri_state=False),
    FeverField("antipyretic_response", "Đáp ứng sau khi uống thuốc", "O", "Không dùng để loại trừ bệnh nặng", tri_state=False),
    FeverField("worse_after_defervescence", "Mệt/khó chịu hơn dù đã hạ sốt", "M0", "Dấu hiệu khám lại ngay theo QĐ 2760 (RF-29)"),
)

# ---------------------------------------------------------------------------------------------
# KM §3.4 — Nhóm GENERAL
# ---------------------------------------------------------------------------------------------
_GENERAL_FIELDS: tuple[FeverField, ...] = (
    FeverField("consciousness_level", "Mức tỉnh táo", "M0", "Yếu tố tiên lượng mạnh nhất mọi thang triage (RF-01)", tri_state=False),
    FeverField("new_confusion", "Lú lẫn/thay đổi hành vi mới", "C", "Biểu hiện duy nhất ở người già (RF-05); kích hoạt tuổi >=16"),
    FeverField("social_response_child", "Đáp ứng xã hội của trẻ", "C", "Lõi traffic light NICE; kích hoạt tuổi <5", tri_state=False),
    FeverField("activity_vs_baseline", "Hoạt động so với ngày thường", "M1", "Chuẩn hóa theo baseline cá nhân", tri_state=False),
    FeverField("feeding_intake", "Ăn/uống/bú", "M0", "IMCI danger sign", tri_state=False),
    FeverField("caregiver_concern_level", "Mức lo lắng người chăm sóc (0-10)", "M1", "Tín hiệu độc lập có giá trị theo NICE", tri_state=False),
    FeverField("looks_very_unwell", "Trông rất mệt/khác hẳn thường ngày", "M1", "Proxy ill-appearance khi không khám trực tiếp được"),
)

# ---------------------------------------------------------------------------------------------
# KM §3.5 — Nhóm RESPIRATORY
# ---------------------------------------------------------------------------------------------
_RESPIRATORY_FIELDS: tuple[FeverField, ...] = (
    FeverField("breathing_difficulty", "Khó thở", "M0", "none/mild/severe - cấu phần red/amber hô hấp", tri_state=False),
    FeverField("rapid_breathing", "Thở nhanh hơn bình thường", "M1", "Dấu hiệu nặng nhận biết từ xa"),
    FeverField("chest_indrawing", "Rút lõm lồng ngực", "C", "Suy hô hấp ở trẻ -> red (RF-09); kích hoạt tuổi <5"),
    FeverField("nasal_flaring_grunting", "Phập phồng cánh mũi/thở rên", "C", "Red ở trẻ (RF-09); kích hoạt tuổi <5"),
    FeverField("cyanosis", "Tím môi/đầu chi", "M0", "Red tuyệt đối (RF-08)"),
    FeverField("stridor_or_drooling", "Thở rít/chảy dãi, không nuốt được", "M0", "Nghi tắc nghẽn đường thở trên (RF-10)"),
    FeverField("chest_pain", "Đau ngực", "C", "Cross-protocol; kích hoạt tuổi >=12"),
    FeverField("hemoptysis", "Ho ra máu", "O", "Cần khám"),
    FeverField("spo2_percent", "SpO2 tự đo (%)", "O", "Bổ trợ hô hấp; <=95% khí trời là amber ở trẻ", tri_state=False),
)

# ---------------------------------------------------------------------------------------------
# KM §3.6 — Nhóm CIRCULATION & HYDRATION
# ---------------------------------------------------------------------------------------------
_CIRCULATION_FIELDS: tuple[FeverField, ...] = (
    FeverField("cold_clammy_skin", "Da lạnh, ẩm, nổi vân tím", "M0", "Dấu hiệu sốc (RF-13)"),
    FeverField("capillary_refill_ge_3s", "CRT >= 3 giây", "M0", "Giảm tưới máu (RF-13)"),
    FeverField("dizziness_on_standing", "Choáng khi đứng dậy", "M1", "Giảm thể tích tuần hoàn - tiền sốc"),
    FeverField("urine_output", "Lượng nước tiểu", "M0", "normal/reduced/none_gt_6h - tưới máu thận (RF-14)", tri_state=False),
    FeverField("dehydration_signs", "Dấu mất nước", "O", "Đa dấu hiệu: khô môi, mắt trũng, thóp lõm...", tri_state=False),
    FeverField("vomiting_severity", "Mức độ nôn", "M0", "none/occasional/frequent/unable_to_keep_fluids (RF-15,40)", tri_state=False),
)

# ---------------------------------------------------------------------------------------------
# KM §3.7 — Nhóm NEUROLOGICAL
# ---------------------------------------------------------------------------------------------
_NEUROLOGICAL_FIELDS: tuple[FeverField, ...] = (
    FeverField("seizure_occurred", "Có co giật trong đợt bệnh này", "M0", "IMCI general danger sign (RF-02)"),
    FeverField("seizure_active_now", "Đang co giật", "C", "Cấp cứu tối khẩn (RF-02)"),
    FeverField("seizure_features", "Đặc điểm cơn co giật", "C", "focal/duration_gt_5min/recurrent_24h/incomplete_recovery (RF-03)", tri_state=False),
    FeverField("neck_stiffness", "Cứng gáy", "M0", "Nghi nhiễm khuẩn thần kinh trung ương (RF-04)"),
    FeverField("photophobia", "Sợ ánh sáng", "O", "Đi kèm cứng gáy"),
    FeverField("severe_headache", "Đau đầu dữ dội/khác thường", "M0", "Cross-protocol đau đầu (RF-04)"),
    FeverField("bulging_fontanelle", "Thóp phồng", "C", "Red ở nhũ nhi (RF-04); kích hoạt tuổi <18 tháng"),
    FeverField("focal_neuro_deficit", "Yếu liệt/nói khó mới", "M0", "Cross-protocol đột quỵ/viêm não (RF-06)"),
)

# ---------------------------------------------------------------------------------------------
# KM §3.8 — Nhóm SKIN & BLEEDING
# ---------------------------------------------------------------------------------------------
_SKIN_FIELDS: tuple[FeverField, ...] = (
    FeverField("non_blanching_rash", "Ban không mất khi ấn kính", "M0", "Red flag kinh điển nghi não mô cầu (RF-18)"),
    FeverField("rash_present", "Có ban", "C", "Chỉ hỏi riêng khi non_blanching_rash dương tính/mơ hồ"),
    FeverField("rash_type", "Kiểu ban", "C", "petechial/maculopapular/vesicular/urticarial", tri_state=False),
    FeverField("mucosal_bleeding", "Chảy máu chân răng/mũi/âm đạo bất thường", "M0", "Cảnh báo SXHD -> nhập viện (RF-19)"),
    FeverField("gi_bleeding", "Nôn ra máu / phân đen", "M0", "Xuất huyết nặng (RF-20)"),
    FeverField("jaundice_new", "Vàng da mới", "O", "Tổn thương gan/nhiễm khuẩn nặng"),
    FeverField("localized_infection_signs", "Sưng nóng đỏ khu trú/áp xe/vết loét", "O", "Ổ nhiễm khuẩn"),
)

# ---------------------------------------------------------------------------------------------
# KM §3.9 — Nhóm ASSOCIATED SYMPTOMS
# ---------------------------------------------------------------------------------------------
_ASSOCIATED_FIELDS: tuple[FeverField, ...] = (
    FeverField("abdominal_pain_severity", "Mức độ đau bụng", "M0", "none/mild/moderate/severe - cảnh báo SXHD (RF-39)", tri_state=False),
    FeverField("abdominal_pain_location", "Vị trí đau bụng", "C", "Định hướng cho người duyệt", tri_state=False),
    FeverField("abdominal_guarding", "Bụng cứng/ấn rất đau", "C", "Nghi bụng ngoại khoa (RF-39)"),
    FeverField("diarrhea", "Tiêu chảy", "M1", "Mất nước, nguồn nhiễm"),
    FeverField("bloody_stool", "Phân máu", "C", "Cần khám"),
    FeverField("urinary_symptoms", "Tiểu buốt/rắt/đau hông lưng", "C", "NICE: luôn cân nhắc NKTN ở trẻ <5 tuổi sốt không rõ ổ (RF-42)"),
    FeverField("sore_throat", "Đau họng", "O", "Định hướng ổ nhiễm khuẩn lành tính hơn"),
    FeverField("ear_pain", "Đau tai", "O", "Định hướng ổ nhiễm khuẩn lành tính hơn"),
    FeverField("cough", "Ho", "O", "Định hướng ổ nhiễm khuẩn lành tính hơn"),
    FeverField("joint_limb_swelling", "Sưng đau khớp/chi", "M1", "Amber NICE - nghi nhiễm khuẩn xương khớp (RF-41)"),
    FeverField("non_weight_bearing", "Không chịu đi/không dùng chi", "C", "Amber NICE (RF-41); kích hoạt tuổi <16"),
    FeverField("myalgia_retroorbital_pain", "Đau cơ, đau hốc mắt", "O", "Bộ triệu chứng gợi ý bệnh virus lưu hành VN"),
)

# ---------------------------------------------------------------------------------------------
# KM §3.10 — Nhóm RISK
# ---------------------------------------------------------------------------------------------
_RISK_FIELDS: tuple[FeverField, ...] = (
    FeverField("chronic_conditions", "Bệnh mạn tính", "M1", "Lý do cân nhắc nhập viện theo BYT (RF-36)", tri_state=False),
    FeverField("obesity_or_malnutrition", "Béo phì/suy dinh dưỡng", "O", "Tăng nặng, khó đánh giá", tri_state=False),
    FeverField("immunocompromised", "Suy giảm miễn dịch", "M1", "Nhóm nguy cơ cao nhất (RF-31)"),
    FeverField("immunocompromise_cause", "Nguyên nhân suy giảm miễn dịch", "C", "chemotherapy_6w/transplant/hiv_uncontrolled...", tri_state=False),
    FeverField("known_neutropenia", "Đã biết giảm bạch cầu hạt", "C", "Kích hoạt ngưỡng sốt 38,3°C/38,0°C >=1h (RF-30)"),
    FeverField("is_pregnant", "Đang mang thai", "C", "Nhánh sản khoa riêng (RF-32); kích hoạt nữ 10-60 tuổi"),
    FeverField("gestational_weeks", "Tuần thai", "C", "3 tháng cuối sinh lý khác", tri_state=False),
    FeverField("postpartum_6w", "Sinh/sảy/nạo hút trong 6 tuần", "C", "Nguy cơ nhiễm khuẩn hậu sản (RF-32)"),
    FeverField("obstetric_red_flags", "Dấu hiệu sản khoa cần cấp cứu", "C", "Đau bụng/ra máu/giảm cử động thai", tri_state=False),
    FeverField("recent_surgery_30d", "Phẫu thuật/thủ thuật <=30 ngày", "M1", "Nguy cơ nhiễm khuẩn vết mổ/sepsis (RF-33)"),
    FeverField("surgical_site_signs", "Vết mổ sưng đỏ/chảy dịch/hở", "C", "Ổ nhiễm khuẩn rõ (RF-33)"),
    FeverField("indwelling_device", "Thiết bị lưu trong cơ thể", "M1", "Đường vào nhiễm khuẩn (RF-34)", tri_state=False),
    FeverField("recent_wound_or_bite", "Vết thương hở/bỏng/động vật cắn", "O", "Nhiễm khuẩn mô mềm, uốn ván"),
    FeverField("travel_history_12m", "Du lịch gần đây", "C", "Vùng sốt rét lưu hành = nguy cơ cao (RF-35)", tri_state=False),
    FeverField("malaria_risk_area", "Vùng đến có sốt rét lưu hành", "C", "Cấp cứu tiềm tàng (RF-35)"),
    FeverField("outbreak_exposure", "Ổ dịch quanh khu vực/gia đình", "H", "Thay đổi xác suất nền", tri_state=False),
    FeverField("mosquito_exposure", "Bị muỗi đốt/vùng có SXHD", "C", "Kích hoạt bộ câu hỏi cảnh báo SXHD"),
    FeverField("animal_water_exposure", "Tiếp xúc động vật/lội nước lũ", "O", "Bệnh lây từ động vật, Leptospira", tri_state=False),
    FeverField("sick_contact", "Tiếp xúc người bệnh tương tự", "O", "Dịch tễ"),
    FeverField("immunization_status", "Tình trạng tiêm chủng", "C", "up_to_date/incomplete/unknown; kích hoạt tuổi <5", tri_state=False),
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
    # --- Stage 0 — Xác định đối tượng (CS §3.0) ---
    QuestionCluster("Q0-01", "0", ("age_value", "age_unit", "reporter_type"), script_hint="Người đang cần tư vấn là bé hay người lớn, bao nhiêu tuổi/tháng"),
    QuestionCluster("Q0-02", "0", ("sex",), script_hint="Nam hay nữ"),
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
    QuestionCluster("Q3-01", "3A", ("consciousness_level", "social_response_child"), batch_negation=True, script_hint="Hiện có tỉnh táo bình thường không - dễ đánh thức, phản ứng gọi hỏi bình thường không"),
    QuestionCluster("Q3-03", "3A", ("seizure_occurred", "seizure_active_now", "seizure_features"), batch_negation=True, script_hint="Có bị co giật không - đang co giật ngay lúc này không"),
    QuestionCluster("Q3-04", "3A", ("neck_stiffness", "photophobia", "severe_headache", "bulging_fontanelle"), batch_negation=True, script_hint="Có cứng gáy, sợ ánh sáng, đau đầu dữ dội khác thường không"),
    QuestionCluster("Q3-05", "3A", ("focal_neuro_deficit",), batch_negation=True, script_hint="Có yếu tay/chân một bên, méo miệng, nói khó mới xuất hiện không"),
    QuestionCluster("Q3-06", "3A", ("breathing_difficulty", "cyanosis", "chest_indrawing", "nasal_flaring_grunting"), batch_negation=True, script_hint="Có khó thở không - môi/đầu ngón tay tím tái không"),
    QuestionCluster("Q3-07", "3A", ("stridor_or_drooling",), batch_negation=True, script_hint="Có thở rít khi hít vào, chảy dãi không nuốt được không"),
    QuestionCluster("Q3-08", "3A", ("cold_clammy_skin", "capillary_refill_ge_3s"), batch_negation=True, script_hint="Da có lạnh, ẩm, nổi vân tím không - CRT có chậm không"),
    QuestionCluster("Q3-09", "3A", ("urine_output", "feeding_intake", "vomiting_severity"), batch_negation=True, script_hint="6 giờ qua có đi tiểu không, ăn uống được không, có nôn nhiều không"),
    QuestionCluster("Q3-11", "3A", ("non_blanching_rash", "rash_present", "rash_type"), batch_negation=True, script_hint="Trên da có nổi ban đỏ/tím không - ấn kính vào có mất không"),
    QuestionCluster("Q3-12", "3A", ("mucosal_bleeding", "gi_bleeding"), batch_negation=True, script_hint="Có chảy máu bất thường không - chân răng, mũi, nôn ra máu, phân đen"),
    QuestionCluster("Q3-13", "3A", ("abdominal_pain_severity", "abdominal_pain_location", "abdominal_guarding"), batch_negation=True, script_hint="Có đau bụng không - mức nào, bụng có cứng không"),
    # --- Stage 3B — Early/self-care scan (CS §3.3B), batch-negation ---
    QuestionCluster("Q3-01b", "3B", ("activity_vs_baseline", "rapid_breathing"), batch_negation=True, script_hint="So với ngày thường mức độ hoạt động có giảm nhiều không, thở có nhanh hơn không"),
    QuestionCluster("Q3-08b", "3B", ("dizziness_on_standing",), batch_negation=True, script_hint="Khi đứng dậy đột ngột có thấy choáng váng không"),
    QuestionCluster("Q3-02", "3B", ("new_confusion",), batch_negation=True, script_hint="Gần đây có ai nhận thấy nói lẫn, hành vi khác lạ hẳn không"),
    QuestionCluster("Q3-13b", "3B", ("joint_limb_swelling", "non_weight_bearing"), batch_negation=True, script_hint="Có sưng đau khớp/chi nào không - có chịu đi lại được không"),
    QuestionCluster("Q3-14", "3B", ("caregiver_concern_level", "looks_very_unwell"), batch_negation=True, script_hint="Trên thang 0-10 lo lắng đến mức nào, có trông khác hẳn không"),
    # --- Stage 4 — Đánh giá quần thể nguy cơ (CS §3.4) ---
    QuestionCluster("Q4-00", "4", ("is_pregnant", "immunocompromised", "chronic_conditions", "recent_surgery_30d", "indwelling_device", "malaria_risk_area"), script_hint="Câu sàng lọc rủi ro gộp: mang thai, hóa trị, bệnh mạn tính, phẫu thuật/ống thông, đi vùng sốt rét"),
    QuestionCluster("Q4-01", "4", ("is_pregnant", "gestational_weeks"), script_hint="Hiện có đang mang thai không - được bao nhiêu tuần"),
    QuestionCluster("Q4-01b", "4", ("obstetric_red_flags",), script_hint="Có ra máu/dịch bất thường, đau bụng từng cơn, giảm cử động thai không"),
    QuestionCluster("Q4-02", "4", ("postpartum_6w",), script_hint="6 tuần gần đây có sinh nở, sảy thai, nạo hút thai không"),
    QuestionCluster("Q4-03", "4", ("immunocompromised", "immunocompromise_cause", "known_neutropenia"), script_hint="Có đang hóa trị, ghép tạng, dùng thuốc ức chế miễn dịch, HIV không kiểm soát không"),
    QuestionCluster("Q4-04", "4", ("chronic_conditions",), script_hint="Có đang mắc bệnh mạn tính nào không - tim, phổi, gan, thận, tiểu đường, thalassemia"),
    QuestionCluster("Q4-05", "4", ("recent_surgery_30d", "surgical_site_signs", "indwelling_device"), script_hint="30 ngày gần đây có phẫu thuật không, hiện có ống thông/catheter/dẫn lưu không"),
    QuestionCluster("Q4-06", "4", ("travel_history_12m", "malaria_risk_area"), script_hint="1-3 tháng gần đây có đi vùng sốt rét lưu hành không"),
    QuestionCluster("Q4-07", "4", ("outbreak_exposure", "mosquito_exposure"), script_hint="Xung quanh có ai bị SXHD/cúm/sởi/tay chân miệng không, có bị muỗi đốt nhiều không"),
    QuestionCluster("Q4-08", "4", ("lives_alone", "caregiver_available", "access_to_care_minutes"), script_hint="Sống một mình hay có người theo dõi, từ nhà đến cơ sở y tế mất bao lâu"),
    # --- Stage 5 — Thu thập phần còn lại (CS §3.5) ---
    QuestionCluster("Q5-01", "5", ("urinary_symptoms",), script_hint="Có tiểu buốt, tiểu rắt, đau vùng hông lưng không"),
    QuestionCluster("Q5-02", "5", ("joint_limb_swelling", "non_weight_bearing"), script_hint="Có sưng đau khớp/chi nào không - có chịu đi lại được không"),
    QuestionCluster("Q5-03", "5", ("sore_throat", "ear_pain", "cough"), script_hint="Có đau họng, đau tai, ho, sổ mũi không"),
    QuestionCluster("Q5-04", "5", ("diarrhea", "bloody_stool"), script_hint="Có tiêu chảy không - phân có lẫn máu không"),
    QuestionCluster("Q5-05a", "5", ("nsaid_use",), script_hint="Có đang dùng thuốc giảm đau/hạ sốt nào khác ngoài paracetamol không"),
    QuestionCluster("Q5-05b", "5", ("antibiotic_current",), script_hint="Có đang dùng kháng sinh nào không"),
    QuestionCluster("Q5-06", "5", ("immunization_status", "recent_vaccination_48h"), script_hint="Đã tiêm chủng đầy đủ theo lịch chưa, có tiêm vắc-xin trong 48 giờ gần đây không"),
    QuestionCluster("Q5-07", "5", ("myalgia_retroorbital_pain",), script_hint="Có đau nhức người, đau cơ, đau phía sau hốc mắt không"),
)

CLUSTERS_BY_ID: dict[str, QuestionCluster] = {cluster.id: cluster for cluster in QUESTION_CLUSTERS}


def clusters_for_stage(stage: Stage) -> tuple[QuestionCluster, ...]:
    return tuple(cluster for cluster in QUESTION_CLUSTERS if cluster.stage == stage)
