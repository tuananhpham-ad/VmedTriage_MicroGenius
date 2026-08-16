"""Checkpoint 4 (_guidance/fever-detect-agent-task.md Bước 4) — LLM extraction theo cụm.

LLM thật KHÔNG được gọi trong test này (không xác định, tốn tiền, CI không có key): mock
`provider_router.complete`, kiểm cả PROMPT GỬI ĐI (chỉ chứa field của cụm hiện tại, không phải cả 101
field) lẫn OUTPUT XỬ LÝ VỀ (tri-state chuẩn hoá đúng, batch-negation gán `false` đồng loạt, không có
khoá quyết định triage lẫn vào).

Golden case dùng lại input User của ca O1 (Part 8 CS) - mock LLM trả đúng JSON mà tài liệu ghi nhận
đã trích được cho cụm Q3-01 (`consciousness_level`), rồi kiểm hậu xử lý của `extract_cluster` cho
đúng - đây là ranh giới hợp lý của Checkpoint 4: verify hậu xử lý/schema, không verify "LLM có hiểu
tiếng Việt hay không" (việc đó chỉ kiểm được bằng LLM thật ở Checkpoint 6).
"""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from src import paths
from src.services.checklists.fever_checklist import CLUSTERS_BY_ID
from src.services.engines.fever_protocol import FEVER_PROTOCOL
from src.services.infra import fever_stage_log, provider_router
from src.services.symptom_protocol import intake_agent as _engine
from src.services.symptom_protocol import retraction
from tests.helpers import fever_api as agent

O1_USER_MESSAGE = (
    "Con em 3 tuổi, sốt 2 ngày 38,5 độ, bé vẫn tỉnh táo, chơi đùa bình thường, ăn uống tốt, "
    "không có gì bất thường khác cả."
)


@pytest.fixture(autouse=True)
def _isolated_log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LOGS_DIR", tmp_path)
    yield


def _fake_complete(response_json: dict, *, provider: str = "openrouter", model: str = "openai/gpt-4o-mini"):
    fake = Mock()
    fake.return_value = provider_router.CompletionResult(text=json.dumps(response_json), provider=provider, model=model)
    return fake


# --- đúng tool: đúng số call, đúng prompt chỉ chứa field của cụm hiện tại -----------------------


def test_extract_cluster_calls_provider_exactly_once(monkeypatch):
    fake = _fake_complete({"consciousness_level": "alert"})
    monkeypatch.setattr(provider_router, "complete", fake)

    cluster = CLUSTERS_BY_ID["Q3-01"]
    agent.extract_cluster(cluster, O1_USER_MESSAGE)

    assert fake.call_count == 1


def test_extract_cluster_prompt_only_contains_current_cluster_fields(monkeypatch):
    fake = _fake_complete({"consciousness_level": "alert"})
    monkeypatch.setattr(provider_router, "complete", fake)

    cluster = CLUSTERS_BY_ID["Q3-01"]  # fields: consciousness_level, social_response_child
    agent.extract_cluster(cluster, O1_USER_MESSAGE)

    system_prompt = fake.call_args.args[0][0]["content"]
    assert "consciousness_level" in system_prompt
    assert "social_response_child" in system_prompt
    # Không được lẫn field của cụm KHÁC (vd Q3-06 hô hấp) vào cùng 1 lượt gọi.
    assert "breathing_difficulty" not in system_prompt
    assert "non_blanching_rash" not in system_prompt


def test_extract_cluster_schema_size_matches_cluster_field_count(monkeypatch):
    cluster = CLUSTERS_BY_ID["Q3-09"]  # 3 field: urine_output, feeding_intake, vomiting_severity
    fake = _fake_complete({"urine_output": "normal", "feeding_intake": "normal", "vomiting_severity": "none"})
    monkeypatch.setattr(provider_router, "complete", fake)

    result = agent.extract_cluster(cluster, "bé vẫn đi tiểu bình thường, ăn uống tốt, không nôn")
    assert set(result.keys()) == set(cluster.fields)
    assert len(cluster.fields) == 3


# --- golden: khớp field mẫu Part 8 (ca O1, cụm Q3-01) --------------------------------------------


def test_golden_o1_consciousness_cluster_matches_part8_sample(monkeypatch):
    # JSON mẫu O1 ghi general.consciousness_level = "alert" - mock LLM trả đúng giá trị đó.
    fake = _fake_complete({"consciousness_level": "alert", "social_response_child": None})
    monkeypatch.setattr(provider_router, "complete", fake)

    cluster = CLUSTERS_BY_ID["Q3-01"]
    result = agent.extract_cluster(cluster, O1_USER_MESSAGE)

    assert result["consciousness_level"] == "alert"
    # social_response_child là enum (không tri-state) - model trả null -> bỏ qua field, KHÔNG tự
    # gán "unknown" (đó là quy ước riêng của field tri-state).
    assert "social_response_child" not in result


def test_golden_o1_feeding_cluster_matches_part8_sample(monkeypatch):
    # JSON mẫu O1 ghi general.feeding_intake = "normal" (Q3-09 phủ trường này).
    fake = _fake_complete({"urine_output": None, "feeding_intake": "normal", "vomiting_severity": None})
    monkeypatch.setattr(provider_router, "complete", fake)

    cluster = CLUSTERS_BY_ID["Q3-09"]
    result = agent.extract_cluster(cluster, O1_USER_MESSAGE)

    assert result["feeding_intake"] == "normal"


# --- batch negation ------------------------------------------------------------------------


def test_batch_negation_sets_all_cluster_fields_false_none_unknown(monkeypatch):
    message = "Dạ không, không có gì trong số đó cả."
    fake = _fake_complete({"cluster_all_negative": True, "negation_evidence": "không có gì trong số đó cả"})
    monkeypatch.setattr(provider_router, "complete", fake)

    cluster = CLUSTERS_BY_ID["Q3-04"]  # batch_negation=True, 4 field tri-state
    assert cluster.batch_negation is True

    result = agent.extract_cluster(cluster, message)

    assert set(result.values()) == {"false"}
    assert "unknown" not in result.values()
    assert len(result) == len(cluster.fields)


def test_batch_negation_partial_positive_keeps_explicit_field_true():
    cluster = CLUSTERS_BY_ID["Q3-06"]  # breathing_difficulty, cyanosis, chest_indrawing, nasal_flaring_grunting
    message = "Thở hơi mệt một chút thôi, ngoài ra không có gì cả."
    parsed = {
        "cluster_all_negative": True,
        "negation_evidence": "ngoài ra không có gì cả",
        "breathing_difficulty": "mild",
    }
    collected = agent._collect(cluster, parsed, message)

    assert collected["breathing_difficulty"] == "mild"
    assert collected["cyanosis"] == "false"
    assert collected["chest_indrawing"] == "false"


# --- Guard 1: evidence span bắt buộc cho phủ định gộp (lỗi C1, test tay 2026-08-13) --------------


def test_batch_negation_without_evidence_key_is_rejected():
    cluster = CLUSTERS_BY_ID["Q3-04"]
    collected = agent._collect(cluster, {"cluster_all_negative": True}, "Bé ăn uống tốt, không nôn.")
    # Không có `negation_evidence` -> cờ bị bỏ, mọi field giữ unknown.
    assert set(collected.values()) == {"unknown"}


def test_batch_negation_with_fabricated_evidence_is_rejected():
    """Đúng lỗi C1: tin nhắn nói về ăn uống, model bịa cờ phủ định cho cả cụm red flag thần kinh."""
    cluster = CLUSTERS_BY_ID["Q3-04"]
    parsed = {"cluster_all_negative": True, "negation_evidence": "không có dấu hiệu nào bất thường"}
    collected = agent._collect(cluster, parsed, "Bé ăn uống tốt, không nôn.")

    assert set(collected.values()) == {"unknown"}
    assert "false" not in collected.values()


def test_bare_negation_word_is_not_evidence_for_an_unasked_field():
    """Lỗi thật đo được khi chạy LLM thật (2026-08-13, gemini-3.1-flash-lite).

    Người bệnh trả lời "Không, không bị co giật" cho cụm co giật; model tiện tay ghi
    `rash_present="false"` kèm trích dẫn "Không" - đúng chữ có trong tin nhắn nên guard chấp nhận, dù
    người bệnh chưa hề được hỏi về ban. Đây là lỗi C1 ở dạng nhỏ hơn: một hạt phủ định trần chứng minh
    được MỌI thứ, tức là không chứng minh được gì."""
    message = "Không, không bị co giật"
    collected = _engine._collect_fields(
        FEVER_PROTOCOL, ("rash_present",),
        {"rash_present": {"value": "false", "evidence_span": "Không"}},
        message=message, evidence="unasked",
    )
    assert collected["rash_present"] == "unknown"


def test_specific_evidence_is_still_accepted_for_an_unasked_field():
    """Mặt đối xứng: bằng chứng NHẮC TỚI chính triệu chứng đó vẫn được nhận - guard không được siết
    tới mức loại luôn phủ định thật (ca lành tính sẽ không bao giờ kết thúc)."""
    message = "Người không nổi ban gì cả, chỉ sốt thôi"
    collected = _engine._collect_fields(
        FEVER_PROTOCOL, ("rash_present",),
        {"rash_present": {"value": "false", "evidence_span": "không nổi ban gì cả"}},
        message=message, evidence="unasked",
    )
    assert collected["rash_present"] == "false"


def test_bare_negation_still_valid_for_batch_negation_of_the_asked_cluster():
    """Trong phạm vi cụm VỪA ĐƯỢC HỎI thì "Không" là câu trả lời trực tiếp, không phải suy diễn -
    turn-scoping (`batch_negation=False` cho safety keys) đã chặn cờ này lan ra ngoài cụm."""
    cluster = CLUSTERS_BY_ID["Q3-04"]
    collected = agent._collect(
        cluster, {"cluster_all_negative": True, "negation_evidence": "Không"}, "Không",
    )
    assert set(collected.values()) == {"false"}


def test_batch_negation_evidence_tolerates_case_and_whitespace():
    cluster = CLUSTERS_BY_ID["Q3-04"]
    parsed = {"cluster_all_negative": True, "negation_evidence": "KHÔNG   có   gì  cả"}
    collected = agent._collect(cluster, parsed, "Dạ không có gì cả ạ.")

    assert set(collected.values()) == {"false"}


# --- Guard 4: enum lạ bị loại thay vì lưu nguyên văn tiếng Việt (lỗi M2) -------------------------


def test_enum_field_rejects_free_text_value():
    cluster = CLUSTERS_BY_ID["Q3-01"]  # consciousness_level, social_response_child
    collected = agent._collect(cluster, {"consciousness_level": "tỉnh táo bình thường"}, "Bé tỉnh táo bình thường ạ.")
    # Giá trị ngoài allowed_values bị loại hẳn (giữ unknown) thay vì lọt vào answers rồi làm rule
    # engine không bao giờ khớp `consciousness_level = alert`.
    assert "consciousness_level" not in collected


def test_enum_field_accepts_canonical_value_case_insensitively():
    cluster = CLUSTERS_BY_ID["Q3-01"]
    collected = agent._collect(cluster, {"consciousness_level": "Alert"}, "Bé tỉnh táo ạ.")
    assert collected["consciousness_level"] == "alert"


def test_free_text_field_without_allowed_values_is_kept_as_is():
    cluster = CLUSTERS_BY_ID["Q0-01"]  # age_value không có allowed_values
    collected = agent._collect(cluster, {"age_value": "3"}, "Bé 3 tuổi.")
    assert collected["age_value"] == "3"


# --- Guard 3: unknown không xoá được giá trị đã xác định (lỗi M3) --------------------------------


def test_merge_answers_keeps_determined_value_against_unknown():
    merged = _engine._merge_answers({"cyanosis": "false"}, {"cyanosis": "unknown"})
    assert merged["cyanosis"] == "false"


def test_merge_answers_allows_user_to_correct_a_determined_value():
    # CS §3: người dùng có quyền sửa lời khai - giá trị XÁC ĐỊNH mới vẫn thắng giá trị cũ.
    merged = _engine._merge_answers({"cyanosis": "false"}, {"cyanosis": "true"})
    assert merged["cyanosis"] == "true"


def test_merge_answers_still_writes_unknown_for_new_key():
    merged = _engine._merge_answers({}, {"cyanosis": "unknown"})
    assert merged["cyanosis"] == "unknown"


def test_retraction_never_erases_a_confirmed_red_flag_negative():
    """"Không có ban" KHÔNG làm `non_blanching_rash` vô nghĩa - nó làm field đó âm tính, mà âm tính
    là dữ kiện phải giữ. Lỗi thật đo được khi chạy LLM thật: `non_blanching_rash` đã xác nhận "false"
    ở lượt trước bị xoá về "unknown" -> checklist tự chăm sóc không bao giờ đủ, cụm ban bị hỏi lại."""
    before = {"non_blanching_rash": "false", "rash_present": "unknown", "rash_type": "petechial"}
    after = {"non_blanching_rash": "false", "rash_present": "false", "rash_type": "petechial"}

    cleaned, reopened = retraction.apply_retraction(FEVER_PROTOCOL, before, after)

    assert cleaned["non_blanching_rash"] == "false"
    assert cleaned["rash_type"] == "unknown"  # kiểu ban thì đúng là vô nghĩa khi không có ban
    assert "Q3-11" in reopened


def test_non_batch_negation_cluster_ignores_cluster_all_negative_flag():
    cluster = CLUSTERS_BY_ID["Q0-01"]  # batch_negation=False
    collected = agent._collect(cluster, {"cluster_all_negative": True, "age_value": None})
    # age_value không phải tri-state -> field bị bỏ qua khi null, không bị ép "false"
    assert "age_value" not in collected


# --- tri-state: unknown/null KHÔNG bao giờ thành false, im lặng vẫn là unknown -------------------


def test_missing_field_in_llm_response_becomes_unknown_not_false(monkeypatch):
    fake = _fake_complete({})  # LLM không nhắc gì tới field nào
    monkeypatch.setattr(provider_router, "complete", fake)

    cluster = CLUSTERS_BY_ID["Q3-05"]  # focal_neuro_deficit
    result = agent.extract_cluster(cluster, "Bé bị sốt thôi ạ.")

    assert result["focal_neuro_deficit"] == "unknown"


@pytest.mark.parametrize("raw,expected", [(True, "true"), (False, "false"), ("có", "true"), ("không", "false"), (None, "unknown"), ("", "unknown")])
def test_tri_state_normalization_table(raw, expected):
    assert agent._tri_state_value(raw) == expected


# --- JSON hỏng: không ném ra ngoài, trả toàn unknown + ghi parse_error --------------------------


def test_malformed_llm_response_falls_back_to_unknown_without_raising(monkeypatch):
    fake = Mock(return_value=provider_router.CompletionResult(text="không phải JSON đâu nhé", provider="openrouter", model="x"))
    monkeypatch.setattr(provider_router, "complete", fake)

    cluster = CLUSTERS_BY_ID["Q3-07"]  # stridor_or_drooling
    result = agent.extract_cluster(cluster, "bé có vẻ khó thở")

    assert result["stridor_or_drooling"] == "unknown"


def test_provider_exception_falls_back_to_unknown_without_raising(monkeypatch):
    fake = Mock(side_effect=provider_router.NoProviderConfiguredError("no key"))
    monkeypatch.setattr(provider_router, "complete", fake)

    cluster = CLUSTERS_BY_ID["Q3-07"]
    result = agent.extract_cluster(cluster, "bé có vẻ khó thở")

    assert result["stridor_or_drooling"] == "unknown"


# --- không quyết định triage -----------------------------------------------------------------


def test_extraction_output_never_contains_triage_decision_keys(monkeypatch):
    fake = _fake_complete(
        {
            "consciousness_level": "alert",
            "triage_level": "EMERGENCY",  # LLM cố "lỡ" trả field quyết định - phải bị lọc bỏ
            "priority": "high",
            "next_stage": "6",
        }
    )
    monkeypatch.setattr(provider_router, "complete", fake)

    cluster = CLUSTERS_BY_ID["Q3-01"]
    result = agent.extract_cluster(cluster, O1_USER_MESSAGE)

    assert "triage_level" not in result
    assert "priority" not in result
    assert "next_stage" not in result


# --- opportunistic keyword scan ------------------------------------------------------------


def test_scan_opportunistic_fields_detects_seizure_from_free_text():
    found = agent.scan_opportunistic_fields("bé đang co giật ngay bây giờ")
    assert found.get("seizure_active_now") == "true"


def test_scan_opportunistic_fields_never_returns_false_for_silence():
    found = agent.scan_opportunistic_fields("bé sốt 38 độ, ăn uống bình thường")
    assert "false" not in found.values()


# --- log -----------------------------------------------------------------------------------


# --- sửa lỗi JSON bareword unknown (lỗi thật gặp phải với gpt-4o-mini qua OpenRouter, Checkpoint 6b) -


def test_repair_bareword_unknown_fixes_real_gpt4o_mini_output():
    broken = (
        '{\n  "extracted": {\n    "seizure_active_now": true,\n    "seizure_occurred": unknown,\n'
        '    "neck_stiffness": unknown\n  },\n  "next_question": "..."\n}'
    )
    repaired = agent._repair_bareword_unknown(broken)
    import json as _json

    parsed = _json.loads(repaired)
    assert parsed["extracted"]["seizure_active_now"] is True
    assert parsed["extracted"]["seizure_occurred"] == "unknown"
    assert parsed["extracted"]["neck_stiffness"] == "unknown"


def test_repair_bareword_unknown_does_not_touch_already_quoted_unknown():
    text = '{"consciousness_level": "unknown"}'
    assert agent._repair_bareword_unknown(text) == text


def test_extract_cluster_survives_bareword_unknown_from_real_model_output(monkeypatch):
    broken_json_text = '{"seizure_active_now": true, "seizure_occurred": unknown}'
    fake = Mock(return_value=provider_router.CompletionResult(text=broken_json_text, provider="openrouter", model="openai/gpt-4o-mini"))
    monkeypatch.setattr(provider_router, "complete", fake)

    cluster = CLUSTERS_BY_ID["Q3-03"]
    result = agent.extract_cluster(cluster, "tay chân đang giật")

    assert result["seizure_active_now"] == "true"
    assert result["seizure_occurred"] == "unknown"


def test_extract_cluster_logs_retrieve_llm_and_extract_in_order(monkeypatch):
    fake = _fake_complete({"consciousness_level": "alert"})
    monkeypatch.setattr(provider_router, "complete", fake)

    session_id = "extract-log-check"
    fever_stage_log.start(session_id, route=None, budget=0)
    cluster = CLUSTERS_BY_ID["Q3-01"]
    agent.extract_cluster(cluster, O1_USER_MESSAGE, session_id=session_id, turn=1, stage="3A")

    records = fever_stage_log.read_all(session_id)
    events = [r["event"] for r in records]
    assert events == ["retrieve", "llm_request", "llm_response", "extract"]

    io_rows = fever_stage_log.read_llm_io(session_id)
    assert len(io_rows) == 1
    assert io_rows[0]["messages"][1]["content"] == O1_USER_MESSAGE


# --- quét kèm field ngoài cụm (`_safety_extra_keys`) ------------------------------------------


ADULT_DEMOGRAPHICS = {"age_value": "30", "age_unit": "year", "sex": "female", "reporter_type": "self"}


def test_risk_context_is_extractable_from_the_very_first_turn():
    """Bối cảnh nguy cơ nằm ở Stage 4 nhưng người bệnh hay khai ngay câu đầu ("em đang mang thai").
    Không có ô nào trong schema thì lời khai đó rơi mất, và tới Stage 4 hệ thống hỏi lại nguyên văn -
    đúng phàn nàn "có thông tin trong câu trả lời rồi mà vẫn hỏi"."""
    cluster = CLUSTERS_BY_ID["Q1-01"]

    keys = _engine._safety_extra_keys(
        FEVER_PROTOCOL, "1", cluster, dict(ADULT_DEMOGRAPHICS), frozenset(),
    )

    assert {"is_pregnant", "chronic_conditions", "immunocompromised"} <= set(keys)


def test_lookahead_covers_more_than_the_next_handful_of_clusters():
    """Cửa sổ cũ là 5 cụm - quá hẹp so với thứ người bệnh kể vượt trước."""
    cluster = CLUSTERS_BY_ID["Q1-01"]

    keys = _engine._safety_extra_keys(
        FEVER_PROTOCOL, "1", cluster, dict(ADULT_DEMOGRAPHICS), frozenset(),
    )

    assert _engine.SAFETY_LOOKAHEAD_CLUSTERS > 5
    assert len(keys) > 20


def test_extraction_schema_stays_bounded_even_with_the_wider_lookahead():
    """Nới cửa sổ đổi lấy prompt dài hơn, nên phải có trần đo được. Ngưỡng 60 ở đây là mốc chặn hồi
    quy (số đo thật ~33-39 field/lượt), không phải con số thiêng."""
    for cluster_id in ("Q1-01", "Q3-04", "Q4-00"):
        cluster = CLUSTERS_BY_ID[cluster_id]
        keys = _engine._safety_extra_keys(
            FEVER_PROTOCOL, cluster.stage, cluster, dict(ADULT_DEMOGRAPHICS), frozenset(),
        )
        assert len(keys) + len(cluster.fields) < 60, cluster_id


def test_field_whose_parent_was_denied_is_left_out_of_the_schema():
    """Đã trả lời "không suy giảm miễn dịch" thì "nguyên nhân suy giảm miễn dịch" không phải field
    còn thiếu - nó vô nghĩa. Mời model điền nó là mở đường cho một giá trị bịa."""
    answers = dict(ADULT_DEMOGRAPHICS, immunocompromised="false")

    keys = _engine._safety_extra_keys(
        FEVER_PROTOCOL, "1", CLUSTERS_BY_ID["Q1-01"], answers, frozenset(),
    )

    assert "immunocompromise_cause" not in keys
    assert "known_neutropenia" not in keys
