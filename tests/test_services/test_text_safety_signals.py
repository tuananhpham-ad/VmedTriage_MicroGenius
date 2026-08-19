"""Tầng L0 `text_safety_signals` - guard phủ định/thời gian/chủ thể và việc nối vào luồng chuẩn.

Bộ test hiện có (`test_red_flag_text_rules.py`) chỉ kiểm ca dương tính và ca trung tính, nên ba câu
PHỦ ĐỊNH dưới đây từng khớp red flag mà không ai thấy:

    "Toi khong co giat"              -> seizure
    "Be khong kho tho nang"          -> severe_breathing
    "Khong co moi tim hay co giat"   -> cyanosis + seizure

Đó là lý do tầng này tồn tại: một match trần KHÔNG được thành `EMERGENCY`. Vì vậy file này kiểm hai
thứ tách bạch:

- guard có loại đúng những gì phải loại, và KHÔNG loại nhầm ca dương tính thật (nửa sau nguy hiểm
  hơn - guard quá tay là bỏ sót dấu hiệu đỏ);
- luồng phiên thật sự dừng ngay ở tín hiệu dương tính rõ, TRƯỚC khi gọi model, và không im lặng bỏ
  qua tín hiệu mơ hồ khi model hỏng.
"""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from src import paths
from src.services.engines.fever_protocol import FEVER_PROTOCOL
from src.services.engines.red_flag_text_rules import TEXT_RED_FLAG_RULES
from src.services.infra import provider_router
from src.services.symptom_protocol.common_safety import text_safety_signals as tss
from src.services.symptom_protocol.common_safety.text_safety_signals import (
    SHORT_CIRCUIT_CODES,
    SignalStatus,
    scan_text_safety_signals,
)
from src.services.symptom_protocol.intake_agent import scan_opportunistic_fields
from src.services.symptom_protocol.session import ProtocolSessionStore, SessionState


@pytest.fixture(autouse=True)
def _isolated_log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LOGS_DIR", tmp_path)


def _status_of(message: str, code: str) -> tuple[SignalStatus, str]:
    signal = next(s for s in scan_text_safety_signals(message).signals if s.code == code)
    return signal.status, signal.guard


# --- guard phủ định ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ("Toi khong co giat", "seizure"),
        ("Be khong kho tho nang", "severe_breathing"),
        ("Khong co moi tim hay co giat", "cyanosis"),
        ("Khong co moi tim hay co giat", "seizure"),
        ("Cháu chưa bao giờ co giật", "seizure"),
        ("Bé ko bị co giật", "seizure"),
    ],
)
def test_negated_mentions_are_suppressed(message: str, code: str) -> None:
    """Ba câu đầu là ca hồi quy chép nguyên từ tài liệu - chúng KHÔNG được escalate."""
    status, guard = _status_of(message, code)
    assert status is SignalStatus.SUPPRESSED
    assert guard == tss.GUARD_NEGATED
    assert scan_text_safety_signals(message).short_circuit == ()


def test_negation_spans_a_coordinated_list_but_stops_at_a_contrast_conjunction() -> None:
    """"không A hay B" phủ định cả hai; "không A mà B" thì B là một khẳng định MỚI."""
    assert _status_of("Không có môi tím hay co giật", "seizure")[0] is SignalStatus.SUPPRESSED
    assert _status_of("Tôi không sốt gì cả mà tự nhiên chiều nay co giật", "seizure")[0] is (
        SignalStatus.CONFIRMED_POSITIVE
    )


def test_focus_negation_does_not_suppress_the_predicate_after_it() -> None:
    """"không phải X mà Y" phủ định TRỌNG TÂM, không phủ định dấu hiệu đứng sau."""
    assert _status_of("Không phải tôi mà con tôi bị co giật", "seizure")[0] is SignalStatus.CONFIRMED_POSITIVE


def test_uncertainty_is_not_negation() -> None:
    """"không biết" là bất định - phải đi đường xác nhận, không được loại."""
    status, guard = _status_of("Tôi không biết có phải co giật không", "seizure")
    assert status is SignalStatus.NEEDS_CONFIRMATION
    assert guard in {tss.GUARD_UNCERTAIN, tss.GUARD_INTERROGATIVE}


def test_a_negation_far_away_in_the_same_clause_does_not_reach_the_mention() -> None:
    """Cửa sổ phủ định có trần: một câu dài mở đầu bằng "không" không được nuốt dấu hiệu ở cuối."""
    message = (
        "Không sốt, không ho, không đau họng, không mệt mỏi gì suốt mấy ngày nay thế rồi tự nhiên co giật"
    )
    assert _status_of(message, "seizure")[0] is not SignalStatus.SUPPRESSED


# --- guard thời gian và chủ thể ------------------------------------------------------------------


def test_history_downgrades_instead_of_suppressing() -> None:
    status, guard = _status_of("Hồi nhỏ bé từng bị co giật", "seizure")
    assert status is SignalStatus.NEEDS_CONFIRMATION
    assert guard == tss.GUARD_HISTORICAL


def test_a_present_tense_cue_overrides_the_history_cue() -> None:
    """"Hôm qua sốt, giờ đang co giật" là cấp cứu - mốc quá khứ ở mệnh đề trước không hạ nó xuống."""
    assert _status_of("Hôm qua bé sốt, giờ đang co giật", "seizure")[0] is SignalStatus.CONFIRMED_POSITIVE


def test_another_person_downgrades_but_a_family_member_does_not() -> None:
    assert _status_of("Bạn tôi bị co giật", "seizure")[1] == tss.GUARD_OTHER_SUBJECT
    # Người nhà được tư vấn hộ CHÍNH LÀ bệnh nhân - phần lớn ca nhi đi đường này.
    assert _status_of("Con tôi đang co giật", "seizure")[0] is SignalStatus.CONFIRMED_POSITIVE


def test_hypothetical_and_interrogative_questions_do_not_escalate() -> None:
    assert _status_of("Nếu bé co giật thì phải làm sao", "seizure")[1] == tss.GUARD_HYPOTHETICAL
    assert _status_of("Có bị co giật không", "seizure")[1] == tss.GUARD_INTERROGATIVE
    # Nhưng một ca thật kèm câu hỏi vẫn là ca thật: dấu "?" đơn thuần không hạ cấp.
    assert _status_of("Bé đang co giật, phải làm sao?", "seizure")[0] is SignalStatus.CONFIRMED_POSITIVE


# --- phân loại và danh sách được duyệt -----------------------------------------------------------


def test_a_clear_ongoing_positive_short_circuits() -> None:
    scan = scan_text_safety_signals("Bé đang co giật ngay lúc này")
    assert [signal.code for signal in scan.short_circuit] == ["seizure"]
    assert scan.reason_codes == ("TEXT_SIGNAL_SEIZURE",)


def test_a_positive_outside_the_reviewed_list_asks_instead_of_escalating() -> None:
    """"sưng họng" khớp một luật thật nhưng gặp ở mọi ca viêm họng thường - không được gọi 115."""
    status, guard = _status_of("Em bé bị sưng họng", "throat_swelling")
    assert status is SignalStatus.NEEDS_CONFIRMATION
    assert guard == tss.GUARD_NOT_REVIEWED
    assert scan_text_safety_signals("Em bé bị sưng họng").short_circuit == ()


def test_every_reviewed_code_exists_in_the_rule_catalogue() -> None:
    assert SHORT_CIRCUIT_CODES <= {text_rule.code for text_rule in TEXT_RED_FLAG_RULES}


def test_the_strongest_status_wins_when_one_code_matches_twice() -> None:
    """Nhắc hai lần, một lần mơ hồ một lần rõ ⇒ lấy lần rõ. Thiên về độ nhạy là có chủ đích."""
    scan = scan_text_safety_signals("Hôm qua bé co giật. Bây giờ bé lại đang co giật.")
    assert any(signal.code == "seizure" and signal.status is SignalStatus.CONFIRMED_POSITIVE for signal in scan.signals)


def test_a_benign_message_produces_no_signal() -> None:
    assert scan_text_safety_signals("Tôi cảm nhẹ, vẫn ăn uống và sinh hoạt bình thường.").signals == ()


def test_signals_are_found_without_diacritics() -> None:
    scan = scan_text_safety_signals("be dang co giat")
    assert [signal.code for signal in scan.short_circuit] == ["seizure"]


# --- cùng guard cho tầng quét từ khoá cơ hội -----------------------------------------------------


def test_opportunistic_keyword_scan_no_longer_records_a_denied_symptom() -> None:
    """`scan_opportunistic_fields` cũng khớp substring trên text thô, và cũng từng ghi
    `seizure_occurred=true` cho câu "tôi không co giật"."""
    assert scan_opportunistic_fields(FEVER_PROTOCOL, "Tôi không co giật") == {}
    assert scan_opportunistic_fields(FEVER_PROTOCOL, "Bé đang co giật")["seizure_occurred"] == "true"


# --- nối vào luồng phiên thật --------------------------------------------------------------------


def _store() -> ProtocolSessionStore:
    return ProtocolSessionStore(default_protocol=FEVER_PROTOCOL)


def _llm_that_must_not_be_called(monkeypatch) -> Mock:
    mock = Mock(side_effect=AssertionError("L0 phải chạy TRƯỚC mọi lời gọi model"))
    monkeypatch.setattr(provider_router, "complete", mock)
    monkeypatch.setattr(provider_router, "complete_stream", mock)
    return mock


def _broken_llm(monkeypatch) -> None:
    """Model trả JSON rỗng - mô phỏng parse hỏng/timeout: không field nào được trích."""

    def complete(messages, *, credential=None, temperature=None, max_attempts=3, role=None):
        if "Hãy diễn đạt lại Ý CẦN HỎI" in messages[0]["content"]:
            return provider_router.CompletionResult(text="Bạn bị sốt bao lâu rồi?", provider="fake", model="fake")
        return provider_router.CompletionResult(text=json.dumps({}), provider="fake", model="fake")

    monkeypatch.setattr(provider_router, "complete", Mock(side_effect=complete))


def test_a_clear_text_signal_escalates_before_any_model_call(monkeypatch) -> None:
    mock = _llm_that_must_not_be_called(monkeypatch)
    store = _store()
    session = store.start_session()

    store.submit_message(session.session_id, "Bé đang co giật ngay lúc này")

    assert session.state is SessionState.EMERGENCY
    assert session.triage_level == "EMERGENCY"
    assert session.escalation_lock is True
    assert session.stop_reason == "RED_FLAG"
    assert session.reason_codes == ["TEXT_SIGNAL_SEIZURE"]
    assert session.last_question == FEVER_PROTOCOL.patient_red_flag_message
    mock.assert_not_called()


def test_a_negated_red_flag_phrase_does_not_escalate(monkeypatch) -> None:
    _broken_llm(monkeypatch)
    store = _store()
    session = store.start_session()

    store.submit_message(session.session_id, "Bé không co giật, không tím môi")

    assert session.state is SessionState.COLLECTING
    assert session.triage_level != "EMERGENCY"


def test_an_ambiguous_signal_is_confirmed_deterministically_when_the_model_returns_nothing(monkeypatch) -> None:
    """Đây là khoảng trống defense-in-depth: model hỏng + người bệnh vừa nhắc dấu hiệu nguy hiểm."""
    _broken_llm(monkeypatch)
    store = _store()
    session = store.start_session()
    cluster_before = session.current_cluster

    store.submit_message(session.session_id, "Em bé bị sưng họng")

    assert "xác nhận" in session.last_question
    assert "sưng họng" in session.last_question.lower()
    assert session.pending_safety_signals == ("throat_swelling",)
    # Giữ nguyên cụm: lượt sau vẫn trích theo đúng schema đang hỏi dở.
    assert session.current_cluster is cluster_before
    assert session.conversation[-1]["content"] == session.last_question


def test_the_same_ambiguous_signal_is_only_confirmed_once(monkeypatch) -> None:
    """Model hỏng nhiều lượt liên tiếp không được biến thành vòng lặp hỏi lại cùng một câu."""
    _broken_llm(monkeypatch)
    store = _store()
    session = store.start_session()

    store.submit_message(session.session_id, "Em bé bị sưng họng")
    first = session.last_question
    store.submit_message(session.session_id, "Em bé bị sưng họng")

    assert session.last_question != first
    assert session.asked_safety_signal_codes == {"throat_swelling"}
