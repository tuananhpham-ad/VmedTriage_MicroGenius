"""Tầng Weaviate (`src/pipeline/weaviate_cloud.py`) — trước đây KHÔNG có test nào.

Không test nào ở đây chạm mạng. Hai thứ được canh, và cả hai đều là thứ hỏng âm thầm:

1. **Degrade êm khi chưa cấu hình.** Weaviate là tuỳ chọn, `TriagePipeline._persist_to_weaviate()`
   bọc `try/except Exception` và chỉ log `status=skipped`. Nghĩa là một lỗi cấu hình ở đây KHÔNG làm
   request đỏ - nó im lặng, và triệu chứng duy nhất là dữ liệu không bao giờ tới nơi. Test là cách
   duy nhất thấy được.
2. **Payload gửi đi.** `_case_payload` là chỗ dịch `TriageCase` sang bản ghi Weaviate. Sai ở đây
   không làm gì đỏ cả, chỉ làm dữ liệu downstream sai - đúng lớp lỗi mà bridge `symptom_case_bridge`
   từng mắc khi ghi cứng `symptom_group="fever"` cho mọi ca.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from src.models.schemas import (
    ActorRole,
    CaseStatus,
    ConversationMessage,
    RedFlagFinding,
    TriageCase,
    TriagePriority,
    TriageProposal,
)
from src.pipeline.weaviate_cloud import WeaviateCloudRepository, _enum_value, _json_dumps


def _repo(**kwargs) -> WeaviateCloudRepository:
    """Constructor rơi về `Settings` khi tham số rỗng, nên phải GÁN ĐÈ sau khi dựng.

    Không làm vậy thì test đọc `.env` của máy đang chạy: máy có `WEAVIATE_URL` thật sẽ báo
    `configured is True` và test "chưa cấu hình thì degrade êm" trở thành vô nghĩa mà vẫn xanh."""
    repo = WeaviateCloudRepository(case_collection="TestCases", knowledge_collection="TestKnowledge")
    repo.cluster_url = kwargs.get("cluster_url", "")
    repo.api_key = kwargs.get("api_key", "")
    return repo


def _case() -> TriageCase:
    return TriageCase(
        case_id="case-w1",
        patient_id=3,
        status=CaseStatus.NEEDS_NURSE_REVIEW,
        created_at=datetime.now(timezone.utc),
        conversation=[
            ConversationMessage(role=ActorRole.PATIENT, content="Tôi sốt 39 độ"),
            ConversationMessage(role=ActorRole.SYSTEM, content="Bạn sốt mấy ngày rồi?"),
        ],
        triage_proposal=TriageProposal(priority=TriagePriority.EMERGENCY, reason="test"),
        red_flags=[RedFlagFinding(code="RF-01", label="Giảm ý thức")],
    )


# --- degrade êm khi chưa cấu hình ---------------------------------------------------------------


def test_repository_reports_itself_unconfigured_without_url_or_key():
    assert _repo().configured is False
    assert _repo(cluster_url="https://x.weaviate.cloud").configured is False
    assert _repo(api_key="k").configured is False


def test_repository_is_configured_only_when_both_url_and_key_are_present():
    assert _repo(cluster_url="https://x.weaviate.cloud", api_key="k").configured is True


def test_connect_raises_instead_of_silently_doing_nothing():
    """`connect()` PHẢI raise khi thiếu cấu hình. Caller (`_persist_to_weaviate`) bắt exception và
    log `skipped`; nếu hàm này trả `None` thay vì raise thì lỗi sẽ đi tiếp và nổ ở chỗ khác, xa
    nguyên nhân."""
    with pytest.raises(RuntimeError) as excinfo:
        _repo().connect()

    assert "WEAVIATE_URL" in str(excinfo.value) or "weaviate-client" in str(excinfo.value)


# --- payload gửi đi ------------------------------------------------------------------------------


def test_case_payload_carries_the_latest_patient_message():
    payload = _repo()._case_payload(_case())

    assert payload["case_id"] == "case-w1"
    assert payload["patient_message"] == "Bạn sốt mấy ngày rồi?"


def test_case_payload_flattens_enums_to_their_value_not_their_repr():
    """`str(CaseStatus.X)` cho ra `"CaseStatus.X"` - ghi chuỗi đó vào kho dữ liệu nghĩa là mọi truy
    vấn downstream theo trạng thái đều trượt."""
    payload = _repo()._case_payload(_case())

    assert payload["status"] == CaseStatus.NEEDS_NURSE_REVIEW.value
    assert payload["priority"] == TriagePriority.EMERGENCY.value


def test_case_payload_serialises_nested_parts_as_valid_json():
    payload = _repo()._case_payload(_case())

    assert json.loads(payload["red_flags"])[0]["code"] == "RF-01"
    assert json.loads(payload["triage_proposal"])["reason"] == "test"
    assert len(json.loads(payload["conversation"])) == 2


def test_case_payload_uses_empty_string_not_null_for_missing_parts():
    """Weaviate schema khai các trường này là text. `None` lọt qua sẽ thành lỗi lúc insert - tức là
    lỗi ở tầng mạng, nơi `try/except` nuốt mất."""
    bare = TriageCase(
        case_id="case-bare",
        status=CaseStatus.COLLECTING_INFORMATION,
        created_at=datetime.now(timezone.utc),
    )

    payload = _repo()._case_payload(bare)

    assert payload["priority"] == ""
    assert payload["response"] == ""
    assert all(value is not None for value in payload.values())


# --- helper thuần --------------------------------------------------------------------------------


def test_enum_value_passes_plain_strings_through():
    assert _enum_value(TriagePriority.URGENT) == TriagePriority.URGENT.value
    assert _enum_value("đã là chuỗi") == "đã là chuỗi"


def test_json_dumps_keeps_vietnamese_readable():
    """`ensure_ascii=False` không phải chi tiết thẩm mỹ: bản ghi được người đọc trực tiếp trên
    Weaviate console khi lần lại một ca."""
    assert _json_dumps({"note": "sốt cao"}) == '{"note": "sốt cao"}'


def test_json_dumps_maps_none_to_empty_string():
    assert _json_dumps(None) == ""


def test_json_dumps_does_not_double_encode_a_string():
    assert _json_dumps("đã là chuỗi") == "đã là chuỗi"
