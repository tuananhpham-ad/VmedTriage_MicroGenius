"""Deterministic red-flag phrases for the public triage safety layer.

These are escalation triggers, not diagnoses.  A match only produces the fixed
"call 115 / go to the nearest emergency facility" message; it never generates
treatment advice.  Phrases are intentionally specific to reduce false positives.

Clinical-review sources used for the rule groups:
- WHO IMCI general danger signs (children): https://platform.who.int/docs/default-source/mca-documents/policy-documents/operational-guidance/TLS-CH-23-01-OPERATIONAL-GUIDANCE-2015-eng-Integrated-Management-of-Childhood-Illness.pdf
- CDC stroke warning signs: https://www.cdc.gov/stroke/signs-symptoms/
- NHS emergency, anaphylaxis and poisoning guidance: https://www.nhs.uk/nhs-services/urgent-and-emergency-care-services/when-to-call-999/
- CDC urgent maternal warning signs: https://www.cdc.gov/hearher/

Rules require clinical governance review before a production deployment.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TextRedFlagRule:
    code: str
    label: str
    phrases: tuple[str, ...]


def rule(code: str, label: str, *phrases: str) -> TextRedFlagRule:
    return TextRedFlagRule(code=code, label=label, phrases=phrases)


# 100 deliberately narrow, patient-facing escalation rules.  Each line is one
# independently auditable rule; phrases cover Vietnamese with/without diacritics
# through ``normalize_red_flag_text`` below.
TEXT_RED_FLAG_RULES: tuple[TextRedFlagRule, ...] = (
    # Consciousness, seizure and acute neurologic change (1-10)
    rule("loss_of_consciousness", "Mất ý thức", "bất tỉnh", "mất ý thức", "hôn mê"),
    rule("cannot_be_woken", "Không đánh thức được", "gọi không dậy", "không đánh thức được", "không gọi dậy"),
    rule("collapse", "Đột ngột ngã quỵ/ngất", "ngã quỵ", "ngất xỉu", "ngất đi"),
    rule("seizure", "Co giật", "co giật", "lên cơn giật", "giật kinh phong"),
    rule("ongoing_seizure", "Co giật kéo dài hoặc tái diễn", "co giật liên tục", "co giật không dừng", "co giật nhiều lần"),
    rule("sudden_confusion", "Lú lẫn đột ngột", "lú lẫn đột ngột", "đột nhiên không biết mình ở đâu", "đột nhiên nói sảng"),
    rule("thunderclap_headache", "Đau đầu dữ dội đột ngột", "đau đầu dữ dội đột ngột", "đau đầu như búa bổ", "đau đầu tệ nhất từ trước đến nay"),
    rule("sudden_one_sided_weakness", "Yếu/liệt một bên đột ngột", "yếu một bên người", "liệt nửa người", "tê một bên người"),
    rule("sudden_speech_change", "Rối loạn nói đột ngột", "nói ngọng đột ngột", "không nói được đột ngột", "khó nói đột ngột"),
    rule("sudden_vision_loss", "Mất thị lực đột ngột", "mờ mắt đột ngột", "không nhìn thấy đột ngột", "mất thị lực một bên"),
    # Airway and breathing (11-20)
    rule("not_breathing", "Ngừng thở", "không thở", "ngừng thở", "thở không được"),
    rule("gasping", "Thở ngáp cá", "thở ngáp", "thở hổn hển", "thở từng cơn"),
    rule("severe_breathing", "Khó thở nặng", "khó thở nặng", "không đủ hơi để nói", "khó thở đến không nói được"),
    rule("cyanosis", "Môi hoặc da tím tái", "môi tím", "tím tái", "da xanh tím"),
    rule("choking", "Nghẹn/tắc đường thở", "bị nghẹn", "hóc dị vật", "kẹt dị vật trong cổ"),
    rule("throat_swelling", "Sưng họng cấp", "sưng họng", "cổ họng sưng", "nghẹn cổ họng sau dị ứng"),
    rule("tongue_swelling", "Sưng lưỡi cấp", "sưng lưỡi", "lưỡi phù", "lưỡi to nhanh"),
    rule("stridor", "Thở rít cấp", "thở rít", "tiếng thở rít", "hít vào rít"),
    rule("severe_asthma", "Cơn hen nặng không đáp ứng", "hen không đỡ", "xịt hen không đỡ", "cơn hen nặng"),
    rule("coughing_blood", "Ho ra máu", "ho ra máu", "khạc ra máu", "đờm có nhiều máu"),
    # Cardiac and circulation (21-30)
    rule("severe_chest_pain", "Đau ngực dữ dội", "đau ngực dữ dội", "đau thắt ngực", "bóp nghẹt ngực"),
    rule("chest_pain_radiating", "Đau ngực lan", "đau ngực lan tay", "đau ngực lan hàm", "đau ngực lan lưng"),
    rule("chest_pain_sweating", "Đau ngực kèm vã mồ hôi", "đau ngực vã mồ hôi", "đau ngực toát mồ hôi", "đau ngực mồ hôi lạnh"),
    rule("chest_pain_fainting", "Đau ngực kèm ngất", "đau ngực rồi ngất", "đau ngực kèm choáng", "đau ngực muốn ngất"),
    rule("chest_pain_breathlessness", "Đau ngực kèm khó thở", "đau ngực khó thở", "đau ngực và hụt hơi", "đau ngực kèm thở gấp"),
    rule("palpitations_chest_pain", "Hồi hộp kèm đau ngực", "tim đập loạn xạ kèm đau ngực", "tim đập nhanh đau ngực", "đánh trống ngực đau ngực"),
    rule("cold_clammy_collapse", "Lạnh ẩm kèm choáng/ngất", "mồ hôi lạnh ngất", "lạnh toát người choáng", "vã mồ hôi lạnh sắp ngất"),
    rule("cardiac_arrest_report", "Nghi ngừng tim", "tim ngừng đập", "không bắt được mạch", "đột tử"),
    rule("shock_like", "Dấu hiệu sốc", "choáng không đứng được", "lả đi mạch yếu", "tay chân lạnh vã mồ hôi"),
    rule("severe_rest_dyspnea", "Khó thở dữ dội khi nghỉ", "ngồi yên cũng khó thở", "nằm xuống không thở được", "khó thở khi nghỉ"),
    # Major bleeding and gastrointestinal emergencies (31-40)
    rule("heavy_bleeding", "Chảy máu nhiều không cầm", "máu không cầm", "chảy máu nhiều", "máu phun thành tia"),
    rule("uncontrolled_wound_bleeding", "Vết thương chảy máu không kiểm soát", "vết thương máu chảy ồ ạt", "đứt tay máu không cầm", "máu chảy thành dòng"),
    rule("vomiting_blood", "Nôn ra máu", "nôn ra máu", "ói ra máu", "nôn chất như bã cà phê"),
    rule("black_tarry_stool", "Đi ngoài phân đen", "phân đen như hắc ín", "đi cầu phân đen", "đi ngoài phân đen"),
    rule("bloody_stool_fainting", "Đi ngoài ra máu kèm choáng", "đi ngoài ra máu rồi choáng", "đại tiện ra máu ngất", "ra máu hậu môn nhiều"),
    rule("severe_abdominal_rigidity", "Đau bụng dữ dội kèm bụng cứng", "bụng cứng như gỗ", "đau bụng dữ dội bụng cứng", "đau bụng không chịu nổi"),
    rule("severe_abdominal_with_faint", "Đau bụng dữ dội kèm ngất", "đau bụng rồi ngất", "đau bụng choáng váng", "đau bụng vã mồ hôi lạnh"),
    rule("persistent_vomiting_dehydration", "Nôn liên tục không giữ được nước", "uống vào nôn hết", "nôn tất cả", "nôn liên tục không uống được"),
    rule("severe_dehydration", "Dấu hiệu mất nước nặng", "không tiểu cả ngày", "mắt trũng không uống được", "khát lả không uống được"),
    rule("severe_testicular_pain", "Đau tinh hoàn dữ dội đột ngột", "đau tinh hoàn đột ngột", "sưng đau tinh hoàn dữ dội", "xoắn tinh hoàn"),
    # Pregnancy and postpartum emergencies (41-50)
    rule("pregnancy_heavy_bleeding", "Ra máu nhiều khi mang thai", "mang thai ra máu nhiều", "bầu ra máu ồ ạt", "thai kỳ chảy máu nhiều"),
    rule("pregnancy_severe_abdominal_pain", "Đau bụng dữ dội khi mang thai", "mang thai đau bụng dữ dội", "bầu đau bụng một bên dữ dội", "thai ngoài tử cung"),
    rule("pregnancy_seizure", "Co giật khi mang thai/sau sinh", "mang thai co giật", "bầu co giật", "sau sinh co giật"),
    rule("pregnancy_severe_headache", "Đau đầu dữ dội khi mang thai", "bầu đau đầu dữ dội", "mang thai đau đầu không hết", "sau sinh đau đầu dữ dội"),
    rule("pregnancy_vision_change", "Rối loạn nhìn khi mang thai", "mang thai nhìn mờ", "bầu chớp sáng mắt", "bầu mờ mắt đột ngột"),
    rule("pregnancy_breathing_chest", "Khó thở/đau ngực khi mang thai", "mang thai khó thở nặng", "bầu đau ngực", "sau sinh khó thở"),
    rule("pregnancy_face_hand_swelling", "Phù mặt/tay đột ngột khi mang thai", "bầu sưng mặt tay", "mang thai phù mặt", "phù tay chân đột ngột khi bầu"),
    rule("pregnancy_fluid_leak", "Ra nước ối hoặc dịch nhiều", "vỡ ối", "rỉ nước ối", "ra nước nhiều từ âm đạo"),
    rule("postpartum_heavy_bleeding", "Băng huyết sau sinh", "sau sinh ra máu nhiều", "đẻ xong chảy máu ồ ạt", "băng huyết"),
    rule("reduced_fetal_movement", "Thai giảm hoặc không cử động", "thai không máy", "em bé không đạp", "thai giảm cử động rõ"),
    # Poisoning, overdose, violence and mental-health emergency (51-60)
    rule("poison_ingestion", "Nuốt phải chất độc", "uống nhầm thuốc tẩy", "nuốt hóa chất", "uống phải chất độc"),
    rule("medication_overdose", "Quá liều thuốc", "uống quá liều", "uống nhiều viên thuốc", "dùng thuốc quá liều"),
    rule("carbon_monoxide_exposure", "Nghi ngộ độc khí", "ngộ độc khí than", "hít phải khí độc", "ngửi thấy mùi khí rồi choáng"),
    rule("alcohol_poisoning", "Nghi ngộ độc rượu", "uống rượu rồi bất tỉnh", "say rượu không tỉnh", "uống rượu nôn li bì"),
    rule("drug_overdose", "Quá liều ma túy", "sốc ma túy", "dùng ma túy rồi lịm", "tiêm thuốc rồi khó thở"),
    rule("self_harm_imminent", "Nguy cơ tự làm hại bản thân tức thì", "muốn tự tử", "sẽ tự tử", "đang tự làm hại mình"),
    rule("violent_injury", "Bị bạo hành/chấn thương nghiêm trọng", "bị đánh đến chảy máu", "bị bóp cổ", "bị đâm"),
    rule("sexual_assault_now", "Xâm hại tình dục đang/ vừa xảy ra", "bị cưỡng hiếp", "bị hiếp dâm", "bị xâm hại tình dục"),
    rule("snakebite", "Rắn hoặc động vật độc cắn", "bị rắn cắn", "bị rết cắn rồi khó thở", "bị bọ cạp đốt rồi choáng"),
    rule("chemical_eye_exposure", "Hóa chất bắn vào mắt", "hóa chất vào mắt", "axit bắn vào mắt", "kiềm bắn vào mắt"),
    # Trauma, burns and environmental injury (61-70)
    rule("major_road_traffic_trauma", "Chấn thương giao thông nặng", "tai nạn giao thông chảy máu", "bị xe tông", "va chạm mạnh rồi đau không cử động"),
    rule("fall_from_height", "Ngã từ trên cao", "ngã từ tầng", "rơi từ trên cao", "té từ trên mái"),
    rule("head_injury_with_red_flag", "Chấn thương đầu nguy hiểm", "đập đầu rồi bất tỉnh", "chấn thương đầu nôn liên tục", "đầu va mạnh rồi lơ mơ"),
    rule("penetrating_injury", "Vết thương xuyên thấu", "dao đâm", "vết thương sâu lòi xương", "bị đâm xuyên"),
    rule("open_fracture", "Gãy xương hở", "xương lòi ra", "gãy xương hở", "biến dạng chân tay chảy máu"),
    rule("severe_burn", "Bỏng nặng", "bỏng toàn thân", "bỏng cháy da rộng", "bỏng điện nặng"),
    rule("electrical_injury", "Điện giật", "bị điện giật", "điện giật rồi ngất", "điện giật rồi khó thở"),
    rule("drowning", "Đuối nước", "bị đuối nước", "sặc nước rồi không thở", "suýt chết đuối"),
    rule("heatstroke", "Nghi sốc nhiệt", "say nóng lịm đi", "phơi nắng rồi ngất", "sốt cao sau nắng lơ mơ"),
    rule("hypothermia", "Hạ thân nhiệt nặng", "lạnh run không nói được", "nhiễm lạnh lơ mơ", "ngâm nước lạnh rồi lịm"),
    # Pediatric danger signs (71-80)
    rule("child_unable_to_drink", "Trẻ không uống/bú được", "trẻ không bú được", "bé không uống được", "em bé bỏ bú hoàn toàn"),
    rule("child_vomits_everything", "Trẻ nôn tất cả", "bé uống gì cũng nôn", "trẻ nôn hết mọi thứ", "em bé nôn liên tục không giữ được"),
    rule("child_lethargic", "Trẻ li bì/không đáp ứng", "bé li bì", "trẻ gọi không đáp ứng", "em bé khó đánh thức"),
    rule("child_convulsion", "Trẻ co giật", "bé co giật", "trẻ lên cơn giật", "em bé giật"),
    rule("child_chest_indrawing", "Trẻ rút lõm lồng ngực", "bé rút lõm ngực", "trẻ thở lõm ngực", "em bé thở co kéo"),
    rule("child_blue_lips", "Trẻ tím tái", "bé tím môi", "trẻ da tím", "em bé tím tái"),
    rule("child_stridor_calm", "Trẻ thở rít khi yên", "bé thở rít", "trẻ thở rít khi nằm yên", "em bé hít vào rít"),
    rule("child_severe_dehydration", "Trẻ mất nước nặng", "bé mắt trũng không uống được", "trẻ khát lả li bì", "em bé tiêu chảy không tiểu"),
    rule("child_nonblanching_rash", "Trẻ sốt kèm ban xuất huyết", "bé sốt nổi chấm tím", "trẻ sốt phát ban tím", "ban không mất khi ấn"),
    rule("infant_fever_young", "Sốt ở trẻ rất nhỏ", "bé dưới 3 tháng sốt", "trẻ sơ sinh sốt", "em bé mới sinh bị sốt"),
    # Other time-critical presentations (81-90)
    rule("meningitis_pattern", "Sốt kèm cứng cổ/lú lẫn", "sốt cứng cổ", "sốt đau đầu lơ mơ", "sốt kèm ban tím và cứng cổ"),
    rule("sepsis_pattern", "Nghi nhiễm trùng nặng", "sốt run rét lơ mơ", "sốt cao kèm tụt huyết áp", "sốt kèm tay chân lạnh lả đi"),
    rule("diabetic_emergency", "Nghi biến chứng đái tháo đường cấp", "đường huyết rất cao lơ mơ", "tiểu đường rồi thở nhanh sâu", "tiểu đường rồi bất tỉnh"),
    rule("hypoglycemia_pattern", "Nghi hạ đường huyết nặng", "đường huyết thấp lơ mơ", "hạ đường huyết co giật", "tiểu đường run vã mồ hôi không tỉnh"),
    rule("acute_paralysis", "Yếu liệt tiến triển nhanh", "liệt tăng nhanh", "yếu chân tay tăng dần", "không cử động được tay chân"),
    rule("acute_back_neuro", "Đau lưng kèm mất kiểm soát tiểu tiện", "đau lưng bí tiểu", "đau lưng tê vùng yên ngựa", "đau lưng yếu hai chân"),
    rule("sudden_hearing_balance_neuro", "Chóng mặt kèm dấu thần kinh cấp", "chóng mặt không đi được", "choáng váng kèm nói ngọng", "mất thăng bằng đột ngột"),
    rule("severe_eye_pain_vision_loss", "Đau mắt dữ dội kèm giảm thị lực", "đau mắt dữ dội mờ mắt", "mắt đỏ đau không nhìn rõ", "mất thị lực kèm đau mắt"),
    rule("severe_allergic_reaction", "Phản ứng dị ứng nặng", "dị ứng nổi mề đay khó thở", "ăn xong sưng môi khó thở", "bị ong đốt rồi khó thở"),
    rule("rapid_face_swelling", "Sưng mặt nhanh kèm nguy cơ đường thở", "mặt sưng nhanh", "môi sưng nhanh", "phù mặt khó thở"),
    # Acute genitourinary, musculoskeletal and infection patterns (91-100)
    rule("urinary_retention_severe_pain", "Bí tiểu cấp kèm đau nhiều", "không tiểu được đau bụng", "bí tiểu căng tức", "đau bụng dưới không đi tiểu được"),
    rule("flank_pain_fever", "Đau hông lưng kèm sốt/lơ mơ", "đau hông sốt cao", "đau lưng sốt run", "đau thận sốt lả"),
    rule("rapidly_spreading_skin_infection", "Sưng đỏ lan nhanh kèm toàn trạng xấu", "vết đỏ lan nhanh sốt", "da sưng nóng lan nhanh", "vết thương sưng đỏ lả đi"),
    rule("severe_neck_swelling", "Sưng cổ nhanh", "cổ sưng nhanh khó thở", "áp xe cổ khó thở", "sưng cổ nuốt khó"),
    rule("severe_swallowing_difficulty", "Không nuốt được nước bọt", "nuốt nước bọt không được", "chảy dãi không nuốt được", "nuốt nghẹn kèm khó thở"),
    rule("acute_limb_ischemia", "Chi đột ngột lạnh/tái đau", "chân lạnh tái đau", "tay lạnh tím đau đột ngột", "một chân đột ngột không có mạch"),
    rule("pulmonary_embolism_pattern", "Khó thở/đau ngực đột ngột", "khó thở đột ngột đau ngực", "đau ngực khi hít sâu khó thở", "đột ngột hụt hơi đau ngực"),
    rule("severe_all_body_weakness", "Yếu toàn thân đột ngột không đứng được", "đột ngột không đứng dậy được", "yếu rũ toàn thân", "mất sức không cử động được"),
    rule("postoperative_emergency", "Biến chứng nặng sau phẫu thuật", "mổ xong khó thở", "sau mổ chảy máu nhiều", "sau mổ lơ mơ"),
    rule("dialysis_emergency", "Triệu chứng nặng ở người lọc máu", "lọc máu rồi khó thở", "chạy thận rồi đau ngực", "bệnh thận rồi lơ mơ"),
)


def normalize_red_flag_text(text: str) -> str:
    lowered = (text or "").casefold().replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", lowered)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", without_marks).strip()


def detect_text_red_flags(*texts: str) -> list[tuple[TextRedFlagRule, str]]:
    """Return every matching text rule and its first matching phrase."""
    haystack = normalize_red_flag_text(" ".join(text for text in texts if text))
    findings: list[tuple[TextRedFlagRule, str]] = []
    for text_rule in TEXT_RED_FLAG_RULES:
        matched = next(
            (phrase for phrase in text_rule.phrases if normalize_red_flag_text(phrase) in haystack),
            None,
        )
        if matched:
            findings.append((text_rule, matched))
    return findings
