"""Regression transcript của §13 "Definition of Done" (§9 P0.4).

    User: Tôi bị sốt.
    User: Mình là người lớn, nam, 20 tuổi.
    User: Mình quên mất, mình không sốt.
    User: Bây giờ bạn đang hỏi tôi cái gì vậy?

Đây là ví dụ mà cả tài liệu kế hoạch xoay quanh, nên nó phải có một bài test chạy được trong CI với
LLM giả - không phải một lần chạy tay rồi kể lại. Bốn lượt này chạm đủ bốn cơ chế khác nhau:
`retraction` (xoá dây chuyền), `registry.select_protocol` (đổi protocol khi lời khai bị rút),
`DialoguePolicy` (câu hỏi ngược), và ranking (cụm kế tiếp phải là câu MỞ, không presupposition).

Kết quả tương ứng với model thật (`deepseek-chat`) nằm ở `eval/baselines/` - bài này canh CƠ CHẾ,
bài kia canh CHẤT LƯỢNG DIỄN ĐẠT. Hai thứ hỏng theo hai cách khác nhau nên đo tách.
"""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from src import paths
from src.services.engines.fever_protocol import FEVER_PROTOCOL
from src.services.engines.generic_protocol import GENERIC_PROTOCOL
from src.services.infra import provider_router
from src.services.symptom_protocol import batching, dialogue
from src.services.symptom_protocol.session import ProtocolSessionStore

# `(giá trị, bằng chứng)` cho từng lượt. Bằng chứng phải là NGUYÊN VĂN một đoạn trong tin nhắn -
# `_evidence_in_message` loại mọi field không trích được câu người bệnh thật sự nói.
_TURNS: list[tuple[str, dict[str, tuple[object, str]], str]] = [
    (
        "Tôi bị sốt.",
        {"fever_reported": ("true", "Tôi bị sốt"), "chief_complaint": ("sốt", "Tôi bị sốt")},
        "answered",
    ),
    (
        "Mình là người lớn, nam, 20 tuổi.",
        {
            "age_value": ("20", "20 tuổi"),
            "age_unit": ("year", "20 tuổi"),
            "sex": ("male", "nam"),
            "reporter_type": ("self", "Mình là người lớn"),
        },
        "answered",
    ),
    (
        "Mình quên mất, mình không sốt.",
        {"fever_reported": ("false", "mình không sốt")},
        "correction",
    ),
    (
        "Bây giờ bạn đang hỏi tôi cái gì vậy?",
        {},
        "asks_question",
    ),
]

_RENDERED_QUESTION = "Dạ mình muốn biết điều gì đang khiến bạn khó chịu nhất ạ?"


@pytest.fixture(autouse=True)
def _isolated_log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LOGS_DIR", tmp_path)


@pytest.fixture
def transcript(monkeypatch):
    """Chạy trọn 4 lượt, trả `(session, prompts)` - `prompts` để kiểm plan đã tới renderer chưa."""
    prompts: list[str] = []
    state = {"index": 0}

    def complete(messages, *, credential=None, temperature=None, max_attempts=3, role=None):
        system = messages[0]["content"]
        if "Ý CẦN HỎI" in system:
            prompts.append(system)
            return provider_router.CompletionResult(text=_RENDERED_QUESTION, provider="fake", model="fake")
        _message, payload, quality = _TURNS[state["index"]]
        body: dict[str, object] = {
            key: {"value": value, "evidence_span": evidence}
            for key, (value, evidence) in payload.items()
            if key in system
        }
        body["answer_quality"] = quality
        return provider_router.CompletionResult(text=json.dumps(body), provider="fake", model="fake")

    monkeypatch.setattr(provider_router, "complete", Mock(side_effect=complete))

    store = ProtocolSessionStore(default_protocol=None)
    session = store.start_session()
    asked: list[str | None] = []
    for index, (message, _payload, _quality) in enumerate(_TURNS):
        state["index"] = index
        store.submit_message(session.session_id, message)
        asked.append(session.current_cluster.id if session.current_cluster else None)
    return session, prompts, asked


def _cluster_ids(cluster_id: str) -> set[str]:
    """Mã cụm thật bên trong một mã GÓI - câu hỏi gộp mang mã tổng hợp, không phải mã cụm."""
    if cluster_id.startswith(batching.BATCH_ID_PREFIX):
        return set(batching._components_of(cluster_id))
    return {cluster_id}


# --- §13 mục 1-3: hồ sơ cuối và protocol -----------------------------------------------------------


def test_the_final_record_keeps_demographics_and_the_retracted_fever(transcript) -> None:
    """§13 mục 1. Đính chính KHÔNG được cuốn theo những gì người bệnh không hề rút lại."""
    session, _prompts, _asked = transcript
    assert session.answers.get("age_value") == "20"
    assert session.answers.get("sex") == "male"
    assert session.answers.get("fever_reported") == "false"


def test_fever_details_are_cleared_but_the_history_survives(transcript) -> None:
    """§13 mục 2. Giá trị `false` là DỮ KIỆN, không phải xoá field - nó là căn cứ để chọn lại protocol."""
    session, _prompts, _asked = transcript
    for key in FEVER_PROTOCOL.field_dependencies["fever_reported"]:
        assert session.answers.get(key, "unknown") == "unknown", key
    # Lời khai cũ vẫn còn trong hội thoại để điều dưỡng truy được.
    assert any("Tôi bị sốt" in turn["content"] for turn in session.conversation)


def test_the_session_switches_back_to_the_generic_protocol(transcript) -> None:
    """§13 mục 3."""
    session, _prompts, _asked = transcript
    assert session.protocol_name == GENERIC_PROTOCOL.name


def test_the_next_question_is_an_open_chief_complaint_not_a_presupposition(transcript) -> None:
    """§13 mục 4: ngay SAU lượt rút lời khai, câu hỏi phải là câu MỞ về vấn đề chính - không mặc
    định người bệnh đang đau hay khó chịu ở một vùng nào đó."""
    _session, _prompts, asked = transcript
    after_retraction = asked[2]
    assert after_retraction is not None
    assert "G1-01" in _cluster_ids(after_retraction)


# --- §13 mục 5: câu hỏi ngược -----------------------------------------------------------------------


def test_the_meta_question_is_answered_before_asking_again(transcript) -> None:
    """§13 mục 5 - vế mà trước đây KHÔNG chạy được: `answer_quality=asks_question` đã tồn tại nhưng
    không nhánh nào dùng nó để tạo phản hồi phù hợp (§2.3)."""
    _session, prompts, _asked = transcript
    assert prompts, "renderer chua he duoc goi"
    last = prompts[-1]
    policy = dialogue.DIALOGUE_POLICY[dialogue.DialogueAct.ASKS_CLARIFICATION]
    assert policy.answer_user_question in last
    assert "GIẢI THÍCH NGẮN" in last


def test_the_meta_question_turn_collects_nothing_and_keeps_the_cluster_open(transcript) -> None:
    """§6.2: `asks_clarification` KHÔNG được tính là đã trả lời xong cụm.

    Cụm kế tiếp có thể KHÁC cụm vừa hỏi mà vẫn đúng: cụm bị hoãn ở lượt trước được cộng điểm nợ
    (§8.5) nên nó lên trước - đó là ranking làm việc, không phải cụm bị bỏ rơi. Điều phải canh là
    lượt hỏi ngược không moi được dữ kiện lâm sàng nào và phiên vẫn đang thu thập."""
    session, _prompts, asked = transcript
    assert session.current_cluster is not None
    assert "G1" in asked[-1]
    for key in ("complaint_site", "complaint_severity", "complaint_progression"):
        assert session.answers.get(key, "unknown") == "unknown", key


# --- §13 mục 6: không có chẩn đoán, không tự duyệt --------------------------------------------------


def test_no_diagnosis_and_no_auto_approval(transcript) -> None:
    session, _prompts, _asked = transcript
    assert session.triage_level != "EMERGENCY"
    assert session.escalation_lock is False
    assert session.state.value == "collecting"


def test_the_retraction_turn_is_labelled_a_correction(transcript) -> None:
    """Nhãn `correction` phải đi tới `DialoguePolicy` - đó là điều kiện để lượt đính chính được công
    nhận rõ ràng thay vì im lặng đi tiếp."""
    _session, prompts, _asked = transcript
    correction_policy = dialogue.DIALOGUE_POLICY[dialogue.DialogueAct.CORRECTION]
    assert any(correction_policy.acknowledge_instruction in prompt for prompt in prompts)
