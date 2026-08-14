"""`common_safety/` - phần an toàn dùng chung, và ranh giới không được vượt.

Hai thứ file này canh giữ:

1. **Chiều phụ thuộc.** `common_safety` không được biết gì về fever/generic. Vi phạm chiều này thì
   protocol thứ ba lại phải kéo theo kiến thức về sốt, và cả việc tách ra thành vô nghĩa.
2. **Refactor không đổi hành vi.** Rule đỏ được CHUYỂN chỗ chứ không viết lại, nên thứ tự và danh
   tính của catalog fever phải y hệt trước khi tách - thứ tự là hợp đồng thật (`r_e_21` đọc
   `matches_so_far`), không phải chi tiết trình bày.
"""

from __future__ import annotations

import ast
from pathlib import Path

from src.services.engines.fever_protocol import FEVER_PROTOCOL
from src.services.engines.generic_protocol import GENERIC_PROTOCOL
from src.services.symptom_protocol import rule_engine
from src.services.symptom_protocol.common_safety import fields as common_fields
from src.services.symptom_protocol.common_safety import predicates
from src.services.symptom_protocol.common_safety import rules as common_rules

_COMMON_SAFETY_DIR = Path(__file__).resolve().parents[2] / "src" / "services" / "symptom_protocol" / "common_safety"


# --- ranh giới phụ thuộc -------------------------------------------------------------------------


def test_common_safety_never_imports_a_specific_protocol():
    # Duyệt bằng `ast` chứ không quét chuỗi: docstring của chính các file này có nhắc tên "fever"
    # (đúng chỗ - để giải thích vì sao KHÔNG được import), quét chuỗi sẽ báo động nhầm.
    for path in _COMMON_SAFETY_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        modules: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
        for module in modules:
            assert "fever" not in module, f"{path.name} import {module}"
            assert "generic" not in module, f"{path.name} import {module}"


# --- catalog fever giữ NGUYÊN thứ tự sau khi chuyển rule ra dùng chung ---------------------------

EXPECTED_FEVER_CATALOG: tuple[str, ...] = (
    "r_e_01", "r_e_02", "r_e_03", "r_e_04", "r_e_05", "r_e_06", "r_e_07", "r_e_08", "r_e_09",
    "r_e_10", "r_e_11", "r_e_12", "r_e_13", "r_e_14", "r_e_16", "r_e_17", "r_e_18", "r_e_19",
    "r_e_20", "r_e_15", "r_e_21",
    "r_v_01", "r_v_02", "r_v_03", "r_v_04", "r_v_05", "r_v_06", "r_v_07", "r_v_08", "r_v_09",
    "r_v_10", "r_v_11", "r_v_12", "r_v_13", "r_v_14", "r_v_15", "r_v_16", "r_v_17", "r_v_18",
    "r_v_19", "r_v_20", "r_g_01",
)


def test_fever_rule_catalog_order_is_unchanged_after_extracting_common_rules():
    actual = tuple(rule.__name__.lstrip("_") for rule in FEVER_PROTOCOL.rule_catalog)
    assert actual == EXPECTED_FEVER_CATALOG


def test_obstetric_rule_still_runs_after_every_other_emergency_rule():
    """`r_e_21` khớp khi ĐÃ có rule EMERGENCY khác khớp - nó phải đứng sau, nếu không thai phụ có dấu
    hiệu nguy kịch sẽ không được gắn `RF-32`."""
    for protocol in (FEVER_PROTOCOL, GENERIC_PROTOCOL):
        names = [rule.__name__.lstrip("_") for rule in protocol.rule_catalog]
        emergency_last = max(index for index, name in enumerate(names) if name.startswith("r_e_"))
        assert names.index("r_e_21") == emergency_last, protocol.name


def test_pregnant_patient_with_another_red_flag_gets_obstetric_reason_code():
    result = rule_engine.evaluate(GENERIC_PROTOCOL, {"is_pregnant": "true", "cyanosis": "true"})
    assert result.triage_level == "EMERGENCY"
    assert "RF-32" in result.reason_codes


# --- vị từ dùng chung ----------------------------------------------------------------------------


def test_as_float_reads_the_string_form_every_agent_answer_actually_has():
    """Đây là lỗi an toàn đã xảy ra thật: `_coerce_enum` biến `temp_c` thành `"40.5"`, còn rule kiểm
    `isinstance(x, (int, float))` nên 10 rule theo nhiệt độ IM LẶNG không bao giờ khớp."""
    assert predicates.as_float("40.5") == 40.5
    assert predicates.as_float(40.5) == 40.5
    assert predicates.as_float("không rõ") is None
    assert predicates.as_float(True) is None  # bool là int trong Python - không được nhận nhầm


def test_age_in_months_normalises_every_unit():
    assert predicates.age_in_months({"age_value": "2", "age_unit": "year"}) == 24
    assert predicates.age_in_months({"age_value": "6", "age_unit": "month"}) == 6
    assert predicates.age_in_months({"age_value": "60", "age_unit": "day"}) == 2
    assert predicates.age_in_months({"age_value": "3"}) is None  # thiếu đơn vị -> không đoán


# --- field dùng chung ----------------------------------------------------------------------------


def test_both_protocols_share_the_same_red_flag_field_objects():
    """Cùng một OBJECT, không phải hai bản sao giống nhau - bản sao là thứ sẽ lệch nhau về sau."""
    for spec in common_fields.NEUROLOGICAL_FIELDS:
        assert FEVER_PROTOCOL.fields_by_key[spec.key] is spec
        assert GENERIC_PROTOCOL.fields_by_key[spec.key] is spec


def test_immunocompromised_hint_forbids_inferring_from_a_disease_label():
    """Không suy "có HIV" thành "suy giảm miễn dịch": HIV điều trị ổn không thuộc nhóm nguy cơ này,
    và suy diễn sai vừa đổi mức triage vừa dán nhãn sai cho người bệnh."""
    hint = common_fields.COMMON_FIELDS_BY_KEY["immunocompromised"].hint
    assert "HIV" in hint
    assert "chronic_conditions" in hint


def test_common_reason_code_labels_cover_every_code_the_common_rules_emit():
    emitted = set()
    for rule in (*common_rules.EMERGENCY_RULES, common_rules.r_e_21, *common_rules.EARLY_VISIT_RULES):
        emitted.update(_codes_of(rule))
    assert emitted <= set(common_rules.REASON_CODE_LABELS)


def _codes_of(rule) -> set[str]:
    """Ép rule khớp bằng một hồ sơ "dương tính mọi thứ" rồi đọc mã nó phát ra."""
    answers = {
        key: "true" for key in
        ("seizure_occurred", "seizure_active_now", "neck_stiffness", "focal_neuro_deficit", "cyanosis",
         "stridor_or_drooling", "cold_clammy_skin", "capillary_refill_ge_3s", "non_blanching_rash",
         "mucosal_bleeding", "gi_bleeding", "new_confusion", "chest_indrawing", "rapid_breathing",
         "dizziness_on_standing", "jaundice_new", "immunocompromised", "is_pregnant",
         "recent_surgery_30d", "joint_limb_swelling", "localized_infection_signs", "looks_very_unwell",
         "chest_pain", "lives_alone", "abdominal_guarding")
    }
    answers.update({
        "consciousness_level": "unresponsive", "breathing_difficulty": "severe", "spo2_percent": "90",
        "urine_output": "none_gt_6h", "feeding_intake": "unable", "vomiting_severity": "unable_to_keep_fluids",
        "abdominal_pain_severity": "severe", "age_value": "80", "age_unit": "year",
        "chronic_conditions": ["cardiac"], "indwelling_device": ["catheter"],
        "obstetric_red_flags": ["bleeding"], "dehydration_signs": ["dry_lips", "sunken_eyes"],
    })
    match = rule(answers, ())
    return set(match.reason_codes) if match else set()
