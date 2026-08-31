"""`CHEST_PAIN_PROTOCOL` — protocol ĐAU NGỰC (F09 §3.6.1).

Đọc `chest_pain_checklist.py` trước để biết field/cụm. File này chỉ chứa phần QUYẾT ĐỊNH: nhánh,
ngân sách, skip-rule, và luật triage.

**Mỗi dòng trong bảng mapping của tài liệu nguồn = đúng MỘT rule ở đây**, và mã rule ghi kèm dòng nào
nó đến từ. Đó là điều kiện để review lâm sàng đối chiếu được 1-1 mà không phải đọc Python:

| Mức | Dòng tài liệu | Rule |
| --- | --- | --- |
| Cấp cứu | Câu 1 = có (khó thở nặng / không tỉnh táo) | `common_rules` `r_e_06` / `r_e_01` |
| Cấp cứu | đau >5 phút + đè ép + (tuổi >50 hoặc ≥1 yếu tố nguy cơ) | `r_cp_01` |
| Cấp cứu | đau kèm khó thở / tim đập nhanh-không đều | `r_cp_02` |
| Khám sớm | đau >5 phút nhưng chưa đủ tiêu chí Cấp cứu | `r_cp_03` |
| Khám sớm | có yếu tố nguy cơ VTE | `r_cp_04` |
| Khám sớm | đau từng cơn tăng dần mức độ/tần suất | `r_cp_05` |
| Khám sớm | sốt >38.1°C kèm đau ngực | `r_cp_06` |
| Tự chăm sóc | đau nhẹ, từng cơn, mỗi lần vài giây, không nguy cơ, không triệu chứng kèm | `_self_care_satisfied` |

⚠️ **Ngưỡng và tổ hợp ở đây là NỘI DUNG LÂM SÀNG, cần Data Lead ký duyệt** — cùng lý do
`generic_protocol.py` ghi trong docstring của nó.
"""

from __future__ import annotations

from src.services.checklists.chest_pain_checklist import (
    CRITICAL_SCAN_STAGE,
    EARLY_VISIT_SCAN_STAGE,
    EMERGENCY_SCAN_STAGE,
    FIELDS_BY_KEY,
    GATE_STAGES,
    QUESTION_CLUSTERS,
    STAGE_ORDER,
)
from src.services.symptom_protocol.common_safety import fields as common_fields
from src.services.symptom_protocol.common_safety import rules as common_rules
from src.services.symptom_protocol.common_safety import screening_groups as common_screening
from src.services.symptom_protocol.common_safety.emergency_message import SUSPECTED_RED_FLAG_MESSAGE
from src.services.symptom_protocol.common_safety.predicates import (
    age_in_months,
    array_has_any,
    array_has_non_empty_excluding,
    as_float,
    is_in,
    is_true,
)
from src.services.symptom_protocol.models import QuestionCluster, RuleMatch
from src.services.symptom_protocol.protocol import SymptomProtocol

PROTOCOL_NAME = "chest_pain"

# --- Ngưỡng lâm sàng, tất cả đến từ tài liệu nguồn ------------------------------------------------

PROLONGED_PAIN_MINUTES = 5.0
"""Ngưỡng quyết định CHÍNH của Schmitt-Thompson Chest Pain: đau kéo dài >5 phút."""

CARDIAC_RISK_AGE_YEARS = 50
"""Tuổi >50 tính là một yếu tố nguy cơ tim mạch độc lập."""

FEVER_WITH_CHEST_PAIN_C = 38.1
"""Sốt >38.1°C kèm đau ngực -> khám sớm (nghi viêm màng phổi/viêm phổi/viêm màng ngoài tim)."""

BRIEF_PAIN_MINUTES = 1.0
"""Trần "mỗi lần chỉ vài giây" của dòng Tự chăm sóc. Để 1 phút chứ không 0.5: người bệnh ước lượng
thời gian rất thô, và sai số ở đây rơi về phía thận trọng (quá 1 phút thì lên khám sớm)."""

SELF_CARE_MAX_SEVERITY = 3.0
"""Trần mức đau (0-10) còn được kết luận tự chăm sóc. Thấp hơn generic (4.0) vì đau ngực là than
phiền có hậu quả bỏ sót nặng nhất trong 5 nhóm."""

# Tính chất đau gợi ý hội chứng vành cấp - "đè ép/bóp nghẹt/nặng ngực" của câu 2.
ACS_PAIN_CHARACTER = frozenset({"pressure", "crushing", "tightness"})

# Hướng lan là discriminator kinh điển; "back" tách riêng vì nó gợi bóc tách động mạch chủ.
ACS_RADIATION = frozenset({"shoulder", "arm", "jaw"})

REASON_CODE_LABELS: dict[str, str] = {
    **common_rules.REASON_CODE_LABELS,
    "RF-50": "Đau ngực kiểu đè ép kéo dài kèm yếu tố nguy cơ tim mạch",
    "RF-51": "Đau ngực kèm khó thở / rối loạn nhịp",
    "RF-52": "Đau ngực kéo dài trên 5 phút",
    "RF-53": "Yếu tố nguy cơ thuyên tắc huyết khối tĩnh mạch",
    "RF-54": "Đau ngực tăng dần mức độ / tần suất",
    "RF-55": "Sốt kèm đau ngực",
    "RF-56": "Đau ngực lan ra lưng",
}

SAFETY_SIGNAL_FIELDS: tuple[str, ...] = common_rules.EMERGENCY_TRI_STATE_FIELDS + (
    "consciousness_level",
    "breathing_difficulty",
    # Field đặc thù hay được người bệnh tự khai ngay tin nhắn đầu ("đau thắt ngực lan xuống tay
    # trái") - cùng lý do `fever_protocol._EARLY_VOLUNTEERED_FIELDS`.
    "chest_pain",
    "chest_pain_character",
    "chest_pain_radiation",
    "chest_pain_onset_at",
    "diaphoresis",
    "palpitations",
    # Bối cảnh nguy cơ hay được kể sớm.
    "is_pregnant",
    "chronic_conditions",
    "immunocompromised",
    "temp_c",
)


# --- Nhánh + ngân sách ----------------------------------------------------------------------------


def _has_cardiac_risk(a: dict[str, object]) -> bool:
    """Tuổi >50 HOẶC ≥1 yếu tố nguy cơ tim mạch được khai rõ — câu 4 của tài liệu.

    `array_has_non_empty_excluding` chứ không phải "khác rỗng": người bệnh trả lời "không có gì" thì
    extractor ghi `"none"`, và coi đó là CÓ nguy cơ sẽ đẩy mọi ca lành tính lên cấp cứu."""
    age_months = age_in_months(a)
    if age_months is not None and age_months >= CARDIAC_RISK_AGE_YEARS * 12:
        return True
    if array_has_non_empty_excluding(a.get("cardiac_risk_factors"), frozenset({"none", "khong", "không"})):
        return True
    return array_has_any(a.get("chronic_conditions"), common_rules.CHRONIC_SEVERE)


def _has_vte_risk(a: dict[str, object]) -> bool:
    """Câu 5, nhánh thuyên tắc phổi: mới phẫu thuật / nằm bất động lâu / đi máy bay xa."""
    return is_true(a.get("recent_surgery_30d")) or is_true(a.get("immobility_or_long_travel"))


def _pain_minutes(a: dict[str, object]) -> float | None:
    return as_float(a.get("chest_pain_duration_min"))


def _pain_is_prolonged(a: dict[str, object]) -> bool:
    minutes = _pain_minutes(a)
    return minutes is not None and minutes > PROLONGED_PAIN_MINUTES


def determine_route(a: dict[str, object]) -> str:
    """Hai nhánh: có nền tim mạch/VTE hay không. Nhánh nguy cơ được cấp ngân sách rộng hơn vì nó là
    nhánh mà một câu hỏi thêm còn đổi được kết luận."""
    if _has_cardiac_risk(a) or _has_vte_risk(a):
        return "ROUTE_HIGH_RISK"
    return "ROUTE_STANDARD"


BUDGET: dict[str, tuple[int, int]] = {
    "EMERGENCY": (3, 6),
    "ROUTE_HIGH_RISK": (9, 15),
    "ROUTE_STANDARD": (8, 13),
}

BUDGET_FLOOR_STAGE = "3"
"""Ngân sách chỉ có hiệu lực từ stage quét khám sớm trở đi - cùng lý do và cùng cách đặt như generic:
để ở stage cuối thì nó không bao giờ cắt được gì trước khi đã đi hết bộ câu hỏi."""


def budget_key(a: dict[str, object], route: str, known_triage_level: str | None = None) -> str:
    if known_triage_level == "EMERGENCY":
        return "EMERGENCY"
    return route if route in BUDGET else "ROUTE_STANDARD"


# --- Skip rule — đây là phần "decision tree, không phải checklist tuyến tính" ----------------------


def _skip_pregnancy_detail(a: dict[str, object]) -> bool:
    if a.get("sex") == "male":
        return True
    return a.get("is_pregnant") == "false"


def _skip_surgical_detail(a: dict[str, object]) -> bool:
    return a.get("recent_surgery_30d") == "false" and a.get("indwelling_device") in (None, "unknown", "none")


def _skip_vte_probe(a: dict[str, object]) -> bool:
    """Bỏ cụm VTE khi cơn đau đã rõ là kiểu vành cấp VÀ không có gì gợi thuyên tắc phổi.

    Đây là nhánh cắt duy nhất của protocol này, và nó cố ý HẸP: chỉ cắt khi đã có đủ căn cứ để phân
    loại theo hướng khác, đúng yêu cầu "nhánh đã đủ dữ kiện thì các câu nhánh khác bị bỏ qua"."""
    return (
        is_in(a.get("chest_pain_character"), ACS_PAIN_CHARACTER)
        and is_in(a.get("chest_pain_radiation"), ACS_RADIATION)
        and a.get("breathing_difficulty") == "none"
        and a.get("hemoptysis") == "false"
    )


_SKIP_RULES: dict[str, object] = {
    "Q4-01": _skip_pregnancy_detail,
    "Q4-01b": _skip_pregnancy_detail,
    "Q4-02": _skip_pregnancy_detail,
    "Q4-05": _skip_surgical_detail,
    "CP-04": _skip_vte_probe,
}


def skip_rule(cluster: QuestionCluster, a: dict[str, object]) -> bool:
    predicate = _SKIP_RULES.get(cluster.id)
    return bool(predicate(a)) if predicate is not None else False


# --- Rule đặc thù: CẤP CỨU ------------------------------------------------------------------------


def r_cp_01(a: dict[str, object], _m: tuple[RuleMatch, ...]) -> RuleMatch | None:
    """*"đau >5 phút + tính chất đè ép ở câu 2 + (tuổi/yếu tố nguy cơ ở câu 4)"* -> Cấp cứu.

    Ba vế phải CÙNG đúng - đó là điều làm nó khác `r_cp_03` (chỉ có vế thời gian)."""
    if (
        _pain_is_prolonged(a)
        and is_in(a.get("chest_pain_character"), ACS_PAIN_CHARACTER)
        and _has_cardiac_risk(a)
    ):
        return RuleMatch("R-CP-01", ("RF-50",), "EMERGENCY", "now")
    return None


def r_cp_02(a: dict[str, object], _m: tuple[RuleMatch, ...]) -> RuleMatch | None:
    """*"đau kèm khó thở / tim đập nhanh-không đều ở câu 5"* -> Cấp cứu.

    KHÔNG đòi ngưỡng 5 phút: tài liệu để dòng này độc lập với thời lượng, vì tổ hợp đau ngực + khó
    thở là chỗ hội chứng vành cấp và thuyên tắc phổi gặp nhau. Đây cũng chính là dữ kiện mà cụm phủ
    chéo `CP-03`/`BR-03` thu về (F09 §3.10b)."""
    if not is_true(a.get("chest_pain")):
        return None
    if is_in(a.get("breathing_difficulty"), frozenset({"mild", "severe"})) or is_true(a.get("palpitations")):
        return RuleMatch("R-CP-02", ("RF-51",), "EMERGENCY", "now")
    return None


def r_cp_07(a: dict[str, object], _m: tuple[RuleMatch, ...]) -> RuleMatch | None:
    """Đau ngực lan ra LƯNG -> Cấp cứu (nghi bóc tách động mạch chủ).

    Không phải một dòng riêng trong bảng mapping, nhưng `chest_pain_radiation="back"` là discriminator
    mà mục tiêu của protocol nêu đích danh ("loại trừ ... bóc tách động mạch chủ"), và tài liệu gốc
    Schmitt-Thompson liệt kê nó ở nhóm khẩn cấp. Ghi tách rule riêng để review lâm sàng nhìn thấy nó
    là một quyết định, không phải hệ quả lẫn trong rule khác."""
    if a.get("chest_pain_radiation") == "back" and _pain_is_prolonged(a):
        return RuleMatch("R-CP-07", ("RF-56",), "EMERGENCY", "now")
    return None


# --- Rule đặc thù: CẦN KHÁM SỚM -------------------------------------------------------------------


def r_cp_03(a: dict[str, object], _m: tuple[RuleMatch, ...]) -> RuleMatch | None:
    """*"đau >5 phút nhưng không đủ tiêu chí Cấp cứu"* -> Khám sớm.

    KHÔNG kiểm "không đủ tiêu chí cấp cứu" ở đây: `rule_engine` lấy mức CAO NHẤT trong các rule khớp,
    nên khi `r_cp_01`/`r_cp_02` cùng khớp thì EMERGENCY tự thắng. Viết điều kiện loại trừ vào đây là
    chép lại logic của engine ở chỗ thứ hai - và hai bản sẽ lệch nhau."""
    if _pain_is_prolonged(a):
        return RuleMatch("R-CP-03", ("RF-52",), "EARLY_VISIT", "within_4h")
    return None


def r_cp_04(a: dict[str, object], _m: tuple[RuleMatch, ...]) -> RuleMatch | None:
    """*"có yếu tố nguy cơ VTE ở câu 5"* -> Khám sớm."""
    if is_true(a.get("chest_pain")) and _has_vte_risk(a):
        return RuleMatch("R-CP-04", ("RF-53",), "EARLY_VISIT", "within_4h")
    return None


def r_cp_05(a: dict[str, object], _m: tuple[RuleMatch, ...]) -> RuleMatch | None:
    """*"đau từng cơn tăng dần mức độ/tần suất"* -> Khám sớm."""
    if is_true(a.get("chest_pain_worsening")):
        return RuleMatch("R-CP-05", ("RF-54",), "EARLY_VISIT", "within_4h")
    return None


def r_cp_06(a: dict[str, object], _m: tuple[RuleMatch, ...]) -> RuleMatch | None:
    """*"sốt >38.1°C kèm đau ngực"* -> Khám sớm."""
    temp = as_float(a.get("temp_c"))
    if is_true(a.get("chest_pain")) and temp is not None and temp > FEVER_WITH_CHEST_PAIN_C:
        return RuleMatch("R-CP-06", ("RF-55",), "EARLY_VISIT", "within_24h")
    return None


# --- Tự chăm sóc ----------------------------------------------------------------------------------


def _self_care_satisfied(a: dict[str, object]) -> bool:
    """*"đau nhẹ, từng cơn, mỗi lần chỉ vài giây, không có yếu tố nguy cơ, không triệu chứng đi kèm ở
    câu 5"* — dòng Tự chăm sóc của bảng mapping, dịch nguyên vẹn.

    KHÔNG dùng `common_rules.baseline_self_care_satisfied`: hàm đó đọc `complaint_severity` /
    `complaint_progression` của generic, mà protocol này không khai. Quan trọng hơn, nó là checklist
    cho một protocol KHÔNG biết gì về nguyên nhân; ở đây ta có tài liệu riêng nên phải dùng đúng điều
    kiện của tài liệu đó.

    Mọi field còn `unknown` đều làm hàm trả `False` — "chưa hỏi" không phải "an toàn" (P0-6)."""
    if common_rules.has_emergency_signal(a):
        return False
    if a.get("consciousness_level") != "alert":
        return False

    # đau NHẸ
    severity = as_float(a.get("chest_pain_severity"))
    if severity is None or severity > SELF_CARE_MAX_SEVERITY:
        return False
    # TỪNG CƠN, mỗi lần chỉ vài giây
    if a.get("chest_pain_pattern") != "intermittent":
        return False
    minutes = _pain_minutes(a)
    if minutes is None or minutes > BRIEF_PAIN_MINUTES:
        return False
    if a.get("chest_pain_worsening") != "false":
        return False

    # KHÔNG triệu chứng đi kèm ở câu 5
    if a.get("breathing_difficulty") != "none":
        return False
    for key in ("diaphoresis", "palpitations", "hemoptysis"):
        if a.get(key) != "false":
            return False

    # KHÔNG yếu tố nguy cơ - và chúng phải đã được HỎI, không suy từ im lặng
    for key in ("recent_surgery_30d", "immobility_or_long_travel"):
        if a.get(key) != "false":
            return False
    if a.get("cardiac_risk_factors") in (None, "", "unknown"):
        return False
    if _has_cardiac_risk(a):
        return False

    # safety-netting: chỉ được khuyên ở nhà khi ở nhà là an toàn
    age_months = age_in_months(a)
    if age_months is None:
        return False
    self_sufficient_adult = age_months >= 16 * 12 and a.get("reporter_type") == "self"
    if not (is_true(a.get("caregiver_available")) or self_sufficient_adult):
        return False
    return bool(is_true(a.get("can_return_for_followup")))


def _self_care_default_rule(_a: dict[str, object]) -> RuleMatch:
    """Mã `R-S-03` riêng cho đau ngực (fever `R-S-01`, generic `R-S-02`): đọc log/phiếu phải thấy
    ngay kết luận "tự theo dõi" này đến từ checklist NÀO."""
    return RuleMatch("R-S-03", (), "SELF_CARE", "monitor")


# --- Catalog --------------------------------------------------------------------------------------
#
# `r_e_21` (sản khoa) phải đứng SAU mọi rule EMERGENCY khác - kể cả rule đặc thù nhóm - vì nó đọc
# `matches_so_far`. Đây là ràng buộc thứ tự thật, không phải sở thích trình bày.
RULE_CATALOG: tuple = (
    *common_rules.EMERGENCY_RULES,
    r_cp_01,
    r_cp_02,
    r_cp_07,
    common_rules.r_e_21,
    *(rule for rule in common_rules.EARLY_VISIT_RULES if rule is not common_rules.r_v_19),
    r_cp_03,
    r_cp_04,
    r_cp_05,
    r_cp_06,
    common_rules.r_g_01,
)

SCREENING_GROUPS: tuple = (
    common_screening.critical_scan_groups(CRITICAL_SCAN_STAGE)
    + common_screening.emergency_scan_groups(EMERGENCY_SCAN_STAGE)
    + common_screening.early_visit_scan_groups(EARLY_VISIT_SCAN_STAGE)
    + common_screening.risk_context_groups("4")
)

FIELD_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "is_pregnant": ("gestational_weeks", "obstetric_red_flags"),
    "immunocompromised": ("immunocompromise_cause", "known_neutropenia"),
    "recent_surgery_30d": ("surgical_site_signs",),
    "rash_present": ("rash_type",),
    # `chest_pain_duration_min` PHẢI có mặt: `registry._has_chest_pain_evidence` đọc chính field này
    # làm bằng chứng nhóm. Thiếu nó thì người bệnh rút lời "tôi không đau ngực" xoá được tính chất và
    # hướng lan, nhưng thời lượng sống sót - và bằng chứng đau ngực KHÔNG BAO GIỜ tắt, nên phiên bị
    # kéo về lại protocol này ở mọi lượt sau.
    "chest_pain": (
        "chest_pain_character", "chest_pain_radiation", "chest_pain_location",
        "chest_pain_duration_min",
    ),
}


CHEST_PAIN_PROTOCOL = SymptomProtocol(
    name=PROTOCOL_NAME,
    fields_by_key=FIELDS_BY_KEY,
    clusters=QUESTION_CLUSTERS,
    stage_order=STAGE_ORDER,
    gate_stages=GATE_STAGES,
    critical_scan_stage=CRITICAL_SCAN_STAGE,
    emergency_scan_stage=EMERGENCY_SCAN_STAGE,
    early_visit_scan_stage=EARLY_VISIT_SCAN_STAGE,
    budget=BUDGET,
    budget_floor_stage=BUDGET_FLOOR_STAGE,
    determine_route=determine_route,
    budget_key=budget_key,
    provisional_emergency_signal=common_rules.has_emergency_signal,
    self_care_checklist_satisfied=_self_care_satisfied,
    skip_rule=skip_rule,
    rule_catalog=RULE_CATALOG,
    fallback_rule=common_rules.default_early_visit_rule,
    self_care_default_rule=_self_care_default_rule,
    patient_red_flag_message=SUSPECTED_RED_FLAG_MESSAGE,
    safety_signal_fields=SAFETY_SIGNAL_FIELDS,
    opportunistic_keywords=common_rules.OPPORTUNISTIC_KEYWORDS,
    screening_groups=SCREENING_GROUPS,
    field_dependencies=FIELD_DEPENDENCIES,
    confirm_before_retract=common_fields.CONFIRM_BEFORE_RETRACT,
    reason_code_labels=REASON_CODE_LABELS,
    default_chief_complaint="Đau ngực",
    onset_field="chest_pain_onset_at",
    severity_field="chest_pain_severity",
)
