"""Nội dung fever (field/cụm/rule/route/checklist) đăng ký vào engine chung `symptom_protocol/`.

Đây là "bản data" của fever sau khi tách cơ chế ra dùng chung (xem
`_guidance/fever-detect-agent-task.md`, mục "kế thừa được"). File này chứa:

- Rule catalog `R-E-xx`/`R-V-xx`/`R-G-01` (KM §6.1) - ánh xạ `RF-xx` sang mức triage.
- Các hook lâm sàng: `determine_route` (CS §4.3), `has_provisional_emergency_signal` (Part 1.3),
  `self_care_checklist_satisfied` (KM §5.4), `budget_key` (CS §6.5), `skip_rule` (CS Part 3 - điều
  kiện "Ask condition" khác "luôn hỏi").
- `FEVER_PROTOCOL`: gói tất cả lại thành 1 `SymptomProtocol`, dùng bởi
  `fever_stage_machine.py`/`fever_red_flag_engine.py`/`fever_intake_agent.py`/`fever_session.py`
  (các file đó giờ chỉ là lớp mỏng gọi vào engine chung với `FEVER_PROTOCOL`).

KHÔNG import LLM/provider_router ở đây - mọi hàm trong file này THUẦN rule-based.
"""

from __future__ import annotations

from typing import Literal

from src.services.checklists.fever_checklist import FIELDS_BY_KEY, QUESTION_CLUSTERS
from src.services.symptom_protocol.models import QuestionCluster, RuleMatch
from src.services.symptom_protocol.protocol import SymptomProtocol

Route = Literal[
    "ROUTE_INFANT_HIGH",
    "ROUTE_HIGH_RISK",
    "ROUTE_STANDARD",
    "ROUTE_DENGUE_CONTEXT",
    "ROUTE_LOCALIZED_SOURCE",
]

STAGE_ORDER: tuple[str, ...] = ("0", "1", "2", "3A", "3B", "4", "5")
GATE_STAGES: tuple[str, str] = ("3A", "3B")
BUDGET_FLOOR_STAGE = "5"

# CS §6.5 - ngân sách câu hỏi tính theo CỤM (không phải field đơn lẻ), khoá theo route/kết luận.
# ROUTE_DENGUE_CONTEXT không có hàng riêng trong §6.5 - tài liệu mô tả nó "đào sâu" bộ câu hỏi trước
# khi kết luận, nên dùng chung ngân sách với nhóm ứng viên SELF_CARE (12-16) [EN - suy luận hợp lý từ
# §4.3/§6.5, không có con số riêng trong tài liệu nguồn].
BUDGET: dict[str, tuple[int, int]] = {
    "ROUTE_INFANT_HIGH": (3, 6),
    "EMERGENCY": (3, 6),
    "EARLY_VISIT": (8, 12),
    "ROUTE_HIGH_RISK": (8, 12),
    "SELF_CARE_CANDIDATE": (12, 16),
    "ROUTE_DENGUE_CONTEXT": (12, 16),
}

# Field M0 "đỏ tuyệt đối" dùng cho provisional scan (should_stop) VÀ cho hướng E quét field an toàn
# ngoài cụm hiện tại (`intake_agent._run_turn_combined`). Value coi là dương tính: chuỗi tri-state
# "true", hoặc enum/giá trị cụ thể liệt kê trong `_EMERGENCY_ENUM_MATCHES`.
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
    "worse_after_defervescence",
)
# Field "hay được tự nguyện nói trước" (nhóm b trong docstring `SymptomProtocol.safety_signal_fields`)
# - không phải dấu hiệu đỏ, nhưng người dùng thường kể ngay ở tin nhắn đầu (vd "bé 38 độ", "sốt 2 ngày
# nay") dù chưa tới lượt hỏi cụm tương ứng. Thiếu quét kèm khiến hệ thống hỏi lại thông tin đã có
# (phát hiện qua test tay với LLM thật).
_EARLY_VOLUNTEERED_FIELDS: tuple[str, ...] = (
    "temp_c",
    "temp_site",
    "fever_onset_at",
    "consciousness_level",
    "feeding_intake",
    "urine_output",
)
SAFETY_SIGNAL_FIELDS: tuple[str, ...] = EMERGENCY_TRI_STATE_FIELDS + _EARLY_VOLUNTEERED_FIELDS
_EMERGENCY_ENUM_MATCHES: dict[str, frozenset[str]] = {
    "consciousness_level": frozenset({"difficult_to_rouse", "unresponsive"}),
    "breathing_difficulty": frozenset({"severe"}),
    "urine_output": frozenset({"none_gt_6h"}),
    "feeding_intake": frozenset({"unable"}),
    "vomiting_severity": frozenset({"unable_to_keep_fluids"}),
    "abdominal_pain_severity": frozenset({"severe"}),
}

CHRONIC_SEVERE = frozenset({"cardiac", "pulmonary", "renal", "hepatic", "hematologic_thalassemia", "malignancy"})

EMERGENCY_MESSAGE = (
    "Đây là tình huống cần được cấp cứu ngay bây giờ — vui lòng gọi 115 hoặc đến ngay cơ sở y tế/"
    "khoa cấp cứu gần nhất, không chờ thêm. Thông tin đã được chuyển cho điều dưỡng ưu tiên hỗ trợ."
)

# Quét cơ hội: các field an toàn cốt lõi thường được người dùng chủ động mô tả ngay từ câu đầu tiên,
# trước khi tới lượt hỏi cụm tương ứng (đúng ví dụ O1, Part 8 CS). Danh sách CỐ Ý ngắn - chỉ phủ field
# M0 có hậu quả bỏ sót cao nhất; không thay thế LLM extraction theo cụm, chỉ bổ trợ.
OPPORTUNISTIC_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("seizure_active_now", ("đang co giật", "dang co giat", "co giật ngay", "co giat ngay")),
    ("seizure_occurred", ("co giật", "co giat")),
    ("non_blanching_rash", ("ban tím không mất", "ban tim khong mat", "ấn không mất", "an khong mat")),
    ("cyanosis", ("tím môi", "tim moi", "tím tái", "tim tai")),
    ("neck_stiffness", ("cứng gáy", "cung gay")),
    ("cold_clammy_skin", ("lạnh ẩm", "lanh am", "nổi vân tím", "noi van tim")),
)


def _is_filled(value: object) -> bool:
    return value is not None and value != "unknown" and value != ""


def _is_true(value: object) -> bool:
    return value is True or value == "true"


def _in(value: object, allowed: frozenset[str]) -> bool:
    return isinstance(value, str) and value in allowed


def _array_has_any(value: object, items: frozenset[str]) -> bool:
    if not isinstance(value, (list, tuple, set)):
        return False
    return any(item in items for item in value)


def _array_has_non_empty_excluding(value: object, excluded: frozenset[str]) -> bool:
    if not isinstance(value, (list, tuple, set)):
        return False
    return any(item not in excluded for item in value)


def _fever_present(a: dict[str, object]) -> bool:
    return _is_true(a.get("fever_reported")) or a.get("fever_status") in ("objective", "subjective")


def _months_since(iso_date: object) -> float | None:
    """Ước lượng số tháng từ một ngày ISO tới "hiện tại" giả định trong tài liệu (2026-08-12, theo
    ngày soạn KM/CS). Chỉ dùng cho rule sốt rét (R-E-19/R-V-20) - không dùng cho quyết định lâm sàng
    khác."""
    if not isinstance(iso_date, str):
        return None
    from datetime import date

    try:
        year, month, day = (int(part) for part in iso_date[:10].split("-"))
        returned = date(year, month, day)
    except ValueError:
        return None
    reference = date(2026, 8, 12)
    return (reference - returned).days / 30.0


def derive_duration(answers: dict[str, object]) -> dict[str, object]:
    """Field DẪN XUẤT `fever_duration_days` = số ngày từ `fever_onset_at` tới NGÀY THỰC (khác
    `_months_since` ở trên, cố tình dùng mốc tài liệu cố định chỉ cho rule sốt rét). KHÔNG bắt LLM tự
    tính (không đáng tin), và KHÔNG ghi đè nếu đã có sẵn `fever_duration_days` hợp lệ (vd người dùng tự
    nói số ngày trực tiếp thay vì ngày khởi phát)."""
    onset = answers.get("fever_onset_at")
    if not isinstance(onset, str):
        return {}
    from datetime import date, timezone
    from datetime import datetime as _datetime

    try:
        year, month, day = (int(part) for part in onset[:10].split("-"))
        onset_date = date(year, month, day)
    except ValueError:
        return {}
    today = _datetime.now(timezone.utc).date()
    days = (today - onset_date).days
    if days < 0:
        return {}
    return {"fever_duration_days": days}


def _travel_within_months(a: dict[str, object], months: float) -> bool | None:
    history = a.get("travel_history_12m")
    if not isinstance(history, (list, tuple)) or not history:
        return None
    deltas = [_months_since(entry.get("return_date")) for entry in history if isinstance(entry, dict)]
    deltas = [delta for delta in deltas if delta is not None]
    if not deltas:
        return None
    return min(deltas) <= months


def age_in_months(answers: dict[str, object]) -> float | None:
    value = answers.get("age_value")
    unit = answers.get("age_unit")
    if not _is_filled(value) or not _is_filled(unit):
        return None
    try:
        numeric = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if unit == "day":
        return numeric / 30.0
    if unit == "month":
        return numeric
    if unit == "year":
        return numeric * 12.0
    return None


def conservatism_tier(a: dict[str, object]) -> int:
    """KM §5.1-5.2 - hệ số thận trọng theo quần thể. Dùng nội bộ cho rule hạ thân nhiệt (R-E-15)."""
    age_months = age_in_months(a)
    if age_months is not None and age_months < 3:
        return 2
    if _is_true(a.get("known_neutropenia")) or _array_has_any(a.get("immunocompromise_cause"), frozenset({"chemotherapy_6w"})):
        return 2
    if (
        _is_true(a.get("is_pregnant"))
        or _is_true(a.get("postpartum_6w"))
        or _is_true(a.get("immunocompromised"))
        or _array_has_any(a.get("chronic_conditions"), CHRONIC_SEVERE)
        or (age_months is not None and age_months >= 75 * 12)
    ):
        return 1
    return 0


def has_provisional_emergency_signal(answers: dict[str, object]) -> bool:
    """Quét rất nhẹ các field M0 đỏ tuyệt đối - CHỈ dùng để biết khi nào nên dừng hỏi thường quy
    (Part 1.3 CS điểm 1). Không sinh reason_codes/triggered_rules chính thức (đó là việc của
    `rule_engine.evaluate` với `FEVER_PROTOCOL.rule_catalog`)."""
    for key in EMERGENCY_TRI_STATE_FIELDS:
        if _is_true(answers.get(key)):
            return True
    for key, matches in _EMERGENCY_ENUM_MATCHES.items():
        if answers.get(key) in matches:
            return True
    age_months = age_in_months(answers)
    if age_months is not None and age_months < 3 and _is_true(answers.get("fever_reported")):
        return True  # RF-22: sốt ở trẻ < 3 tháng luôn EMERGENCY
    return False


def determine_route(answers: dict[str, object]) -> str:
    """CS §4.3. Thứ tự ưu tiên: infant > high_risk > dengue_context > localized_source > standard -
    route mạnh hơn không bao giờ bị route yếu hơn ghi đè, đúng tinh thần "không rule nào hạ mức"."""
    age_months = age_in_months(answers)
    if age_months is not None and age_months < 3:
        return "ROUTE_INFANT_HIGH"
    if _is_high_risk_tier(answers):
        return "ROUTE_HIGH_RISK"
    if _is_dengue_context(answers):
        return "ROUTE_DENGUE_CONTEXT"
    if _is_localized_source(answers):
        return "ROUTE_LOCALIZED_SOURCE"
    return "ROUTE_STANDARD"


def _is_high_risk_tier(answers: dict[str, object]) -> bool:
    if _is_true(answers.get("is_pregnant")) or _is_true(answers.get("postpartum_6w")):
        return True
    if _is_true(answers.get("immunocompromised")) or _is_true(answers.get("known_neutropenia")):
        return True
    if _is_true(answers.get("malaria_risk_area")):
        return True
    chronic = answers.get("chronic_conditions")
    if isinstance(chronic, (list, tuple)) and any(item not in ("none", "unknown") for item in chronic):
        return True
    age_months = age_in_months(answers)
    if age_months is not None and age_months >= 75 * 12:
        return True
    if _is_true(answers.get("lives_alone")) or answers.get("caregiver_available") == "false":
        return True
    return False


def _is_dengue_context(answers: dict[str, object]) -> bool:
    if _is_true(answers.get("mosquito_exposure")):
        return True
    outbreak = answers.get("outbreak_exposure")
    if isinstance(outbreak, (list, tuple)) and "dengue" in outbreak:
        return True
    if answers.get("abdominal_pain_severity") == "severe":
        return True
    if _is_true(answers.get("mucosal_bleeding")) or _is_true(answers.get("gi_bleeding")):
        return True
    if _is_true(answers.get("worse_after_defervescence")):
        return True
    if _is_true(answers.get("nsaid_use")):
        return True
    return False


def _is_localized_source(answers: dict[str, object]) -> bool:
    """Chỉ có ý nghĩa SAU Stage 3A sạch (CS §4.3) - caller đảm bảo không gọi sớm hơn."""
    localized_signals = (
        _is_true(answers.get("sore_throat")),
        _is_true(answers.get("ear_pain")),
        _is_true(answers.get("cough")),
        _is_true(answers.get("urinary_symptoms")),
        _is_true(answers.get("localized_infection_signs")),
    )
    return any(localized_signals) and not has_provisional_emergency_signal(answers)


def budget_key(answers: dict[str, object], route: str, known_triage_level: str | None = None) -> str:
    """Chọn đúng hàng ngân sách trong `BUDGET` theo route/kết luận hiện có (§6.5).

    `known_triage_level`: kết luận triage MỚI NHẤT do rule engine trả về, do caller (`session.py`)
    truyền vào - protocol không tự tính lại rule engine. Không truyền gì thì chỉ dựa vào provisional
    scan (chỉ bắt được EMERGENCY, không bắt được EARLY_VISIT sinh ra ở Stage 4 như RF-23)."""
    if route == "ROUTE_INFANT_HIGH" or has_provisional_emergency_signal(answers) or known_triage_level == "EMERGENCY":
        return "EMERGENCY"
    if route == "ROUTE_HIGH_RISK":
        return "ROUTE_HIGH_RISK"
    if route == "ROUTE_DENGUE_CONTEXT":
        return "ROUTE_DENGUE_CONTEXT"
    if known_triage_level == "EARLY_VISIT":
        return "EARLY_VISIT"
    return "SELF_CARE_CANDIDATE"


# ---------------------------------------------------------------------------------------------
# Skip condition riêng cho các cụm có "Ask condition" không đơn thuần là "luôn hỏi" (CS Part 3).
# Trả True => BỎ QUA cụm này dù còn field chưa điền. (Nhánh "Stage 3B chỉ chạy nếu 3A sạch" đã được
# engine chung xử lý qua `protocol.gate_stages`, không cần khai báo lại ở đây.)
# ---------------------------------------------------------------------------------------------


def _skip_q1_03(answers: dict[str, object]) -> bool:
    return answers.get("fever_status") != "subjective"


def _skip_q2_05(answers: dict[str, object]) -> bool:
    age_months = age_in_months(answers)
    young = age_months is not None and age_months < 3
    old = age_months is not None and age_months >= 65 * 12
    return not (young or old or _is_true(answers.get("immunocompromised")))


def _skip_q3_02(answers: dict[str, object]) -> bool:
    age_months = age_in_months(answers)
    return age_months is not None and age_months < 16 * 12


def _skip_q4_01(answers: dict[str, object]) -> bool:
    age_months = age_in_months(answers)
    if answers.get("sex") != "female" or age_months is None:
        return True
    age_years = age_months / 12.0
    return not (10 <= age_years <= 60)


def _skip_q4_01b(answers: dict[str, object]) -> bool:
    return not (_is_true(answers.get("is_pregnant")) or _is_true(answers.get("postpartum_6w")))


def _skip_q4_02(answers: dict[str, object]) -> bool:
    age_months = age_in_months(answers)
    if answers.get("sex") != "female" or age_months is None:
        return True
    age_years = age_months / 12.0
    if _is_true(answers.get("is_pregnant")):
        return True
    return not (15 <= age_years <= 55)


def _skip_q5_06(answers: dict[str, object]) -> bool:
    age_months = age_in_months(answers)
    return not (age_months is not None and age_months < 5 * 12)


_SKIP_RULES: dict[str, object] = {
    "Q1-03": _skip_q1_03,
    "Q2-05": _skip_q2_05,
    "Q3-02": _skip_q3_02,
    "Q4-01": _skip_q4_01,
    "Q4-01b": _skip_q4_01b,
    "Q4-02": _skip_q4_02,
    "Q5-06": _skip_q5_06,
}


def skip_rule(cluster: QuestionCluster, answers: dict[str, object]) -> bool:
    rule = _SKIP_RULES.get(cluster.id)
    return bool(rule(answers)) if rule is not None else False


def self_care_checklist_satisfied(answers: dict[str, object]) -> bool:
    """KM §5.4 - checklist lâm sàng bắt buộc trước khi cho phép kết luận SELF_CARE (tuổi/tri
    giác/ăn uống/tiểu tiện/người theo dõi/khả năng tái khám). Hàm THUẦN theo giá trị field hiện có,
    không quan tâm đã "hỏi đủ cụm" chưa - đó là việc riêng của `stage_machine.should_stop`
    (SUFFICIENT_EVIDENCE chỉ xét ở stage cuối cùng, khi `next_cluster` đã trả `None` - tức toàn bộ
    stage trước đó chắc chắn đã đi qua tuần tự, nên không cần lặp lại kiểm tra "đã hỏi đủ chưa" ở
    đây). Tách 2 mối quan tâm này cho phép gọi hàm này ĐỘC LẬP để kiểm tra 1 bộ answers bất kỳ (vd
    test vàng Checkpoint 3 evaluate thẳng dữ liệu mẫu, không mô phỏng cả hội thoại)."""
    if has_provisional_emergency_signal(answers):
        return False
    age_months = age_in_months(answers)
    if age_months is None or age_months < 6:
        return False
    duration = answers.get("fever_duration_days")
    if isinstance(duration, (int, float)) and duration >= 5:
        return False
    if answers.get("consciousness_level") != "alert":
        return False
    if answers.get("feeding_intake") not in ("normal", "reduced"):
        return False
    if answers.get("urine_output") != "normal":
        return False
    self_sufficient_adult = age_months >= 16 * 12 and answers.get("reporter_type") == "self"
    if not (_is_true(answers.get("caregiver_available")) or self_sufficient_adult):
        return False
    return bool(_is_true(answers.get("can_return_for_followup")))


# ---------------------------------------------------------------------------------------------
# Rule catalog - R-E-xx (EMERGENCY/now), R-V-xx (EARLY_VISIT), R-G-01 (KM §6.1)
# Mỗi hàm nhận (answers, matches_so_far) - đa số bỏ qua matches_so_far, chỉ R-E-21 dùng để biết đã có
# rule EMERGENCY nào khác khớp trước đó chưa (theo đúng thứ tự khai báo trong _RULE_CATALOG bên dưới).
# ---------------------------------------------------------------------------------------------


def _r_e_01(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if _in(a.get("consciousness_level"), frozenset({"difficult_to_rouse", "unresponsive"})):
        return RuleMatch("R-E-01", ("RF-01",), "EMERGENCY", "now")
    return None


def _r_e_02(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    complex_features = _array_has_any(
        a.get("seizure_features"), frozenset({"focal", "duration_gt_5min", "recurrent_24h", "incomplete_recovery"})
    )
    if _is_true(a.get("seizure_occurred")) or _is_true(a.get("seizure_active_now")) or complex_features:
        codes = ["RF-02"]
        if complex_features:
            codes.append("RF-03")
        return RuleMatch("R-E-02", tuple(codes), "EMERGENCY", "now")
    return None


def _r_e_03(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if _is_true(a.get("neck_stiffness")) or _is_true(a.get("bulging_fontanelle")) or _is_true(a.get("photophobia")):
        return RuleMatch("R-E-03", ("RF-04",), "EMERGENCY", "now")
    return None


def _r_e_04(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    age_months = age_in_months(a)
    if _is_true(a.get("new_confusion")) and age_months is not None and age_months >= 16 * 12:
        return RuleMatch("R-E-04", ("RF-05",), "EMERGENCY", "now")
    return None


def _r_e_05(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if _is_true(a.get("focal_neuro_deficit")):
        return RuleMatch("R-E-05", ("RF-06",), "EMERGENCY", "now")
    return None


def _r_e_06(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if a.get("breathing_difficulty") == "severe" or _is_true(a.get("cyanosis")) or _is_true(a.get("stridor_or_drooling")):
        codes = []
        if a.get("breathing_difficulty") == "severe":
            codes.append("RF-07")
        if _is_true(a.get("cyanosis")):
            codes.append("RF-08")
        if _is_true(a.get("stridor_or_drooling")):
            codes.append("RF-10")
        return RuleMatch("R-E-06", tuple(codes), "EMERGENCY", "now")
    return None


def _r_e_07(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    age_months = age_in_months(a)
    young = age_months is not None and age_months < 5 * 12
    if young and (_is_true(a.get("chest_indrawing")) or _is_true(a.get("nasal_flaring_grunting"))):
        return RuleMatch("R-E-07", ("RF-09",), "EMERGENCY", "now")
    return None


def _r_e_08(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    spo2 = a.get("spo2_percent")
    if isinstance(spo2, (int, float)) and spo2 <= 92:
        return RuleMatch("R-E-08", ("RF-11",), "EMERGENCY", "now")
    return None


def _r_e_09(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if _is_true(a.get("cold_clammy_skin")) or _is_true(a.get("capillary_refill_ge_3s")):
        return RuleMatch("R-E-09", ("RF-13",), "EMERGENCY", "now")
    return None


def _r_e_10(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if a.get("urine_output") == "none_gt_6h":
        return RuleMatch("R-E-10", ("RF-14",), "EMERGENCY", "now")
    return None


def _r_e_11(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if a.get("feeding_intake") == "unable" or a.get("vomiting_severity") == "unable_to_keep_fluids":
        return RuleMatch("R-E-11", ("RF-15",), "EMERGENCY", "now")
    return None


def _r_e_12(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if _is_true(a.get("non_blanching_rash")):
        return RuleMatch("R-E-12", ("RF-18",), "EMERGENCY", "now")
    return None


def _r_e_13(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if _is_true(a.get("mucosal_bleeding")) or _is_true(a.get("gi_bleeding")):
        codes = []
        if _is_true(a.get("mucosal_bleeding")):
            codes.append("RF-19")
        if _is_true(a.get("gi_bleeding")):
            codes.append("RF-20")
        return RuleMatch("R-E-13", tuple(codes), "EMERGENCY", "now")
    return None


def _r_e_14(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    age_months = age_in_months(a)
    if age_months is not None and age_months < 3 and _fever_present(a):
        return RuleMatch("R-E-14", ("RF-22",), "EMERGENCY", "now")
    return None


def _r_e_16(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    temp = a.get("temp_c")
    if not (isinstance(temp, (int, float)) and temp >= 40.0):
        return None
    heat_exposure = _is_true(a.get("heat_exposure_context"))
    if a.get("consciousness_level") not in ("alert", None) or heat_exposure:
        return RuleMatch("R-E-16", ("RF-25",), "EMERGENCY", "now")
    return None


def _r_e_17(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if _is_true(a.get("worse_after_defervescence")):
        return RuleMatch("R-E-17", ("RF-29",), "EMERGENCY", "now")
    return None


def _r_e_18(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    at_risk = _is_true(a.get("known_neutropenia")) or _array_has_any(a.get("immunocompromise_cause"), frozenset({"chemotherapy_6w"}))
    if not at_risk:
        return None
    temp = a.get("temp_c")
    threshold_met = isinstance(temp, (int, float)) and temp >= 38.3
    if threshold_met or _is_true(a.get("fever_reported")):
        return RuleMatch("R-E-18", ("RF-30",), "EMERGENCY", "now")
    return None


def _r_e_19(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if not _is_true(a.get("malaria_risk_area")):
        return None
    within_month = _travel_within_months(a, 1)
    if within_month is None or within_month:
        return RuleMatch("R-E-19", ("RF-35",), "EMERGENCY", "now")
    return None


def _r_e_20(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if a.get("abdominal_pain_severity") == "severe" or _is_true(a.get("abdominal_guarding")):
        return RuleMatch("R-E-20", ("RF-39",), "EMERGENCY", "now")
    return None


def _r_e_15(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    temp = a.get("temp_c")
    hypothermia = (isinstance(temp, (int, float)) and temp < 36.0) or _is_true(a.get("hypothermia_reported"))
    if hypothermia and conservatism_tier(a) >= 1:
        return RuleMatch("R-E-15", ("RF-24",), "EMERGENCY", "now")
    return None


def _r_e_21(a: dict[str, object], matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if not (_is_true(a.get("is_pregnant")) or _is_true(a.get("postpartum_6w"))):
        return None
    flags = a.get("obstetric_red_flags")
    has_flags = isinstance(flags, (list, tuple)) and len(flags) > 0
    other_emergency_matched = any(m.level == "EMERGENCY" for m in matches)
    if has_flags or other_emergency_matched:
        return RuleMatch("R-E-21", ("RF-32",), "EMERGENCY", "now")
    return None


def _r_v_01(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    age_months = age_in_months(a)
    if age_months is None or not (3 <= age_months < 6):
        return None
    temp = a.get("temp_c")
    if isinstance(temp, (int, float)) and temp >= 39.0:
        return RuleMatch("R-V-01", ("RF-23",), "EARLY_VISIT", "within_24h")
    return None


def _r_v_02(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    duration = a.get("fever_duration_days")
    if isinstance(duration, (int, float)) and duration >= 5:
        return RuleMatch("R-V-02", ("RF-26",), "EARLY_VISIT", "within_24h")
    return None


def _r_v_03(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    duration = a.get("fever_duration_days")
    if isinstance(duration, (int, float)) and duration >= 7:
        return RuleMatch("R-V-03", ("RF-27",), "EARLY_VISIT", "within_24h")
    return None


def _r_v_04(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if _is_true(a.get("rigors")):
        return RuleMatch("R-V-04", ("RF-28",), "EARLY_VISIT", "within_24h")
    return None


def _r_v_05(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    spo2 = a.get("spo2_percent")
    spo2_band = isinstance(spo2, (int, float)) and 93 <= spo2 <= 95
    if spo2_band or _is_true(a.get("rapid_breathing")):
        return RuleMatch("R-V-05", ("RF-11",), "EARLY_VISIT", "within_4h")
    return None


def _r_v_06(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    signs = a.get("dehydration_signs")
    many_signs = isinstance(signs, (list, tuple)) and len(signs) >= 2
    reduced_combo = a.get("urine_output") == "reduced" and a.get("feeding_intake") == "reduced"
    if many_signs or reduced_combo:
        return RuleMatch("R-V-06", ("RF-16",), "EARLY_VISIT", "within_4h")
    return None


def _r_v_07(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if _is_true(a.get("dizziness_on_standing")):
        return RuleMatch("R-V-07", ("RF-17",), "EARLY_VISIT", "within_24h")
    return None


def _r_v_08(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if _is_true(a.get("jaundice_new")):
        return RuleMatch("R-V-08", ("RF-21",), "EARLY_VISIT", "within_24h")
    return None


def _r_v_09(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if _is_true(a.get("immunocompromised")) and not _is_true(a.get("known_neutropenia")):
        return RuleMatch("R-V-09", ("RF-31",), "EARLY_VISIT", "within_4h")
    return None


def _r_v_10(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if _is_true(a.get("is_pregnant")) or _is_true(a.get("postpartum_6w")):
        return RuleMatch("R-V-10", ("RF-32",), "EARLY_VISIT", "within_4h")
    return None


def _r_v_11(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    device = a.get("indwelling_device")
    has_device = isinstance(device, (list, tuple)) and _array_has_non_empty_excluding(device, frozenset({"none"}))
    if _is_true(a.get("recent_surgery_30d")) or has_device:
        codes = []
        if _is_true(a.get("recent_surgery_30d")):
            codes.append("RF-33")
        if has_device:
            codes.append("RF-34")
        return RuleMatch("R-V-11", tuple(codes), "EARLY_VISIT", "within_24h")
    return None


def _r_v_12(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if _array_has_any(a.get("chronic_conditions"), CHRONIC_SEVERE):
        return RuleMatch("R-V-12", ("RF-36",), "EARLY_VISIT", "within_24h")
    return None


def _r_v_13(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    age_months = age_in_months(a)
    if age_months is not None and age_months >= 75 * 12:
        return RuleMatch("R-V-13", ("RF-37",), "EARLY_VISIT", "within_24h")
    return None


def _r_v_14(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if a.get("vomiting_severity") == "frequent":
        return RuleMatch("R-V-14", ("RF-40",), "EARLY_VISIT", "within_4h")
    return None


def _r_v_15(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if _is_true(a.get("joint_limb_swelling")) or _is_true(a.get("non_weight_bearing")):
        return RuleMatch("R-V-15", ("RF-41",), "EARLY_VISIT", "within_24h")
    return None


def _r_v_16(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    age_months = age_in_months(a)
    young = age_months is not None and age_months < 5 * 12
    has_clear_source = _is_true(a.get("localized_infection_signs")) or any(
        _is_true(a.get(key)) for key in ("sore_throat", "ear_pain", "cough")
    )
    if young and _fever_present(a) and not has_clear_source:
        return RuleMatch("R-V-16", ("RF-42",), "EARLY_VISIT", "within_24h")
    return None


def _r_v_17(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if _is_true(a.get("localized_infection_signs")):
        return RuleMatch("R-V-17", ("RF-43",), "EARLY_VISIT", "within_24h")
    return None


def _r_v_18(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    concern = a.get("caregiver_concern_level")
    high_concern = isinstance(concern, (int, float)) and concern >= 8
    if high_concern or _is_true(a.get("looks_very_unwell")):
        return RuleMatch("R-V-18", ("RF-44",), "EARLY_VISIT", "within_4h")
    return None


def _r_v_19(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if _is_true(a.get("chest_pain")) or _is_true(a.get("hemoptysis")):
        return RuleMatch("R-V-19", ("RF-12",), "EARLY_VISIT", "within_4h")
    return None


def _r_v_20(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if not _is_true(a.get("malaria_risk_area")):
        return None
    within_month = _travel_within_months(a, 1)
    if within_month is False:
        return RuleMatch("R-V-20", ("RF-35",), "EARLY_VISIT", "within_24h")
    return None


def _r_g_01(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if _is_true(a.get("lives_alone")) or a.get("caregiver_available") == "false":
        return RuleMatch("R-G-01", ("RF-38",), "EARLY_VISIT", "within_24h")
    return None


def _fallback_rule(_a: dict[str, object]) -> RuleMatch:
    # R-G-02(a) + CS Part 6 "Dừng hẳn" (c): không bao giờ mặc định về SELF_CARE khi checklist §5.4
    # chưa thoả - an toàn hơn luôn là EARLY_VISIT (P0-6: mơ hồ giữa 2 mức luôn chọn mức thận trọng hơn).
    return RuleMatch("R-G-02", (), "EARLY_VISIT", "within_24h")


def _self_care_default_rule(_a: dict[str, object]) -> RuleMatch:
    return RuleMatch("R-S-01", (), "SELF_CARE", "monitor")


# Thứ tự khai báo QUAN TRỌNG: R-E-15 (hạ thân nhiệt) và R-E-21 (sản khoa) phải đứng SAU mọi rule
# R-E-xx khác trong cùng nhóm EMERGENCY, vì R-E-21 cần biết ĐÃ có rule EMERGENCY nào khác khớp chưa
# (đúng logic gốc trước khi tách generic engine).
RULE_CATALOG: tuple = (
    _r_e_01, _r_e_02, _r_e_03, _r_e_04, _r_e_05, _r_e_06, _r_e_07, _r_e_08, _r_e_09, _r_e_10,
    _r_e_11, _r_e_12, _r_e_13, _r_e_14, _r_e_16, _r_e_17, _r_e_18, _r_e_19, _r_e_20,
    _r_e_15, _r_e_21,
    _r_v_01, _r_v_02, _r_v_03, _r_v_04, _r_v_05, _r_v_06, _r_v_07, _r_v_08, _r_v_09, _r_v_10,
    _r_v_11, _r_v_12, _r_v_13, _r_v_14, _r_v_15, _r_v_16, _r_v_17, _r_v_18, _r_v_19, _r_v_20,
    _r_g_01,
)


FEVER_PROTOCOL = SymptomProtocol(
    name="fever",
    fields_by_key=FIELDS_BY_KEY,
    clusters=QUESTION_CLUSTERS,
    stage_order=STAGE_ORDER,
    gate_stages=GATE_STAGES,
    budget=BUDGET,
    budget_floor_stage=BUDGET_FLOOR_STAGE,
    determine_route=determine_route,
    budget_key=budget_key,
    provisional_emergency_signal=has_provisional_emergency_signal,
    self_care_checklist_satisfied=self_care_checklist_satisfied,
    skip_rule=skip_rule,
    rule_catalog=RULE_CATALOG,
    fallback_rule=_fallback_rule,
    self_care_default_rule=_self_care_default_rule,
    emergency_message=EMERGENCY_MESSAGE,
    safety_signal_fields=SAFETY_SIGNAL_FIELDS,
    opportunistic_keywords=OPPORTUNISTIC_KEYWORDS,
    derive_fields=derive_duration,
)
