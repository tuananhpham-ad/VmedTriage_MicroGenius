"""F10 Fix F: "bạn tôi bị đau ngực" phải ghi đúng AI là bệnh nhân.

Khung lại cho đúng trước khi đọc test: bạn của người dùng CHÍNH LÀ bệnh nhân, nên `chest_pain="true"`
là dữ liệu ĐÚNG. Lỗi không phải "ghi thừa triệu chứng" mà là ghi sai ai đang có triệu chứng, rồi xưng
hô sai theo suốt cả phiên, rồi bảo sửa cũng không sửa được.

Bốn lớp cùng thủng, mỗi lớp một test:
1. `_OTHER_SUBJECT_CUES` đã có sẵn "bạn tôi" nhưng chỉ dùng để hạ một tín hiệu đỏ - không nối vào
   `reporter_type`.
2. `reporter_type` điền rồi thì `_safety_extra_keys` loại nó khỏi schema mọi lượt sau, vì nó không
   thuộc `confirm_before_retract` - mà tập đó chỉ `fever` khai, 5 protocol còn lại rỗng.
3. `hint` của field đóng khung nó là "độ tin cậy thông tin", và `script_hint` của `Q0-01` - cụm CHỨA
   nó - chỉ hỏi tuổi/giới.
4. Tier H nên nó không lên phiếu: điều dưỡng cũng không thấy hệ thống đang nói về nhầm người.
"""

from __future__ import annotations

import pytest

from src.services.engines.abdominal_protocol import ABDOMINAL_PROTOCOL
from src.services.engines.breathing_protocol import BREATHING_PROTOCOL
from src.services.engines.chest_pain_protocol import CHEST_PAIN_PROTOCOL
from src.services.engines.fever_protocol import FEVER_PROTOCOL
from src.services.engines.generic_protocol import GENERIC_PROTOCOL
from src.services.engines.headache_protocol import HEADACHE_PROTOCOL
from src.services.sessions import summary_render
from src.services.symptom_protocol import intake_agent, stage_machine
from src.services.symptom_protocol.common_safety import text_safety_signals

_ALL_PROTOCOLS = (
    CHEST_PAIN_PROTOCOL, BREATHING_PROTOCOL, HEADACHE_PROTOCOL,
    ABDOMINAL_PROTOCOL, FEVER_PROTOCOL, GENERIC_PROTOCOL,
)


# --- lớp 1: cue có sẵn được nối vào `reporter_type` -------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "bạn tôi bị đau ngực",
        "Bạn mình khó thở từ sáng",
        "đồng nghiệp mình sốt cao",
        "hàng xóm tôi đau bụng dữ dội",
        "người quen tôi bị đau đầu",
    ],
)
def test_a_third_person_complaint_is_recorded_as_reported_by_someone_else(message):
    assert text_safety_signals.reporter_type_from_text(message) == "other"


@pytest.mark.parametrize(
    "message",
    [
        "tôi bị đau ngực",
        "con tôi sốt 39 độ",  # người nhà kể hộ VẪN là bệnh nhân - không phải "other"
        "bé nhà mình khó thở",
        "nghe nói sốt cao là nguy hiểm lắm",  # hỏi vu vơ, không có bệnh nhân nào
        "đọc báo thấy đau ngực có thể là bệnh tim",
    ],
)
def test_silence_and_hearsay_never_become_evidence_about_who_the_patient_is(message):
    """KHÔNG bao giờ trả `"self"`: im lặng không phải bằng chứng người nhắn là bệnh nhân (P0-4).

    Nguồn NGHE KỂ cũng không: "nghe nói sốt cao nguy hiểm" không có bệnh nhân nào ở đầu bên kia, nên
    nó vẫn hạ một tín hiệu đỏ xuống mức cần xác nhận, nhưng không trả lời được "ai là bệnh nhân"."""
    assert text_safety_signals.reporter_type_from_text(message) == ""


def test_the_hearsay_split_did_not_shrink_the_red_flag_guard():
    """Tách `_OTHER_PERSON_CUES` khỏi `_HEARSAY_CUES` KHÔNG được làm hẹp guard đang chạy.

    Guard `GUARD_OTHER_SUBJECT` vẫn phải bắt cả hai nhóm - nó trả lời một câu khác ("câu này có phải
    chuyện của người nhắn không"), và câu trả lời cho cả hai nhóm đều là không."""
    for cue in text_safety_signals._OTHER_PERSON_CUES + text_safety_signals._HEARSAY_CUES:
        assert text_safety_signals._OTHER_SUBJECT_CUES.search(
            text_safety_signals.normalize_red_flag_text(cue)
        ), cue


# --- lớp 2: còn ô để ghi khi người dùng đính chính --------------------------------------------------


@pytest.mark.parametrize("protocol", _ALL_PROTOCOLS, ids=lambda p: p.name)
def test_reporter_type_stays_correctable_in_every_protocol(protocol):
    """`_safety_extra_keys` loại khỏi schema mọi field ĐÃ điền trừ `confirm_before_retract`.

    Không có nó thì lượt sau người dùng nói "không, là bạn tôi chứ không phải tôi" mà extractor không
    có ô nào để ghi - đúng triệu chứng "bảo sửa vẫn không nhận"."""
    assert "reporter_type" in protocol.confirm_before_retract


@pytest.mark.parametrize("protocol", _ALL_PROTOCOLS, ids=lambda p: p.name)
def test_the_extraction_schema_keeps_reporter_type_after_it_is_already_filled(protocol):
    """Kiểm chính cái cơ chế, không chỉ kiểm khai báo: field đã điền vẫn phải nằm trong schema."""
    cluster = next(c for c in protocol.clusters if "reporter_type" not in c.fields)
    keys = intake_agent._safety_extra_keys(
        protocol, cluster.stage, cluster, {"reporter_type": "self"}, frozenset(),
    )

    assert "reporter_type" in keys


def test_fever_did_not_lose_its_own_two_guarded_fields():
    """`fever` là protocol DUY NHẤT từng khai tập này. Gộp tập nền vào không được đá mất phần của nó."""
    assert {"fever_reported", "fever_status"} <= FEVER_PROTOCOL.confirm_before_retract


# --- lớp 3: hỏi tường minh, và hỏi đúng thứ ---------------------------------------------------------


def test_the_field_hint_says_who_has_the_symptom_not_how_reliable_the_report_is():
    spec = CHEST_PAIN_PROTOCOL.fields_by_key["reporter_type"]
    assert "TRIỆU CHỨNG" in spec.hint
    assert "độ tin cậy thông tin" not in spec.hint


def test_the_cluster_that_holds_reporter_type_actually_asks_about_it():
    """`Q0-01` chứa `reporter_type` nhưng `script_hint` chỉ hỏi tuổi/giới - cụm không bao giờ hỏi
    tường minh ai đang khai, nên cả phiên trôi theo giả định ngầm."""
    cluster = next(c for c in CHEST_PAIN_PROTOCOL.clusters if c.id == "Q0-01")

    assert "reporter_type" in cluster.fields
    assert "chính bạn" in cluster.script_hint


@pytest.mark.parametrize(
    ("reporter", "expected"),
    [("other", "NGƯỜI KHÁC"), ("parent_caregiver", "NGƯỜI NHÀ"), ("self", "CHÍNH LÀ")],
)
def test_the_question_prompt_switches_subject_by_reporter_type(reporter, expected):
    """Đây là chỗ Fix E và Fix F gặp nhau: persona nhất quán mà chủ ngữ sai thì agent hỏi "bạn có đau
    ngực không" một cách rất kiên định với người vừa nói rõ là đang hỏi hộ bạn mình."""
    note = intake_agent._subject_note({"reporter_type": reporter})

    assert expected in note


def test_an_unknown_reporter_does_not_get_a_default_subject():
    """Rỗng chứ không mặc định `"self"` - đoán "người nhắn là bệnh nhân" chính là lỗi gốc."""
    assert intake_agent._subject_note({}) == ""
    assert intake_agent._subject_note({"reporter_type": "unknown"}) == ""


# --- lớp 4: điều dưỡng đọc được ----------------------------------------------------------------------


def test_reporter_type_reaches_the_nurse_ticket_without_changing_its_tier():
    """Tier H nên nó không lên phiếu theo đường tier. Nâng tier để lên phiếu là đổi luôn điều kiện
    dừng của phiên (`mandatory_fields_covered`) - `_ALWAYS_DETAIL_KEYS` là cửa đúng."""
    assert CHEST_PAIN_PROTOCOL.fields_by_key["reporter_type"].tier == "H"
    assert "reporter_type" not in stage_machine.MANDATORY_TIERS

    summary = summary_render.field_summary(
        CHEST_PAIN_PROTOCOL, {"reporter_type": "other", "chest_pain": "true"},
    )

    assert any("người khác khai" in detail.casefold() for detail in summary.details)


# --- cả bốn lớp trên cùng một phiên -----------------------------------------------------------------


def test_a_session_that_opens_with_a_third_person_complaint_records_the_right_patient(
    monkeypatch, tmp_path,
):
    """Đường tất định phải chạy được KHI MODEL KHÔNG ĐIỀN GÌ cho `reporter_type`.

    Đó là điều kiện thật: `_EXTRACTION_SYSTEM` không có luật nào về chủ ngữ, nên model trả `unknown`
    là trường hợp bình thường, không phải sự cố."""
    import json
    from unittest.mock import Mock

    from src import paths
    from src.services.infra import provider_router
    from src.services.symptom_protocol.session import ProtocolSessionStore

    monkeypatch.setattr(paths, "LOGS_DIR", tmp_path)

    def complete(messages, *, credential=None, temperature=None, max_attempts=3, role=None):
        system = messages[0]["content"]
        if "Hãy diễn đạt lại Ý CẦN HỎI" in system:
            return provider_router.CompletionResult(
                text="Cơn khó chịu bắt đầu khi nào?", provider="fake", model="fake",
            )
        body = {"chest_pain": {"value": "true", "evidence_span": "đau ngực"}}
        return provider_router.CompletionResult(
            text=json.dumps({k: v for k, v in body.items() if k in system}),
            provider="fake", model="fake",
        )

    monkeypatch.setattr(provider_router, "complete", Mock(side_effect=complete))
    store = ProtocolSessionStore()
    session = store.start_session()
    session = store.submit_message(session.session_id, "Bạn tôi bị đau ngực từ sáng nay")

    # Triệu chứng của bạn người dùng là dữ liệu ĐÚNG - bạn họ chính là bệnh nhân của phiên.
    assert session.answers.get("chest_pain") == "true"
    assert session.answers.get("reporter_type") == "other"
