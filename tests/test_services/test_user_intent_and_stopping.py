"""Ý định người bệnh, thứ tự dừng, và nhánh bất hợp tác (§7.1 + §7.2 `_guidance/what_to_do_next.md`).

Hai tầng, cố ý không trộn:

- phần đầu THUẦN (`user_intent.classify`, `stage_machine.should_stop`) - đây là nơi ràng buộc an
  toàn thật sự nằm, và nó phải kiểm được không cần model nào;
- phần cuối chạy qua `session.submit_message` với LLM giả, vì bộ đếm bất hợp tác chỉ tồn tại ở tầng
  phiên và mức đơn vị không thấy được nó có đi trọn đường hay không.

Ca chặn của cả file là `test_red_flag_beats_a_stop_request_in_the_same_turn`: nó là lỗi an toàn P0.6
trong code đang chạy, và không ca golden nào chạm tới vì đó là một lượt hiếm.
"""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from src import paths
from src.services.engines.fever_protocol import FEVER_PROTOCOL
from src.services.infra import provider_router
from src.services.symptom_protocol import stage_machine, user_intent
from src.services.symptom_protocol.session import ProtocolSessionStore

_RENDERED_QUESTION = "Dạ cho mình hỏi thêm một ý nữa ạ?"

ADULT: dict[str, object] = {
    "age_value": "30", "age_unit": "year", "sex": "male", "reporter_type": "self",
}


@pytest.fixture(autouse=True)
def _isolated_log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LOGS_DIR", tmp_path)


def _should_stop(answers: dict[str, object], *, asked_count: int = 1, **kwargs):
    return stage_machine.should_stop(FEVER_PROTOCOL, "1", answers, asked_count=asked_count, **kwargs)


# --- §7.1 thứ tự dừng ---------------------------------------------------------------------------


def test_red_flag_beats_a_stop_request_in_the_same_turn():
    """CA CHẶN của P0.6.

    Người bệnh vừa khai một dấu hiệu cấp cứu rồi nói "thôi khỏi" trong CÙNG một lượt. Bản cũ kiểm
    `user_can_continue` trước nên phiên đóng với `USER_CANNOT_CONTINUE` - tức là KHÔNG escalate. Ý
    định dừng của người bệnh không bao giờ được tắt một tín hiệu đỏ."""
    answers = {"seizure_active_now": "true"}

    assert _should_stop(answers, user_can_continue=False) == "RED_FLAG"
    assert _should_stop(answers, uncooperative=True) == "RED_FLAG"
    assert _should_stop(answers, no_more_symptoms=True) == "RED_FLAG"


def test_known_emergency_level_also_beats_a_stop_request():
    """Cùng bất biến, nhưng qua đường thứ hai: mức đỏ do rule engine chốt ở lượt trước, chứ không
    phải một field đỏ trong `answers`."""
    assert _should_stop({}, known_triage_level="EMERGENCY", user_can_continue=False) == "RED_FLAG"


def test_stop_intent_beats_sufficient_evidence_and_budget():
    """Phần còn lại của thứ tự đúng như docstring: chỉ chốt đỏ mới thắng ý định người bệnh."""
    assert _should_stop({}, user_can_continue=False) == "USER_CANNOT_CONTINUE"
    assert _should_stop({}, uncooperative=True) == "USER_UNCOOPERATIVE"
    assert _should_stop({}, asked_count=999, user_can_continue=False) == "USER_CANNOT_CONTINUE"


def test_three_stop_reasons_stay_distinguishable():
    """§7.2 mục 4: ba lý do dừng phải ra ba mã KHÁC NHAU. Điều dưỡng cần biết ca này thiếu thông tin
    vì người bệnh bỏ dở, chứ không phải vì không có triệu chứng."""
    reasons = {
        _should_stop({}, user_can_continue=False),
        _should_stop({}, uncooperative=True),
        _should_stop(_full_benign_record(), no_more_symptoms=True),
    }

    assert reasons == {"USER_CANNOT_CONTINUE", "USER_UNCOOPERATIVE", "NO_MORE_SYMPTOMS"}


# --- §7.1 mục 4: "không còn triệu chứng nào khác" KHÔNG phải lệnh dừng tuyệt đối -----------------


def test_no_more_symptoms_does_not_stop_while_mandatory_clusters_are_unasked():
    """Người bệnh nói "hết rồi" khi chưa ai hỏi họ về ngất hay co giật - họ không biết những thứ đó
    là triệu chứng cần khai (§1 bất biến 8)."""
    assert _should_stop(dict(ADULT), no_more_symptoms=True) is None


def test_no_more_symptoms_stops_once_nothing_mandatory_is_left_to_ask():
    record = _full_benign_record()

    assert _should_stop(record, no_more_symptoms=True) == "NO_MORE_SYMPTOMS"


def _full_benign_record() -> dict[str, object]:
    """Hồ sơ mà không cụm nào còn field chưa có căn cứ - dựng từ chính protocol thay vì chép tay một
    danh sách field, để nó không mục đi khi checklist đổi.

    Field enum lấy giá trị hợp lệ ĐẦU TIÊN khác `"unknown"`: `allowed_values[-1]` của fever thường
    chính là `"unknown"`, và một hồ sơ toàn `unknown` thì mọi cụm vẫn còn phải hỏi - test sẽ xanh vì
    lý do sai. `test_no_more_symptoms_stops_once_nothing_mandatory_is_left_to_ask` chỉ có nghĩa khi
    hồ sơ này thật sự đầy."""
    record = dict(ADULT)
    for key, spec in FEVER_PROTOCOL.fields_by_key.items():
        if key in record:
            continue
        allowed = [value for value in spec.allowed_values if value not in ("", "unknown")]
        record[key] = allowed[0] if allowed else "false"
    assert not FEVER_PROTOCOL.provisional_emergency_signal(record), "hồ sơ đối chứng phải LÀNH TÍNH"
    return record


# --- §7.1 mục 5 + §4.7: phân loại ý định ---------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "thôi tôi không trả lời nữa",
        "toi khong muon tra loi nua",
        "tóm tắt cho tôi đi",
        "dừng ở đây nhé",
    ],
)
def test_explicit_stop_requests_are_detected(message: str):
    assert user_intent.classify(message).wants_to_stop is True


@pytest.mark.parametrize(
    "message",
    [
        "không còn gì nữa đâu",
        "khong con trieu chung nao khac",
        "chỉ có thế thôi",
    ],
)
def test_no_more_symptoms_is_detected_separately_from_a_stop_request(message: str):
    intent = user_intent.classify(message)

    assert intent.no_more_symptoms is True
    # Hai tín hiệu KHÁC nhau: một cái là lệnh dừng, một cái là tín hiệu mềm. Trộn chúng lại là mở
    # đúng cái lỗ §4.7a nói tới.
    assert intent.wants_to_stop is False


@pytest.mark.parametrize(
    "message",
    [
        "dm đau quá đi mất",
        "vcl sốt cao lắm",
        "hôm nay trời mưa to",
        "bác sĩ ơi cái này có sao không",
    ],
)
def test_profanity_or_a_single_off_topic_line_is_never_a_stop_signal(message: str):
    """§4.7: người đang đau và sợ thì nói năng không dễ chịu - đó là bối cảnh y tế bình thường."""
    intent = user_intent.classify(message)

    assert intent.wants_to_stop is False
    assert intent.no_more_symptoms is False


def test_a_normal_symptom_report_is_not_read_as_an_intent():
    """Chống bắt nhầm: cụm từ phải đủ dài để không đụng câu kể bình thường."""
    intent = user_intent.classify("tôi bị đau khi dừng lại, đi bộ thì hết đau")

    assert intent.wants_to_stop is False


# --- §7.2 bộ đếm bất hợp tác ---------------------------------------------------------------------


def test_one_off_topic_turn_never_stops_the_session():
    tracker = user_intent.UncooperativeTracker()

    tracker.record_turn(off_topic=True, information_gain=False)

    assert tracker.should_prompt is False
    assert tracker.should_stop is False


def test_two_off_topic_turns_ask_once_before_giving_up():
    tracker = user_intent.UncooperativeTracker()

    for _ in range(user_intent.UNCOOPERATIVE_STREAK_LIMIT):
        tracker.record_turn(off_topic=True, information_gain=False)

    assert tracker.should_prompt is True
    assert tracker.should_stop is False


def test_still_uncooperative_after_the_prompt_stops_the_session():
    tracker = user_intent.UncooperativeTracker()
    for _ in range(user_intent.UNCOOPERATIVE_STREAK_LIMIT):
        tracker.record_turn(off_topic=True, information_gain=False)
    tracker.prompted = True

    tracker.record_turn(off_topic=True, information_gain=False)

    assert tracker.should_stop is True


def test_any_clinical_information_clears_the_streak():
    """Người bệnh quay lại hợp tác thì phiên tiếp tục bình thường, không mang theo "án tích"."""
    tracker = user_intent.UncooperativeTracker()
    for _ in range(user_intent.UNCOOPERATIVE_STREAK_LIMIT):
        tracker.record_turn(off_topic=True, information_gain=False)
    tracker.prompted = True

    tracker.record_turn(off_topic=True, information_gain=True)

    assert tracker.streak == 0
    assert tracker.prompted is False
    assert tracker.should_stop is False


# --- qua `session.submit_message` (LLM giả) -------------------------------------------------------


@pytest.fixture
def fake_llm(monkeypatch):
    """Model trả JSON RỖNG - đúng hành vi khi người bệnh nói những câu không chứa dữ kiện lâm sàng."""
    quality = {"value": "non_answer"}

    def complete(messages, *, credential=None, temperature=None, max_attempts=3, role=None):
        system = messages[0]["content"]
        if "Ý CẦN HỎI" in system:
            return provider_router.CompletionResult(text=_RENDERED_QUESTION, provider="fake", model="fake")
        return provider_router.CompletionResult(
            text=json.dumps({"answer_quality": quality["value"]}), provider="fake", model="fake",
        )

    monkeypatch.setattr(provider_router, "complete", Mock(side_effect=complete))
    return quality


def _fever_session(store: ProtocolSessionStore):
    session = store.start_session(protocol_name=FEVER_PROTOCOL.name)
    session.answers.update(ADULT)
    return session


def test_asking_for_a_summary_closes_the_session_with_missing_information(fake_llm):
    """§7.1 mục 3. Phiếu phải nói rõ đây là ca CHƯA đầy đủ - `missing_information` liệt kê field
    M0/M1 còn `unset`."""
    from src.services.sessions.symptom_case_bridge import to_triage_case

    store = ProtocolSessionStore(FEVER_PROTOCOL)
    session = _fever_session(store)

    store.submit_message(session.session_id, "tóm tắt cho tôi đi")

    assert session.stop_reason == "USER_CANNOT_CONTINUE"
    case = to_triage_case(session, patient_id=None)
    assert case.summary is not None
    assert case.summary.missing_information, "phiếu bỏ dở phải liệt kê field M0/M1 còn thiếu"


def test_a_stop_request_does_not_lower_an_escalation(fake_llm):
    """§7.1 mục 6. Ý định người bệnh chỉ được DỪNG, không được hạ mức - phiên có dấu hiệu đỏ thật
    trong hồ sơ vẫn phải đóng bằng `RED_FLAG`, không phải bằng ý định."""
    store = ProtocolSessionStore(FEVER_PROTOCOL)
    session = _fever_session(store)
    session.answers["seizure_active_now"] = "true"

    store.submit_message(session.session_id, "thôi tôi không trả lời nữa")

    assert session.stop_reason == "RED_FLAG"
    assert session.triage_level == "EMERGENCY"
    assert session.escalation_lock is True


def test_session_asks_once_then_stops_as_uncooperative(fake_llm):
    """§7.2 mục 2-3, chạy trọn đường: hai lượt lạc đề -> hỏi một lần -> vẫn vậy -> dừng."""
    store = ProtocolSessionStore(FEVER_PROTOCOL)
    session = _fever_session(store)

    store.submit_message(session.session_id, "hôm nay trời mưa to quá")
    assert session.stop_reason is None

    store.submit_message(session.session_id, "kệ đi ông ơi")
    assert session.last_question == user_intent.UNCOOPERATIVE_PROMPT
    assert session.stop_reason is None, "mới hỏi lại, chưa được dừng"

    store.submit_message(session.session_id, "chán chả buồn nói")
    assert session.stop_reason == "USER_UNCOOPERATIVE"


def test_uncooperative_session_is_not_asked_the_catch_all_question(fake_llm):
    """Hỏi thêm một câu mở với người vừa từ chối trả lời là làm đúng cái họ vừa từ chối."""
    store = ProtocolSessionStore(FEVER_PROTOCOL)
    session = _fever_session(store)

    for message in ("hôm nay trời mưa to quá", "kệ đi ông ơi", "chán chả buồn nói"):
        store.submit_message(session.session_id, message)

    assert session.stop_reason == "USER_UNCOOPERATIVE"
    assert session.catch_all_asked is False
    assert session.awaiting_catch_all is False
