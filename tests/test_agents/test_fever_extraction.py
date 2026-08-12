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
from src.services.agents import fever_intake_agent as agent
from src.services.checklists.fever_checklist import CLUSTERS_BY_ID
from src.services.infra import fever_stage_log, provider_router

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
    fake = _fake_complete({"cluster_all_negative": True})
    monkeypatch.setattr(provider_router, "complete", fake)

    cluster = CLUSTERS_BY_ID["Q3-04"]  # batch_negation=True, 4 field tri-state
    assert cluster.batch_negation is True

    result = agent.extract_cluster(cluster, "Dạ không, không có gì trong số đó cả.")

    assert set(result.values()) == {"false"}
    assert "unknown" not in result.values()
    assert len(result) == len(cluster.fields)


def test_batch_negation_partial_positive_keeps_explicit_field_true():
    cluster = CLUSTERS_BY_ID["Q3-06"]  # breathing_difficulty, cyanosis, chest_indrawing, nasal_flaring_grunting
    parsed = {"cluster_all_negative": True, "breathing_difficulty": "mild"}
    collected = agent._collect(cluster, parsed)

    assert collected["breathing_difficulty"] == "mild"
    assert collected["cyanosis"] == "false"
    assert collected["chest_indrawing"] == "false"


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
