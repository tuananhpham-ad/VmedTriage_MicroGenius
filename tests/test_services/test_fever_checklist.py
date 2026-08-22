"""Checkpoint 1 (_guidance/fever-detect-agent-task.md Bước 1) — field registry + question clusters.

Golden: đếm thủ công field tại `docs/medical_knowledge/fever-knowledge-model.md` §3.2-3.11 (loại field
metadata/derived ở §3.12 - đó là output của rule engine, không phải câu hỏi hội thoại) và mã câu hỏi
tại `docs/medical_knowledge/fever-conversation-specification.md` Part 3. Số đếm ghi CỐ ĐỊNH dưới đây,
không tính động từ chính registry - nếu registry thiếu field/cụm, test phải fail.

Lưu ý `tri_state`: KM §3.1 điểm 1 áp tri-state cho field có kiểu dữ liệu tri-state/boolean, KHÔNG áp
cho mọi field M0/M1 (vd `consciousness_level` là M0 nhưng là enum). Test dưới đây kiểm theo đúng quy
tắc đó, không giả định "mọi M0/M1 đều tri-state".
"""

from __future__ import annotations

from src.services.checklists import fever_checklist as fc

EXPECTED_FIELD_COUNT = 101

# Chép nguyên văn mã cụm CS Part 3. Thứ tự khác tài liệu ở HAI điểm, cả hai có chủ đích (2026-08-22):
#  1. Stage `E` đứng ĐẦU: ba cụm nguy kịch phổ quát (Q3-06/07/12) chuyển khỏi 3A lên trước nhân
#     khẩu, để câu hỏi CHỦ ĐỘNG đầu tiên là quét cấp cứu chứ không phải hỏi tuổi.
#  2. `Q0-02` (giới) đã gộp vào `Q0-01`: tách làm hai cụm tốn thêm một lượt mà không đổi độ phủ.
EXPECTED_CLUSTER_IDS: tuple[str, ...] = (
    "Q3-06", "Q3-07", "Q3-12",
    "Q0-01",
    "Q1-01", "Q1-02", "Q1-03",
    "Q2-01", "Q2-02", "Q2-03", "Q2-04", "Q2-05",
    "Q3-01", "Q3-03", "Q3-04", "Q3-05", "Q3-08", "Q3-09", "Q3-11", "Q3-13",
    "Q3-01b", "Q3-08b", "Q3-02", "Q3-13b", "Q3-14",
    "Q4-00", "Q4-01", "Q4-01b", "Q4-02", "Q4-03", "Q4-04", "Q4-05", "Q4-06", "Q4-07", "Q4-08",
    "Q5-01", "Q5-02", "Q5-03", "Q5-04", "Q5-05a", "Q5-05b", "Q5-06", "Q5-07",
)

# Field có Data type = "tri-state" hoặc "boolean" trong KM §3.2-3.11 - đây mới là tập bắt buộc
# tri_state=True, không phải toàn bộ field M0/M1.
EXPECTED_TRI_STATE_KEYS: frozenset[str] = frozenset(
    {
        "lives_alone", "caregiver_available", "can_return_for_followup",
        "fever_reported", "rigors", "hypothermia_reported", "antipyretic_taken", "worse_after_defervescence",
        "new_confusion", "looks_very_unwell",
        "rapid_breathing", "chest_indrawing", "nasal_flaring_grunting", "cyanosis", "stridor_or_drooling",
        "chest_pain", "hemoptysis",
        "cold_clammy_skin", "capillary_refill_ge_3s", "dizziness_on_standing",
        "seizure_occurred", "seizure_active_now", "neck_stiffness", "photophobia", "severe_headache",
        "bulging_fontanelle", "focal_neuro_deficit",
        "non_blanching_rash", "rash_present", "mucosal_bleeding", "gi_bleeding", "jaundice_new",
        "localized_infection_signs",
        "abdominal_guarding", "diarrhea", "bloody_stool", "urinary_symptoms", "sore_throat", "ear_pain",
        "cough", "joint_limb_swelling", "non_weight_bearing", "myalgia_retroorbital_pain",
        "immunocompromised", "known_neutropenia", "is_pregnant", "postpartum_6w", "recent_surgery_30d",
        "surgical_site_signs", "recent_wound_or_bite", "malaria_risk_area", "mosquito_exposure",
        "sick_contact", "recent_vaccination_48h",
        "nsaid_use", "anticoagulant_use", "antibiotic_current", "new_medication_6w",
    }
)


# --- field registry ------------------------------------------------------------------------


def test_field_count_matches_knowledge_model():
    assert len(fc.FEVER_FIELDS) == EXPECTED_FIELD_COUNT


def test_field_keys_are_unique():
    keys = [field.key for field in fc.FEVER_FIELDS]
    assert len(keys) == len(set(keys))


def test_tri_state_flag_matches_data_type_not_tier():
    actual_tri_state_keys = {field.key for field in fc.FEVER_FIELDS if field.tri_state}
    assert actual_tri_state_keys == EXPECTED_TRI_STATE_KEYS


def test_tri_state_fields_are_never_labelled_as_non_boolean_by_accident():
    # Field M0 nổi tiếng là enum/number, không phải tri-state - chốt cứng để tránh hồi quy.
    non_tri_state_examples = ["consciousness_level", "temp_c", "age_value", "fever_status", "urine_output"]
    for key in non_tri_state_examples:
        assert fc.FIELDS_BY_KEY[key].tri_state is False, key


# --- question clusters -----------------------------------------------------------------------


def test_cluster_ids_match_conversation_spec_order():
    actual_ids = tuple(cluster.id for cluster in fc.QUESTION_CLUSTERS)
    assert actual_ids == EXPECTED_CLUSTER_IDS


def test_cluster_fields_all_exist_in_registry():
    for cluster in fc.QUESTION_CLUSTERS:
        for key in cluster.fields:
            assert key in fc.FIELDS_BY_KEY, f"{cluster.id} tham chiếu field lạ: {key}"


def test_cluster_stage_is_valid_and_batch_negation_only_on_stage_3():
    for cluster in fc.QUESTION_CLUSTERS:
        assert cluster.stage in {"E", "0", "1", "2", "3A", "3B", "4", "5"}, cluster.id
        if cluster.stage in {"E", "3A", "3B"}:
            assert cluster.batch_negation is True, f"{cluster.id} phải batch_negation=True (CS §3.3A)"
        else:
            assert cluster.batch_negation is False, f"{cluster.id} không thuộc Stage E/3A/3B, không được batch_negation"


def test_clusters_for_stage_helper_matches_manual_filter():
    stage_3a_ids = [c.id for c in fc.QUESTION_CLUSTERS if c.stage == "3A"]
    assert [c.id for c in fc.clusters_for_stage("3A")] == stage_3a_ids
    # 11 -> 8: ba cụm nguy kịch phổ quát đã chuyển sang stage `E` (2026-08-22).
    assert len(stage_3a_ids) == 8
    assert [c.id for c in fc.clusters_for_stage("E")] == ["Q3-06", "Q3-07", "Q3-12"]
