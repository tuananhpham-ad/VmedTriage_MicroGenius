"""Rule engine cho fever: ánh xạ `RF-xx` (KM Part 4) và `R-x-xx` (KM §6.1) sang mức triage.

Module THUẦN rule-based - không gọi LLM, không import `provider_router`/`llm`. Đây là gate giữa
`extract` và `next_question` ở Stage 3A/3B (kiến trúc hướng C, mục 2 của
`_guidance/fever-detect-agent-task.md`), và là nguồn thật duy nhất cho `triage_level`/`reason_codes`/
`triggered_rules` - `fever_stage_machine.py` (Bước 2) chỉ chạy 1 provisional scan rất nhẹ để biết khi
nào NÊN GỌI module này, không tự sinh kết luận triage chính thức.

Nguyên tắc bất biến (KM §0.2): mức triage cuối = mức CAO NHẤT trong mọi rule khớp; không rule nào
được hạ mức đã đặt bởi rule khác. `evaluate()` áp đúng nguyên tắc này bằng cách chạy TOÀN BỘ catalog
rồi lấy max, không short-circuit ở rule đầu tiên khớp.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from src.services.engines.fever_stage_machine import age_in_months

TriageLevel = Literal["EMERGENCY", "EARLY_VISIT", "SELF_CARE"]
TimeTarget = Literal["now", "within_4h", "within_24h", "monitor"]

_LEVEL_RANK: dict[TriageLevel, int] = {"SELF_CARE": 0, "EARLY_VISIT": 1, "EMERGENCY": 2}
_TIME_RANK: dict[TimeTarget, int] = {"now": 0, "within_4h": 1, "within_24h": 2, "monitor": 3}


@dataclass(frozen=True, slots=True)
class RuleMatch:
    rule_id: str
    reason_codes: tuple[str, ...]
    level: TriageLevel
    time_target: TimeTarget


@dataclass(frozen=True, slots=True)
class RuleEngineResult:
    triage_level: TriageLevel
    time_target: TimeTarget
    reason_codes: tuple[str, ...]
    triggered_rules: tuple[str, ...]
    matches: tuple[RuleMatch, ...] = field(default_factory=tuple)


def _is_true(value: object) -> bool:
    return value is True or value == "true"


def _is_filled(value: object) -> bool:
    return value is not None and value != "unknown" and value != ""


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


def _fever_present(answers: dict[str, object]) -> bool:
    return _is_true(answers.get("fever_reported")) or answers.get("fever_status") in ("objective", "subjective")


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


def _travel_within_months(answers: dict[str, object], months: float) -> bool | None:
    history = answers.get("travel_history_12m")
    if not isinstance(history, (list, tuple)) or not history:
        return None
    deltas = [_months_since(entry.get("return_date")) for entry in history if isinstance(entry, dict)]
    deltas = [delta for delta in deltas if delta is not None]
    if not deltas:
        return None
    return min(deltas) <= months


CHRONIC_SEVERE = frozenset(
    {"cardiac", "pulmonary", "renal", "hepatic", "hematologic_thalassemia", "malignancy"}
)


# ---------------------------------------------------------------------------------------------
# R-E-xx — EMERGENCY / now (KM §6.1)
# ---------------------------------------------------------------------------------------------


def _r_e_01(a: dict[str, object]) -> RuleMatch | None:
    if _in(a.get("consciousness_level"), frozenset({"difficult_to_rouse", "unresponsive"})):
        return RuleMatch("R-E-01", ("RF-01",), "EMERGENCY", "now")
    return None


def _r_e_02(a: dict[str, object]) -> RuleMatch | None:
    complex_features = _array_has_any(
        a.get("seizure_features"), frozenset({"focal", "duration_gt_5min", "recurrent_24h", "incomplete_recovery"})
    )
    if _is_true(a.get("seizure_occurred")) or _is_true(a.get("seizure_active_now")) or complex_features:
        codes = ["RF-02"]
        if complex_features:
            codes.append("RF-03")
        return RuleMatch("R-E-02", tuple(codes), "EMERGENCY", "now")
    return None


def _r_e_03(a: dict[str, object]) -> RuleMatch | None:
    if _is_true(a.get("neck_stiffness")) or _is_true(a.get("bulging_fontanelle")) or _is_true(a.get("photophobia")):
        return RuleMatch("R-E-03", ("RF-04",), "EMERGENCY", "now")
    return None


def _r_e_04(a: dict[str, object]) -> RuleMatch | None:
    age_months = age_in_months(a)
    if _is_true(a.get("new_confusion")) and age_months is not None and age_months >= 16 * 12:
        return RuleMatch("R-E-04", ("RF-05",), "EMERGENCY", "now")
    return None


def _r_e_05(a: dict[str, object]) -> RuleMatch | None:
    if _is_true(a.get("focal_neuro_deficit")):
        return RuleMatch("R-E-05", ("RF-06",), "EMERGENCY", "now")
    return None


def _r_e_06(a: dict[str, object]) -> RuleMatch | None:
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


def _r_e_07(a: dict[str, object]) -> RuleMatch | None:
    age_months = age_in_months(a)
    young = age_months is not None and age_months < 5 * 12
    if young and (_is_true(a.get("chest_indrawing")) or _is_true(a.get("nasal_flaring_grunting"))):
        return RuleMatch("R-E-07", ("RF-09",), "EMERGENCY", "now")
    return None


def _r_e_08(a: dict[str, object]) -> RuleMatch | None:
    spo2 = a.get("spo2_percent")
    if isinstance(spo2, (int, float)) and spo2 <= 92:
        return RuleMatch("R-E-08", ("RF-11",), "EMERGENCY", "now")
    return None


def _r_e_09(a: dict[str, object]) -> RuleMatch | None:
    if _is_true(a.get("cold_clammy_skin")) or _is_true(a.get("capillary_refill_ge_3s")):
        return RuleMatch("R-E-09", ("RF-13",), "EMERGENCY", "now")
    return None


def _r_e_10(a: dict[str, object]) -> RuleMatch | None:
    if a.get("urine_output") == "none_gt_6h":
        return RuleMatch("R-E-10", ("RF-14",), "EMERGENCY", "now")
    return None


def _r_e_11(a: dict[str, object]) -> RuleMatch | None:
    if a.get("feeding_intake") == "unable" or a.get("vomiting_severity") == "unable_to_keep_fluids":
        return RuleMatch("R-E-11", ("RF-15",), "EMERGENCY", "now")
    return None


def _r_e_12(a: dict[str, object]) -> RuleMatch | None:
    if _is_true(a.get("non_blanching_rash")):
        return RuleMatch("R-E-12", ("RF-18",), "EMERGENCY", "now")
    return None


def _r_e_13(a: dict[str, object]) -> RuleMatch | None:
    if _is_true(a.get("mucosal_bleeding")) or _is_true(a.get("gi_bleeding")):
        codes = []
        if _is_true(a.get("mucosal_bleeding")):
            codes.append("RF-19")
        if _is_true(a.get("gi_bleeding")):
            codes.append("RF-20")
        return RuleMatch("R-E-13", tuple(codes), "EMERGENCY", "now")
    return None


def _r_e_14(a: dict[str, object]) -> RuleMatch | None:
    age_months = age_in_months(a)
    if age_months is not None and age_months < 3 and _fever_present(a):
        return RuleMatch("R-E-14", ("RF-22",), "EMERGENCY", "now")
    return None


def _r_e_15(a: dict[str, object], *, conservatism_tier: int) -> RuleMatch | None:
    temp = a.get("temp_c")
    hypothermia = (isinstance(temp, (int, float)) and temp < 36.0) or _is_true(a.get("hypothermia_reported"))
    if hypothermia and conservatism_tier >= 1:
        return RuleMatch("R-E-15", ("RF-24",), "EMERGENCY", "now")
    return None


def _r_e_16(a: dict[str, object]) -> RuleMatch | None:
    temp = a.get("temp_c")
    if not (isinstance(temp, (int, float)) and temp >= 40.0):
        return None
    heat_exposure = _is_true(a.get("heat_exposure_context"))
    if a.get("consciousness_level") not in ("alert", None) or heat_exposure:
        return RuleMatch("R-E-16", ("RF-25",), "EMERGENCY", "now")
    return None


def _r_e_17(a: dict[str, object]) -> RuleMatch | None:
    if _is_true(a.get("worse_after_defervescence")):
        return RuleMatch("R-E-17", ("RF-29",), "EMERGENCY", "now")
    return None


def _r_e_18(a: dict[str, object]) -> RuleMatch | None:
    at_risk = _is_true(a.get("known_neutropenia")) or _array_has_any(
        a.get("immunocompromise_cause"), frozenset({"chemotherapy_6w"})
    )
    if not at_risk:
        return None
    temp = a.get("temp_c")
    threshold_met = isinstance(temp, (int, float)) and temp >= 38.3
    if threshold_met or _is_true(a.get("fever_reported")):
        return RuleMatch("R-E-18", ("RF-30",), "EMERGENCY", "now")
    return None


def _r_e_19(a: dict[str, object]) -> RuleMatch | None:
    if not _is_true(a.get("malaria_risk_area")):
        return None
    within_month = _travel_within_months(a, 1)
    if within_month is None or within_month:
        return RuleMatch("R-E-19", ("RF-35",), "EMERGENCY", "now")
    return None


def _r_e_20(a: dict[str, object]) -> RuleMatch | None:
    if a.get("abdominal_pain_severity") == "severe" or _is_true(a.get("abdominal_guarding")):
        return RuleMatch("R-E-20", ("RF-39",), "EMERGENCY", "now")
    return None


def _r_e_21(a: dict[str, object], *, other_emergency_matched: bool) -> RuleMatch | None:
    if not (_is_true(a.get("is_pregnant")) or _is_true(a.get("postpartum_6w"))):
        return None
    flags = a.get("obstetric_red_flags")
    has_flags = isinstance(flags, (list, tuple)) and len(flags) > 0
    if has_flags or other_emergency_matched:
        return RuleMatch("R-E-21", ("RF-32",), "EMERGENCY", "now")
    return None


_EMERGENCY_RULES_SIMPLE = (
    _r_e_01, _r_e_02, _r_e_03, _r_e_04, _r_e_05, _r_e_06, _r_e_07, _r_e_08, _r_e_09, _r_e_10,
    _r_e_11, _r_e_12, _r_e_13, _r_e_14, _r_e_16, _r_e_17, _r_e_18, _r_e_19, _r_e_20,
)


# ---------------------------------------------------------------------------------------------
# R-V-xx — EARLY_VISIT (KM §6.1)
# ---------------------------------------------------------------------------------------------


def _r_v_01(a: dict[str, object]) -> RuleMatch | None:
    age_months = age_in_months(a)
    if age_months is None or not (3 <= age_months < 6):
        return None
    temp = a.get("temp_c")
    if isinstance(temp, (int, float)) and temp >= 39.0:
        return RuleMatch("R-V-01", ("RF-23",), "EARLY_VISIT", "within_24h")
    return None


def _r_v_02(a: dict[str, object]) -> RuleMatch | None:
    duration = a.get("fever_duration_days")
    if isinstance(duration, (int, float)) and duration >= 5:
        return RuleMatch("R-V-02", ("RF-26",), "EARLY_VISIT", "within_24h")
    return None


def _r_v_03(a: dict[str, object]) -> RuleMatch | None:
    duration = a.get("fever_duration_days")
    if isinstance(duration, (int, float)) and duration >= 7:
        return RuleMatch("R-V-03", ("RF-27",), "EARLY_VISIT", "within_24h")
    return None


def _r_v_04(a: dict[str, object]) -> RuleMatch | None:
    if _is_true(a.get("rigors")):
        return RuleMatch("R-V-04", ("RF-28",), "EARLY_VISIT", "within_24h")
    return None


def _r_v_05(a: dict[str, object]) -> RuleMatch | None:
    spo2 = a.get("spo2_percent")
    spo2_band = isinstance(spo2, (int, float)) and 93 <= spo2 <= 95
    if spo2_band or _is_true(a.get("rapid_breathing")):
        return RuleMatch("R-V-05", ("RF-11",), "EARLY_VISIT", "within_4h")
    return None


def _r_v_06(a: dict[str, object]) -> RuleMatch | None:
    signs = a.get("dehydration_signs")
    many_signs = isinstance(signs, (list, tuple)) and len(signs) >= 2
    reduced_combo = a.get("urine_output") == "reduced" and a.get("feeding_intake") == "reduced"
    if many_signs or reduced_combo:
        return RuleMatch("R-V-06", ("RF-16",), "EARLY_VISIT", "within_4h")
    return None


def _r_v_07(a: dict[str, object]) -> RuleMatch | None:
    if _is_true(a.get("dizziness_on_standing")):
        return RuleMatch("R-V-07", ("RF-17",), "EARLY_VISIT", "within_24h")
    return None


def _r_v_08(a: dict[str, object]) -> RuleMatch | None:
    if _is_true(a.get("jaundice_new")):
        return RuleMatch("R-V-08", ("RF-21",), "EARLY_VISIT", "within_24h")
    return None


def _r_v_09(a: dict[str, object]) -> RuleMatch | None:
    if _is_true(a.get("immunocompromised")) and not _is_true(a.get("known_neutropenia")):
        return RuleMatch("R-V-09", ("RF-31",), "EARLY_VISIT", "within_4h")
    return None


def _r_v_10(a: dict[str, object]) -> RuleMatch | None:
    if _is_true(a.get("is_pregnant")) or _is_true(a.get("postpartum_6w")):
        return RuleMatch("R-V-10", ("RF-32",), "EARLY_VISIT", "within_4h")
    return None


def _r_v_11(a: dict[str, object]) -> RuleMatch | None:
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


def _r_v_12(a: dict[str, object]) -> RuleMatch | None:
    if _array_has_any(a.get("chronic_conditions"), CHRONIC_SEVERE):
        return RuleMatch("R-V-12", ("RF-36",), "EARLY_VISIT", "within_24h")
    return None


def _r_v_13(a: dict[str, object]) -> RuleMatch | None:
    age_months = age_in_months(a)
    if age_months is not None and age_months >= 75 * 12:
        return RuleMatch("R-V-13", ("RF-37",), "EARLY_VISIT", "within_24h")
    return None


def _r_v_14(a: dict[str, object]) -> RuleMatch | None:
    if a.get("vomiting_severity") == "frequent":
        return RuleMatch("R-V-14", ("RF-40",), "EARLY_VISIT", "within_4h")
    return None


def _r_v_15(a: dict[str, object]) -> RuleMatch | None:
    if _is_true(a.get("joint_limb_swelling")) or _is_true(a.get("non_weight_bearing")):
        return RuleMatch("R-V-15", ("RF-41",), "EARLY_VISIT", "within_24h")
    return None


def _r_v_16(a: dict[str, object]) -> RuleMatch | None:
    age_months = age_in_months(a)
    young = age_months is not None and age_months < 5 * 12
    has_clear_source = _is_true(a.get("localized_infection_signs")) or any(
        _is_true(a.get(key)) for key in ("sore_throat", "ear_pain", "cough")
    )
    if young and _fever_present(a) and not has_clear_source:
        return RuleMatch("R-V-16", ("RF-42",), "EARLY_VISIT", "within_24h")
    return None


def _r_v_17(a: dict[str, object]) -> RuleMatch | None:
    if _is_true(a.get("localized_infection_signs")):
        return RuleMatch("R-V-17", ("RF-43",), "EARLY_VISIT", "within_24h")
    return None


def _r_v_18(a: dict[str, object]) -> RuleMatch | None:
    concern = a.get("caregiver_concern_level")
    high_concern = isinstance(concern, (int, float)) and concern >= 8
    if high_concern or _is_true(a.get("looks_very_unwell")):
        return RuleMatch("R-V-18", ("RF-44",), "EARLY_VISIT", "within_4h")
    return None


def _r_v_19(a: dict[str, object]) -> RuleMatch | None:
    if _is_true(a.get("chest_pain")) or _is_true(a.get("hemoptysis")):
        return RuleMatch("R-V-19", ("RF-12",), "EARLY_VISIT", "within_4h")
    return None


def _r_v_20(a: dict[str, object]) -> RuleMatch | None:
    if not _is_true(a.get("malaria_risk_area")):
        return None
    within_month = _travel_within_months(a, 1)
    if within_month is False:
        return RuleMatch("R-V-20", ("RF-35",), "EARLY_VISIT", "within_24h")
    return None


_EARLY_VISIT_RULES = (
    _r_v_01, _r_v_02, _r_v_03, _r_v_04, _r_v_05, _r_v_06, _r_v_07, _r_v_08, _r_v_09, _r_v_10,
    _r_v_11, _r_v_12, _r_v_13, _r_v_14, _r_v_15, _r_v_16, _r_v_17, _r_v_18, _r_v_19, _r_v_20,
)


def _r_g_01(a: dict[str, object]) -> RuleMatch | None:
    if _is_true(a.get("lives_alone")) or a.get("caregiver_available") == "false":
        return RuleMatch("R-G-01", ("RF-38",), "EARLY_VISIT", "within_24h")
    return None


def conservatism_tier(a: dict[str, object]) -> int:
    """KM §5.1-5.2 - hệ số thận trọng theo quần thể. Dùng nội bộ cho R-E-15 (hạ thân nhiệt)."""
    age_months = age_in_months(a)
    if age_months is not None and age_months < 3:
        return 2
    if _is_true(a.get("known_neutropenia")) or _array_has_any(
        a.get("immunocompromise_cause"), frozenset({"chemotherapy_6w"})
    ):
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


def self_care_checklist_satisfied(a: dict[str, object]) -> bool:
    """KM §5.4 - checklist bắt buộc để cho phép SELF_CARE, áp trên `answers` đầy đủ (không phụ thuộc
    cluster/stage, khác `fever_stage_machine.self_care_checklist_satisfied`)."""
    age_months = age_in_months(a)
    if age_months is None or age_months < 6:
        return False
    duration = a.get("fever_duration_days")
    if isinstance(duration, (int, float)) and duration >= 5:
        return False
    if a.get("consciousness_level") != "alert":
        return False
    if a.get("feeding_intake") not in ("normal", "reduced"):
        return False
    if a.get("urine_output") != "normal":
        return False
    self_sufficient_adult = age_months >= 16 * 12 and a.get("reporter_type") == "self"
    if not (_is_true(a.get("caregiver_available")) or self_sufficient_adult):
        return False
    if not _is_true(a.get("can_return_for_followup")):
        return False
    return True


def evaluate(answers: dict[str, object]) -> RuleEngineResult:
    """Chạy TOÀN BỘ catalog KM §6.1, lấy mức triage CAO NHẤT trong các rule khớp (KM §0.2). Không
    short-circuit ở rule đầu tiên - mọi rule khớp đều được ghi vào `matches`."""
    tier = conservatism_tier(answers)

    emergency_matches = [rule(answers) for rule in _EMERGENCY_RULES_SIMPLE]
    hypothermia_match = _r_e_15(answers, conservatism_tier=tier)
    any_emergency_so_far = any(match is not None for match in emergency_matches) or hypothermia_match is not None
    obstetric_match = _r_e_21(answers, other_emergency_matched=any_emergency_so_far)

    matches: list[RuleMatch] = [m for m in (*emergency_matches, hypothermia_match, obstetric_match) if m is not None]
    matches.extend(m for rule in _EARLY_VISIT_RULES if (m := rule(answers)) is not None)

    g01 = _r_g_01(answers)
    if g01 is not None:
        matches.append(g01)

    if not matches:
        if self_care_checklist_satisfied(answers):
            matches.append(RuleMatch("R-S-01", (), "SELF_CARE", "monitor"))
        else:
            # R-G-02(a) + CS Part 6 "Dừng hẳn" (c): không bao giờ mặc định về SELF_CARE khi checklist
            # §5.4 chưa thoả (kể cả ở tier 0) - an toàn hơn luôn là EARLY_VISIT, không phải SELF_CARE
            # (P0-6: mơ hồ giữa 2 mức luôn chọn mức thận trọng hơn).
            matches.append(RuleMatch("R-G-02", (), "EARLY_VISIT", "within_24h"))

    best_level: TriageLevel = max((m.level for m in matches), key=lambda level: _LEVEL_RANK[level])
    winning = [m for m in matches if m.level == best_level]
    best_time_target: TimeTarget = min((m.time_target for m in winning), key=lambda t: _TIME_RANK[t])

    # `triggered_rules` chỉ gồm rule Ở ĐÚNG mức thắng (best_level) - đúng ví dụ E4 trong CS Part 8:
    # rigors=true khớp cả R-V-04 (EARLY_VISIT), nhưng khi đã có R-E-19 (EMERGENCY) thắng, tài liệu
    # chỉ liệt kê triggered_rules=["R-E-19"]. `reason_codes` thì gom TỪ MỌI rule khớp (kể cả mức
    # thấp hơn) làm bằng chứng bổ trợ - cùng ví dụ E4, reason_codes vẫn gồm cả RF-35 (R-E-19) lẫn
    # RF-28 (R-V-04) dù R-V-04 không phải rule "thắng".
    reason_codes: list[str] = []
    triggered_rules: list[str] = []
    for match in matches:
        if match.level == best_level:
            triggered_rules.append(match.rule_id)
        for code in match.reason_codes:
            if code not in reason_codes:
                reason_codes.append(code)

    return RuleEngineResult(
        triage_level=best_level,
        time_target=best_time_target,
        reason_codes=tuple(reason_codes),
        triggered_rules=tuple(triggered_rules),
        matches=tuple(matches),
    )
