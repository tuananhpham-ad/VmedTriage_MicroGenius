"""Field DÙNG CHUNG cho mọi than phiền: nhân khẩu, an toàn tại nhà, dấu hiệu đỏ phổ quát, bối cảnh
nguy cơ, thuốc đang dùng.

Chép NGUYÊN VĂN từ `fever_checklist.py` (nguồn gốc: `docs/medical_knowledge/fever-knowledge-model.md`
§3.2-3.11) - `key`, `label`, `tier`, `hint`, `tri_state`, `allowed_values` không đổi một ký tự nào, để
refactor này không đổi hành vi của fever. Fever import lại từ đây và bổ sung phần đặc thù của nó.

VÌ SAO TÁCH: dấu hiệu đỏ như co giật, tím tái, ban không mất khi ấn kính, chảy máu tiêu hoá không phải
là kiến thức về SỐT - chúng là kiến thức về "người bệnh đang nguy kịch". Để chúng nằm trong
`fever_checklist.py` nghĩa là protocol thứ hai hoặc phải import từ fever (sai chiều phụ thuộc), hoặc
phải chép lại (hai bản sao sẽ lệch nhau). Đây là lỗ hổng an toàn có thật đang mở: sau khi `/chat` đổi
sang agent fever, người nhắn "tôi đau ngực, đi vài bước là hụt hơi" không còn LUẬT ĐỎ NÀO quét.
"""

from __future__ import annotations

from src.services.symptom_protocol.models import FieldSpec

# --- Nhân khẩu (KM §3.2) ------------------------------------------------------------------------
DEMOGRAPHIC_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("reporter_type", "Người khai là ai", "H", "self/parent_caregiver/other - độ tin cậy thông tin", tri_state=False, allowed_values=("self", "parent_caregiver", "other",)),
    FieldSpec("age_value", "Tuổi (số)", "M0", "Biến phân tầng nguy cơ chính, quyết định toàn bộ ngưỡng/nhánh hỏi", tri_state=False),
    FieldSpec("age_unit", "Đơn vị tuổi", "M0", "day/month/year - đi kèm age_value", tri_state=False, allowed_values=("day", "month", "year",)),
    FieldSpec("sex", "Giới tính sinh học", "M0", "male/female/unknown - điều hướng nhánh sản khoa/tiết niệu", tri_state=False, allowed_values=("male", "female", "unknown",)),
)

# --- An toàn tại nhà / safety-netting (KM §3.2) --------------------------------------------------
SAFETY_NETTING_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("lives_alone", "Sống một mình", "M1", "Điều kiện an toàn của SELF_CARE (RF-38)"),
    FieldSpec("caregiver_available", "Có người theo dõi 24h", "M1", "Điều kiện an toàn của SELF_CARE (RF-38)"),
    FieldSpec("access_to_care_minutes", "Thời gian tới cơ sở y tế gần nhất (phút)", "O", "Ảnh hưởng ngưỡng thận trọng", tri_state=False),
    FieldSpec("can_return_for_followup", "Có thể tái khám khi trở nặng", "C", "Tiền đề safety-netting; hiệu lực M1 khi hướng SELF_CARE"),
)

# --- Toàn trạng / tri giác (KM §3.4) ------------------------------------------------------------
GENERAL_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("consciousness_level", "Mức tỉnh táo", "M0", "Yếu tố tiên lượng mạnh nhất mọi thang triage (RF-01)", tri_state=False, allowed_values=("alert", "drowsy_but_rousable", "difficult_to_rouse", "unresponsive", "unknown",)),
    FieldSpec("new_confusion", "Lú lẫn/thay đổi hành vi mới", "C", "Biểu hiện duy nhất ở người già (RF-05); kích hoạt tuổi >=16"),
    FieldSpec("social_response_child", "Đáp ứng xã hội của trẻ", "C", "Lõi traffic light NICE; kích hoạt tuổi <5", tri_state=False, allowed_values=("normal", "reduced", "no_response", "not_applicable",)),
    FieldSpec("activity_vs_baseline", "Hoạt động so với ngày thường", "M1", "Chuẩn hóa theo baseline cá nhân", tri_state=False, allowed_values=("normal", "reduced", "markedly_reduced", "unknown",)),
    FieldSpec("feeding_intake", "Ăn/uống/bú", "M0", "IMCI danger sign", tri_state=False, allowed_values=("normal", "reduced", "unable", "unknown",)),
    FieldSpec("caregiver_concern_level", "Mức lo lắng người chăm sóc (0-10)", "M1", "Tín hiệu độc lập có giá trị theo NICE", tri_state=False),
    FieldSpec("looks_very_unwell", "Trông rất mệt/khác hẳn thường ngày", "M1", "Proxy ill-appearance khi không khám trực tiếp được"),
)

# --- Hô hấp (KM §3.5) ---------------------------------------------------------------------------
RESPIRATORY_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("breathing_difficulty", "Khó thở", "M0", "none/mild/severe - cấu phần red/amber hô hấp", tri_state=False, allowed_values=("none", "mild", "severe", "unknown",)),
    FieldSpec("rapid_breathing", "Thở nhanh hơn bình thường", "M1", "Dấu hiệu nặng nhận biết từ xa"),
    FieldSpec("chest_indrawing", "Rút lõm lồng ngực", "C", "Suy hô hấp ở trẻ -> red (RF-09); kích hoạt tuổi <5"),
    FieldSpec("nasal_flaring_grunting", "Phập phồng cánh mũi/thở rên", "C", "Red ở trẻ (RF-09); kích hoạt tuổi <5"),
    FieldSpec("cyanosis", "Tím môi/đầu chi", "M0", "Red tuyệt đối (RF-08)"),
    FieldSpec("stridor_or_drooling", "Thở rít/chảy dãi, không nuốt được", "M0", "Nghi tắc nghẽn đường thở trên (RF-10)"),
    FieldSpec("chest_pain", "Đau ngực", "C", "Cross-protocol; kích hoạt tuổi >=12"),
    FieldSpec("hemoptysis", "Ho ra máu", "O", "Cần khám"),
    FieldSpec("spo2_percent", "SpO2 tự đo (%)", "O", "Bổ trợ hô hấp; <=95% khí trời là amber ở trẻ", tri_state=False),
)

# --- Tuần hoàn & mất nước (KM §3.6) --------------------------------------------------------------
CIRCULATION_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("cold_clammy_skin", "Da lạnh, ẩm, nổi vân tím", "M0", "Dấu hiệu sốc (RF-13)"),
    FieldSpec("capillary_refill_ge_3s", "CRT >= 3 giây", "M0", "Giảm tưới máu (RF-13)"),
    FieldSpec("dizziness_on_standing", "Choáng khi đứng dậy", "M1", "Giảm thể tích tuần hoàn - tiền sốc"),
    FieldSpec("urine_output", "Lượng nước tiểu", "M0", "normal/reduced/none_gt_6h - tưới máu thận (RF-14)", tri_state=False, allowed_values=("normal", "reduced", "none_gt_6h", "unknown",)),
    FieldSpec("dehydration_signs", "Dấu mất nước", "O", "Đa dấu hiệu: khô môi, mắt trũng, thóp lõm...", tri_state=False),
    FieldSpec("vomiting_severity", "Mức độ nôn", "M0", "none/occasional/frequent/unable_to_keep_fluids (RF-15,40)", tri_state=False, allowed_values=("none", "occasional", "frequent", "unable_to_keep_fluids", "unknown",)),
)

# --- Thần kinh (KM §3.7) ------------------------------------------------------------------------
NEUROLOGICAL_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("seizure_occurred", "Có co giật trong đợt bệnh này", "M0", "IMCI general danger sign (RF-02)"),
    FieldSpec("seizure_active_now", "Đang co giật", "C", "Cấp cứu tối khẩn (RF-02)"),
    FieldSpec("seizure_features", "Đặc điểm cơn co giật", "C", "focal/duration_gt_5min/recurrent_24h/incomplete_recovery (RF-03)", tri_state=False),
    FieldSpec("neck_stiffness", "Cứng gáy", "M0", "Nghi nhiễm khuẩn thần kinh trung ương (RF-04)"),
    FieldSpec("photophobia", "Sợ ánh sáng", "O", "Đi kèm cứng gáy"),
    FieldSpec("severe_headache", "Đau đầu dữ dội/khác thường", "M0", "Cross-protocol đau đầu (RF-04)"),
    FieldSpec("bulging_fontanelle", "Thóp phồng", "C", "Red ở nhũ nhi (RF-04); kích hoạt tuổi <18 tháng"),
    FieldSpec("focal_neuro_deficit", "Yếu liệt/nói khó mới", "M0", "Cross-protocol đột quỵ/viêm não (RF-06)"),
)

# --- Da & chảy máu (KM §3.8) --------------------------------------------------------------------
SKIN_BLEEDING_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("non_blanching_rash", "Ban không mất khi ấn kính", "M0", "Red flag kinh điển nghi não mô cầu (RF-18)"),
    FieldSpec("rash_present", "Có ban", "C", "Chỉ hỏi riêng khi non_blanching_rash dương tính/mơ hồ"),
    FieldSpec("rash_type", "Kiểu ban", "C", "petechial/maculopapular/vesicular/urticarial", tri_state=False, allowed_values=("petechial", "maculopapular", "vesicular", "urticarial", "other", "unknown",)),
    FieldSpec("mucosal_bleeding", "Chảy máu chân răng/mũi/âm đạo bất thường", "M0", "Cảnh báo SXHD -> nhập viện (RF-19)"),
    FieldSpec("gi_bleeding", "Nôn ra máu / phân đen", "M0", "Xuất huyết nặng (RF-20)"),
    FieldSpec("jaundice_new", "Vàng da mới", "O", "Tổn thương gan/nhiễm khuẩn nặng"),
    FieldSpec("localized_infection_signs", "Sưng nóng đỏ khu trú/áp xe/vết loét", "O", "Ổ nhiễm khuẩn"),
)

# --- Triệu chứng đi kèm hay gặp ở mọi than phiền (KM §3.9) ---------------------------------------
ASSOCIATED_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("abdominal_pain_severity", "Mức độ đau bụng", "M0", "none/mild/moderate/severe - cảnh báo SXHD (RF-39)", tri_state=False, allowed_values=("none", "mild", "moderate", "severe", "unknown",)),
    FieldSpec("abdominal_pain_location", "Vị trí đau bụng", "C", "Định hướng cho người duyệt", tri_state=False, allowed_values=("diffuse", "ruq", "rlq", "epigastric", "other", "unknown",)),
    FieldSpec("abdominal_guarding", "Bụng cứng/ấn rất đau", "C", "Nghi bụng ngoại khoa (RF-39)"),
    FieldSpec("diarrhea", "Tiêu chảy", "M1", "Mất nước, nguồn nhiễm"),
    FieldSpec("bloody_stool", "Phân máu", "C", "Cần khám"),
    FieldSpec("urinary_symptoms", "Tiểu buốt/rắt/đau hông lưng", "C", "NICE: luôn cân nhắc NKTN ở trẻ <5 tuổi sốt không rõ ổ (RF-42)"),
    FieldSpec("joint_limb_swelling", "Sưng đau khớp/chi", "M1", "Amber NICE - nghi nhiễm khuẩn xương khớp (RF-41)"),
    FieldSpec("non_weight_bearing", "Không chịu đi/không dùng chi", "C", "Amber NICE (RF-41); kích hoạt tuổi <16"),
)

# --- Bối cảnh nguy cơ (KM §3.10) ----------------------------------------------------------------
RISK_CONTEXT_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("chronic_conditions", "Bệnh mạn tính", "M1", "Lý do cân nhắc nhập viện theo BYT (RF-36)", tri_state=False),
    FieldSpec("obesity_or_malnutrition", "Béo phì/suy dinh dưỡng", "O", "Tăng nặng, khó đánh giá", tri_state=False, allowed_values=("none", "obesity", "malnutrition", "unknown",)),
    # Hint của 2 field này CỐ Ý dài: nó là chỗ duy nhất chặn được việc model suy từ NHÃN BỆNH sang
    # tình trạng miễn dịch. "Tôi có HIV" -> ghi vào bệnh nền, KHÔNG đủ để kết luận suy giảm miễn dịch
    # (HIV điều trị tốt không thuộc nhóm nguy cơ này) - suy diễn sai ở đây vừa đổi mức triage vừa dán
    # nhãn sai cho người bệnh về một thông tin rất nhạy cảm.
    FieldSpec("immunocompromised", "Suy giảm miễn dịch", "M1", "Nhóm nguy cơ cao nhất (RF-31). CHỈ đặt \"true\" khi lời khai thực sự hỗ trợ: đang hoá trị, ghép tạng, dùng thuốc ức chế miễn dịch, HIV KHÔNG kiểm soát. Riêng việc CÓ một bệnh truyền nhiễm (HIV đang điều trị ổn, viêm gan, giang mai...) KHÔNG đủ - để \"unknown\" và ghi tên bệnh vào chronic_conditions"),
    FieldSpec("immunocompromise_cause", "Nguyên nhân suy giảm miễn dịch", "C", "chemotherapy_6w/transplant/immunosuppressant/hiv_uncontrolled - chỉ điền khi người bệnh nói rõ nguyên nhân, không suy từ tên bệnh", tri_state=False),
    FieldSpec("known_neutropenia", "Đã biết giảm bạch cầu hạt", "C", "Kích hoạt ngưỡng sốt 38,3°C/38,0°C >=1h (RF-30)"),
    FieldSpec("is_pregnant", "Đang mang thai", "C", "Nhánh sản khoa riêng (RF-32); kích hoạt nữ 10-60 tuổi"),
    FieldSpec("gestational_weeks", "Tuần thai", "C", "3 tháng cuối sinh lý khác", tri_state=False),
    FieldSpec("postpartum_6w", "Sinh/sảy/nạo hút trong 6 tuần", "C", "Nguy cơ nhiễm khuẩn hậu sản (RF-32)"),
    FieldSpec("obstetric_red_flags", "Dấu hiệu sản khoa cần cấp cứu", "C", "Đau bụng/ra máu/giảm cử động thai", tri_state=False),
    FieldSpec("recent_surgery_30d", "Phẫu thuật/thủ thuật <=30 ngày", "M1", "Nguy cơ nhiễm khuẩn vết mổ/sepsis (RF-33)"),
    FieldSpec("surgical_site_signs", "Vết mổ sưng đỏ/chảy dịch/hở", "C", "Ổ nhiễm khuẩn rõ (RF-33)"),
    FieldSpec("indwelling_device", "Thiết bị lưu trong cơ thể", "M1", "Đường vào nhiễm khuẩn (RF-34)", tri_state=False),
    FieldSpec("recent_wound_or_bite", "Vết thương hở/bỏng/động vật cắn", "O", "Nhiễm khuẩn mô mềm, uốn ván"),
)

# --- Thuốc (KM §3.11) ---------------------------------------------------------------------------
MEDICATION_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("current_medications", "Thuốc đang dùng", "O", "Sốt do thuốc; tương tác an toàn", tri_state=False),
    FieldSpec("nsaid_use", "Đang dùng NSAID/aspirin", "C", "Cảnh báo an toàn bắt buộc trong bối cảnh SXHD (R-G-03)"),
    FieldSpec("anticoagulant_use", "Đang dùng chống đông", "O", "Diễn giải chảy máu khác đi"),
    FieldSpec("antibiotic_current", "Đang dùng kháng sinh", "H", "Sốt dai dẳng dù dùng KS = tín hiệu cần khám"),
    FieldSpec("new_medication_6w", "Thuốc mới trong 6 tuần", "O", "Sốt do thuốc"),
    FieldSpec("drug_allergies", "Dị ứng thuốc", "O", "An toàn cho tuyến sau", tri_state=False),
)

COMMON_FIELDS: tuple[FieldSpec, ...] = (
    DEMOGRAPHIC_FIELDS
    + SAFETY_NETTING_FIELDS
    + GENERAL_FIELDS
    + RESPIRATORY_FIELDS
    + CIRCULATION_FIELDS
    + NEUROLOGICAL_FIELDS
    + SKIN_BLEEDING_FIELDS
    + ASSOCIATED_FIELDS
    + RISK_CONTEXT_FIELDS
    + MEDICATION_FIELDS
)

COMMON_FIELDS_BY_KEY: dict[str, FieldSpec] = {field.key: field for field in COMMON_FIELDS}
