"""Rule đỏ PHỔ QUÁT - đúng với mọi than phiền, không riêng gì sốt.

Chép nguyên văn thân hàm từ `fever_protocol.py` (nguồn: KM §6.1), chỉ đổi tên từ `_r_e_xx` riêng tư
thành hàm PUBLIC để protocol khác dùng lại được. Mã rule (`R-E-xx`) và `reason_codes` (`RF-xx`) giữ
nguyên: chúng là thứ ổn định để log/test/truy vết ngược về tài liệu, đổi mã theo protocol là làm mất
đường truy và làm hỏng mọi test golden đang có.

Ranh giới "phổ quát" ở đây là: rule KHÔNG đọc field nào của riêng một bệnh. Co giật, tím tái, sốc, ban
không mất khi ấn kính, xuất huyết tiêu hoá là dấu hiệu người bệnh đang nguy kịch - đúng như vậy dù họ
than phiền vì sốt, đau ngực hay đau bụng. Ngược lại `R-E-16` (nhiệt độ >= 40°C), `R-V-02` (sốt >= 5
ngày), `R-E-19` (sốt rét) đọc field của protocol sốt nên Ở LẠI `fever_protocol.py`.

THỨ TỰ trong `EMERGENCY_RULES`/`EARLY_VISIT_RULES` là một phần của hợp đồng: `rule_engine.evaluate`
truyền `matches_so_far` theo đúng thứ tự khai báo, và `r_e_21` (sản khoa) cần biết đã có rule EMERGENCY
nào khác khớp chưa. Protocol nào ghép catalog riêng phải giữ rule phụ thuộc ấy đứng SAU.
"""

from __future__ import annotations

from src.services.symptom_protocol.common_safety.predicates import (
    age_in_months,
    array_has_any,
    array_has_non_empty_excluding,
    as_float,
    is_in,
    is_true,
)
from src.services.symptom_protocol.models import RuleMatch

CHRONIC_SEVERE = frozenset({"cardiac", "pulmonary", "renal", "hepatic", "hematologic_thalassemia", "malignancy"})

# Field tri-state "đỏ tuyệt đối" + giá trị enum coi là đỏ. Dùng cho `provisional_emergency_signal`
# (biết khi nào nên dừng hỏi thường quy) và cho việc quét kèm field an toàn ngoài cụm đang hỏi.
EMERGENCY_TRI_STATE_FIELDS: tuple[str, ...] = (
    "seizure_active_now",
    "seizure_occurred",
    "neck_stiffness",
    "focal_neuro_deficit",
    "cyanosis",
    "stridor_or_drooling",
    "cold_clammy_skin",
    "capillary_refill_ge_3s",
    "non_blanching_rash",
    "mucosal_bleeding",
    "gi_bleeding",
)

EMERGENCY_ENUM_MATCHES: dict[str, frozenset[str]] = {
    "consciousness_level": frozenset({"difficult_to_rouse", "unresponsive"}),
    "breathing_difficulty": frozenset({"severe"}),
    "urine_output": frozenset({"none_gt_6h"}),
    "feeding_intake": frozenset({"unable"}),
    "vomiting_severity": frozenset({"unable_to_keep_fluids"}),
    "abdominal_pain_severity": frozenset({"severe"}),
}

# Quét từ khoá nhẹ cho field đỏ hay được người dùng tự mô tả ngay câu đầu, trước khi tới lượt hỏi cụm
# tương ứng. CỐ Ý ngắn - chỉ phủ field có hậu quả bỏ sót cao nhất, không thay thế LLM extraction.
OPPORTUNISTIC_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("seizure_active_now", ("đang co giật", "dang co giat", "co giật ngay", "co giat ngay")),
    ("seizure_occurred", ("co giật", "co giat")),
    ("non_blanching_rash", ("ban tím không mất", "ban tim khong mat", "ấn không mất", "an khong mat")),
    ("cyanosis", ("tím môi", "tim moi", "tím tái", "tim tai")),
    ("neck_stiffness", ("cứng gáy", "cung gay")),
    ("cold_clammy_skin", ("lạnh ẩm", "lanh am", "nổi vân tím", "noi van tim")),
)

# Nhãn tiếng Việt của các `RF-xx` do rule trong file này phát ra (KM §6.1). CHỈ để hiển thị trên phiếu
# bàn giao - không tham gia bất kỳ quyết định nào.
REASON_CODE_LABELS: dict[str, str] = {
    "RF-01": "Giảm ý thức",
    "RF-02": "Đang co giật / vừa co giật",
    "RF-03": "Co giật phức tạp",
    "RF-04": "Dấu hiệu màng não",
    "RF-05": "Lú lẫn mới ở người lớn",
    "RF-06": "Dấu hiệu thần kinh khu trú",
    "RF-07": "Khó thở nặng",
    "RF-08": "Tím tái",
    "RF-09": "Rút lõm lồng ngực / thở rên ở trẻ nhỏ",
    "RF-10": "Thở rít / chảy dãi không nuốt được",
    "RF-11": "SpO2 thấp",
    "RF-12": "Đau ngực / ho ra máu",
    "RF-13": "Dấu hiệu sốc",
    "RF-14": "Không tiểu > 6 giờ",
    "RF-15": "Không ăn uống được / nôn không giữ được nước",
    "RF-16": "Mất nước",
    "RF-17": "Choáng khi đứng dậy",
    "RF-18": "Ban không mất khi ấn kính",
    "RF-19": "Chảy máu niêm mạc",
    "RF-20": "Xuất huyết tiêu hoá",
    "RF-21": "Vàng da mới",
    "RF-31": "Suy giảm miễn dịch",
    "RF-32": "Thai kỳ / hậu sản",
    "RF-33": "Phẫu thuật gần đây",
    "RF-34": "Thiết bị lưu trong cơ thể",
    "RF-36": "Bệnh mạn tính nặng",
    "RF-37": "Người rất cao tuổi",
    "RF-38": "Không có người theo dõi tại nhà",
    "RF-39": "Đau bụng dữ dội / bụng cứng",
    "RF-40": "Nôn nhiều",
    "RF-41": "Sưng đau khớp / không đi lại được",
    "RF-43": "Ổ nhiễm khuẩn khu trú",
    "RF-44": "Người nhà rất lo lắng / trông rất mệt",
}


def has_emergency_signal(answers: dict[str, object]) -> bool:
    """Quét RẤT NHẸ field đỏ tuyệt đối - chỉ để biết khi nào nên dừng hỏi thường quy. Không sinh
    `reason_codes`/`triggered_rules` chính thức (đó là việc của `rule_engine.evaluate`)."""
    if any(is_true(answers.get(key)) for key in EMERGENCY_TRI_STATE_FIELDS):
        return True
    return any(answers.get(key) in matches for key, matches in EMERGENCY_ENUM_MATCHES.items())


# --- EMERGENCY ---------------------------------------------------------------------------------


def r_e_01(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if is_in(a.get("consciousness_level"), frozenset({"difficult_to_rouse", "unresponsive"})):
        return RuleMatch("R-E-01", ("RF-01",), "EMERGENCY", "now")
    return None


def r_e_02(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    complex_features = array_has_any(
        a.get("seizure_features"), frozenset({"focal", "duration_gt_5min", "recurrent_24h", "incomplete_recovery"})
    )
    if is_true(a.get("seizure_occurred")) or is_true(a.get("seizure_active_now")) or complex_features:
        codes = ["RF-02"]
        if complex_features:
            codes.append("RF-03")
        return RuleMatch("R-E-02", tuple(codes), "EMERGENCY", "now")
    return None


def r_e_03(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if is_true(a.get("neck_stiffness")) or is_true(a.get("bulging_fontanelle")) or is_true(a.get("photophobia")):
        return RuleMatch("R-E-03", ("RF-04",), "EMERGENCY", "now")
    return None


def r_e_04(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    age_months = age_in_months(a)
    if is_true(a.get("new_confusion")) and age_months is not None and age_months >= 16 * 12:
        return RuleMatch("R-E-04", ("RF-05",), "EMERGENCY", "now")
    return None


def r_e_05(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if is_true(a.get("focal_neuro_deficit")):
        return RuleMatch("R-E-05", ("RF-06",), "EMERGENCY", "now")
    return None


def r_e_06(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if a.get("breathing_difficulty") == "severe" or is_true(a.get("cyanosis")) or is_true(a.get("stridor_or_drooling")):
        codes = []
        if a.get("breathing_difficulty") == "severe":
            codes.append("RF-07")
        if is_true(a.get("cyanosis")):
            codes.append("RF-08")
        if is_true(a.get("stridor_or_drooling")):
            codes.append("RF-10")
        return RuleMatch("R-E-06", tuple(codes), "EMERGENCY", "now")
    return None


def r_e_07(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    age_months = age_in_months(a)
    young = age_months is not None and age_months < 5 * 12
    if young and (is_true(a.get("chest_indrawing")) or is_true(a.get("nasal_flaring_grunting"))):
        return RuleMatch("R-E-07", ("RF-09",), "EMERGENCY", "now")
    return None


def r_e_08(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    spo2 = as_float(a.get("spo2_percent"))
    if spo2 is not None and spo2 <= 92:
        return RuleMatch("R-E-08", ("RF-11",), "EMERGENCY", "now")
    return None


def r_e_09(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if is_true(a.get("cold_clammy_skin")) or is_true(a.get("capillary_refill_ge_3s")):
        return RuleMatch("R-E-09", ("RF-13",), "EMERGENCY", "now")
    return None


def r_e_10(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if a.get("urine_output") == "none_gt_6h":
        return RuleMatch("R-E-10", ("RF-14",), "EMERGENCY", "now")
    return None


def r_e_11(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if a.get("feeding_intake") == "unable" or a.get("vomiting_severity") == "unable_to_keep_fluids":
        return RuleMatch("R-E-11", ("RF-15",), "EMERGENCY", "now")
    return None


def r_e_12(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if is_true(a.get("non_blanching_rash")):
        return RuleMatch("R-E-12", ("RF-18",), "EMERGENCY", "now")
    return None


def r_e_13(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if is_true(a.get("mucosal_bleeding")) or is_true(a.get("gi_bleeding")):
        codes = []
        if is_true(a.get("mucosal_bleeding")):
            codes.append("RF-19")
        if is_true(a.get("gi_bleeding")):
            codes.append("RF-20")
        return RuleMatch("R-E-13", tuple(codes), "EMERGENCY", "now")
    return None


def r_e_20(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if a.get("abdominal_pain_severity") == "severe" or is_true(a.get("abdominal_guarding")):
        return RuleMatch("R-E-20", ("RF-39",), "EMERGENCY", "now")
    return None


def r_e_21(a: dict[str, object], matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    """PHỤ THUỘC THỨ TỰ: cần biết đã có rule EMERGENCY nào khác khớp chưa, nên phải đứng SAU chúng."""
    if not (is_true(a.get("is_pregnant")) or is_true(a.get("postpartum_6w"))):
        return None
    flags = a.get("obstetric_red_flags")
    has_flags = isinstance(flags, (list, tuple)) and len(flags) > 0
    other_emergency_matched = any(m.level == "EMERGENCY" for m in matches)
    if has_flags or other_emergency_matched:
        return RuleMatch("R-E-21", ("RF-32",), "EMERGENCY", "now")
    return None


# --- EARLY_VISIT -------------------------------------------------------------------------------


def r_v_05(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    spo2 = as_float(a.get("spo2_percent"))
    spo2_band = spo2 is not None and 93 <= spo2 <= 95
    if spo2_band or is_true(a.get("rapid_breathing")):
        return RuleMatch("R-V-05", ("RF-11",), "EARLY_VISIT", "within_4h")
    return None


def r_v_06(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    signs = a.get("dehydration_signs")
    many_signs = isinstance(signs, (list, tuple)) and len(signs) >= 2
    reduced_combo = a.get("urine_output") == "reduced" and a.get("feeding_intake") == "reduced"
    if many_signs or reduced_combo:
        return RuleMatch("R-V-06", ("RF-16",), "EARLY_VISIT", "within_4h")
    return None


def r_v_07(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if is_true(a.get("dizziness_on_standing")):
        return RuleMatch("R-V-07", ("RF-17",), "EARLY_VISIT", "within_24h")
    return None


def r_v_08(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if is_true(a.get("jaundice_new")):
        return RuleMatch("R-V-08", ("RF-21",), "EARLY_VISIT", "within_24h")
    return None


def r_v_09(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if is_true(a.get("immunocompromised")) and not is_true(a.get("known_neutropenia")):
        return RuleMatch("R-V-09", ("RF-31",), "EARLY_VISIT", "within_4h")
    return None


def r_v_10(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if is_true(a.get("is_pregnant")) or is_true(a.get("postpartum_6w")):
        return RuleMatch("R-V-10", ("RF-32",), "EARLY_VISIT", "within_4h")
    return None


def r_v_11(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    device = a.get("indwelling_device")
    has_device = isinstance(device, (list, tuple)) and array_has_non_empty_excluding(device, frozenset({"none"}))
    if is_true(a.get("recent_surgery_30d")) or has_device:
        codes = []
        if is_true(a.get("recent_surgery_30d")):
            codes.append("RF-33")
        if has_device:
            codes.append("RF-34")
        return RuleMatch("R-V-11", tuple(codes), "EARLY_VISIT", "within_24h")
    return None


def r_v_12(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if array_has_any(a.get("chronic_conditions"), CHRONIC_SEVERE):
        return RuleMatch("R-V-12", ("RF-36",), "EARLY_VISIT", "within_24h")
    return None


def r_v_13(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    age_months = age_in_months(a)
    if age_months is not None and age_months >= 75 * 12:
        return RuleMatch("R-V-13", ("RF-37",), "EARLY_VISIT", "within_24h")
    return None


def r_v_14(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if a.get("vomiting_severity") == "frequent":
        return RuleMatch("R-V-14", ("RF-40",), "EARLY_VISIT", "within_4h")
    return None


def r_v_15(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if is_true(a.get("joint_limb_swelling")) or is_true(a.get("non_weight_bearing")):
        return RuleMatch("R-V-15", ("RF-41",), "EARLY_VISIT", "within_24h")
    return None


def r_v_17(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if is_true(a.get("localized_infection_signs")):
        return RuleMatch("R-V-17", ("RF-43",), "EARLY_VISIT", "within_24h")
    return None


def r_v_18(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    concern = as_float(a.get("caregiver_concern_level"))
    high_concern = concern is not None and concern >= 8
    if high_concern or is_true(a.get("looks_very_unwell")):
        return RuleMatch("R-V-18", ("RF-44",), "EARLY_VISIT", "within_4h")
    return None


def r_v_19(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if is_true(a.get("chest_pain")) or is_true(a.get("hemoptysis")):
        return RuleMatch("R-V-19", ("RF-12",), "EARLY_VISIT", "within_4h")
    return None


def r_g_01(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if is_true(a.get("lives_alone")) or a.get("caregiver_available") == "false":
        return RuleMatch("R-G-01", ("RF-38",), "EARLY_VISIT", "within_24h")
    return None


def default_early_visit_rule(_a: dict[str, object]) -> RuleMatch:
    """Kết luận khi KHÔNG rule nào khớp và checklist tự chăm sóc chưa thoả.

    R-G-02(a) + CS Part 6 "Dừng hẳn" (c): không bao giờ mặc định về SELF_CARE. Mơ hồ giữa hai mức thì
    luôn chọn mức thận trọng hơn (P0-6) - "chưa tìm thấy dấu hiệu nguy hiểm" KHÔNG đồng nghĩa với "an
    toàn", nhất là với protocol chỉ quét được tập dấu hiệu phổ quát."""
    return RuleMatch("R-G-02", (), "EARLY_VISIT", "within_24h")


BASELINE_SELF_CARE_MAX_SEVERITY = 4.0
"""Trần mức khó chịu (thang 0-10) còn được phép kết luận "tự theo dõi" khi KHÔNG có protocol chuyên
biệt. Cố ý thấp: đây là ngưỡng cho một protocol chỉ quét được dấu hiệu PHỔ QUÁT, không biết gì về
nguyên nhân của than phiền cụ thể. 5-10 điểm là mức người bệnh tự thấy đáng lo - với hiểu biết ở mức
này, câu trả lời đúng là để điều dưỡng xem."""


def baseline_self_care_satisfied(answers: dict[str, object]) -> bool:
    """Checklist "tự theo dõi" chỉ dùng field PHỔ QUÁT - không đọc field của bệnh nào cả.

    Dành cho protocol không có tài liệu lâm sàng riêng (`generic`). Nó KHẮT KHE HƠN checklist của
    fever một cách có chủ ý, và đây là chỗ mang phán đoán an toàn nên đọc kỹ trước khi nới:

    - fever biết mình đang nói về bệnh gì nên đọc được các dấu hiệu đặc thù (thời gian sốt, đáp ứng
      hạ sốt). Protocol phổ quát không có gì tương đương, nên phải bù bằng những điều kiện chặt hơn:
      KHÔNG có bối cảnh nguy cơ nào, và mức khó chịu phải thấp.
    - Mọi field còn `unknown` đều làm hàm trả `False`. Đây là điểm khác biệt quan trọng nhất so với
      "không tìm thấy dấu hiệu nguy hiểm": chưa hỏi KHÔNG phải là an toàn (P0-6).

    Trước đây `generic` không bao giờ kết luận được mức nhẹ nhất (`never_self_care`), nên MỌI than
    phiền ngoài sốt đều vào hàng đợi điều dưỡng ở mức "Khám sớm" - kể cả một vết xước tay. Ràng buộc
    HITL không đổi: kết quả vẫn là ĐỀ XUẤT và vẫn cần điều dưỡng duyệt.
    """
    if has_emergency_signal(answers):
        return False
    if answers.get("consciousness_level") != "alert":
        return False
    if answers.get("feeding_intake") not in ("normal", "reduced"):
        return False
    if answers.get("urine_output") != "normal":
        return False
    if answers.get("complaint_progression") not in ("better", "same"):
        return False

    severity = as_float(answers.get("complaint_severity"))
    if severity is None or severity > BASELINE_SELF_CARE_MAX_SEVERITY:
        return False

    if _has_any_risk_context(answers) or not _risk_context_is_answered(answers):
        return False

    age_months = age_in_months(answers)
    if age_months is None or age_months < 6:
        return False
    self_sufficient_adult = age_months >= 16 * 12 and answers.get("reporter_type") == "self"
    if not (is_true(answers.get("caregiver_available")) or self_sufficient_adult):
        return False
    return bool(is_true(answers.get("can_return_for_followup")))


RISK_CONTEXT_FIELDS: tuple[str, ...] = (
    "is_pregnant", "postpartum_6w", "immunocompromised", "recent_surgery_30d", "chronic_conditions",
)


def _risk_context_is_answered(a: dict[str, object]) -> bool:
    """Mọi field bối cảnh nguy cơ phải CÓ câu trả lời xác định.

    `_has_any_risk_context` một mình không đủ: nó chỉ hỏi "có dương tính nào không", nên một hồ sơ
    chưa từng hỏi tới thai sản cũng trả `False` và lọt qua như thể đã loại trừ. Với protocol phổ quát
    - vốn không biết gì về nguyên nhân than phiền - bối cảnh nguy cơ là thứ duy nhất còn phân biệt
    được "nhẹ" với "nhẹ bề ngoài", nên nó phải được HỎI chứ không được suy ra từ im lặng."""
    return all(a.get(key) not in (None, "", "unknown") for key in RISK_CONTEXT_FIELDS)


def _has_any_risk_context(a: dict[str, object]) -> bool:
    """Bối cảnh nguy cơ phổ quát. `unknown` KHÔNG tính là "không có" - nó chỉ chặn `self_care` qua
    việc các field này còn trống, không tự nâng mức (nâng mức là việc của `EARLY_VISIT_RULES`)."""
    age_months = age_in_months(a)
    if age_months is not None and (age_months < 3 or age_months >= 75 * 12):
        return True
    return (
        is_true(a.get("immunocompromised"))
        or is_true(a.get("is_pregnant"))
        or is_true(a.get("postpartum_6w"))
        or is_true(a.get("recent_surgery_30d"))
        or array_has_any(a.get("chronic_conditions"), CHRONIC_SEVERE)
    )


EMERGENCY_RULES: tuple = (
    r_e_01, r_e_02, r_e_03, r_e_04, r_e_05, r_e_06, r_e_07, r_e_08, r_e_09, r_e_10,
    r_e_11, r_e_12, r_e_13, r_e_20,
)
"""KHÔNG gồm `r_e_21` - rule đó phụ thuộc thứ tự và phải đứng sau MỌI rule EMERGENCY khác, kể cả rule
đặc thù bệnh mà protocol tự thêm vào. Protocol ghép catalog phải tự đặt nó đúng chỗ."""

EARLY_VISIT_RULES: tuple = (
    r_v_05, r_v_06, r_v_07, r_v_08, r_v_09, r_v_10, r_v_11, r_v_12, r_v_13, r_v_14, r_v_15,
    r_v_17, r_v_18, r_v_19,
)
