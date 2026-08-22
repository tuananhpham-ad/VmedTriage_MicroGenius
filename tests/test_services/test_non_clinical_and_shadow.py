"""Protocol phi lâm sàng (§4.10) và controller shadow mode (§4.11 bước 1).

Hai cơ chế khác nhau nhưng cùng một bất biến: **cả hai đều không được đụng tới quyết định lâm sàng.**
Lane phi lâm sàng không sinh red flag và không đổi `answers`; shadow mode không đổi gì cả.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from src import paths
from src.services.infra import provider_router
from src.services.symptom_protocol import controller_shadow, non_clinical
from src.services.symptom_protocol.non_clinical import NonClinicalLane
from src.services.symptom_protocol.session import ProtocolSessionStore, SessionPhase


@pytest.fixture(autouse=True)
def _isolated_log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LOGS_DIR", tmp_path)

# --- §4.10: lane phi lâm sàng ---------------------------------------------------------------------


@pytest.mark.parametrize("message", ["uống bia có sao không", "toi hay thuc khuya", "tập gym mỗi ngày ổn chứ"])
def test_a_lifestyle_question_without_symptoms_gets_the_lifestyle_lane(message: str):
    assert non_clinical.classify(message).lane is NonClinicalLane.LIFESTYLE


@pytest.mark.parametrize("message", ["bạn là ai vậy", "du lieu cua toi co bao mat khong", "bao lâu thì có kết quả"])
def test_a_question_about_the_system_gets_the_meta_lane(message: str):
    assert non_clinical.classify(message).lane is NonClinicalLane.META


@pytest.mark.parametrize("message", [".", "/", "???"])
def test_a_low_content_message_gets_a_specific_retry_lane(message: str):
    assert non_clinical.classify(message).lane is NonClinicalLane.LOW_CONTENT


@pytest.mark.parametrize(
    "message",
    [
        "Cho em hỏi xe buýt tuyến số 8 hiện tại còn chạy qua đường Nguyễn Trãi không",
        "xe bus tuyến này còn đi qua Nguyễn Trãi không",
    ],
)
def test_an_out_of_scope_question_gets_the_out_of_scope_lane(message: str):
    assert non_clinical.classify(message).lane is NonClinicalLane.OUT_OF_SCOPE


def test_an_opening_no_symptoms_statement_does_not_enter_the_clinical_lane():
    assert non_clinical.classify("mình không thấy khó chịu").lane is NonClinicalLane.NO_SYMPTOMS


def test_no_symptoms_does_not_hide_a_real_symptom():
    assert non_clinical.classify("mình không thấy khó chịu, chỉ hơi đau đầu").is_non_clinical is False


@pytest.mark.parametrize(
    "message",
    [
        "uống bia xong tôi đau bụng",
        "chạy bộ xong thấy tức ngực",
        "hút thuốc nhiều nên ho ra máu",
    ],
)
def test_any_clinical_marker_cancels_the_non_clinical_lane(message: str):
    """CA CHẶN của §4.10. Định tuyến nhầm một câu tán gẫu vào đường lâm sàng chỉ tốn một câu hỏi
    thừa; định tuyến nhầm một triệu chứng vào lifestyle là BỎ MỘT CA."""
    assert non_clinical.classify(message).is_non_clinical is False


def test_the_lifestyle_reply_collects_and_hands_off_instead_of_advising():
    """`CLAUDE.md` nguyên tắc 2. Cách xử lý đúng cho "uống bia khi đang dùng kháng sinh" là hỏi đang
    dùng thuốc gì / điều trị bệnh gì rồi bàn giao - KHÔNG hard-code một luật tương tác thuốc."""
    reply = non_clinical.reply_for(NonClinicalLane.LIFESTYLE)

    assert "thuốc" in reply and "?" in reply
    assert "không sao" not in reply.casefold(), "không được tự trấn an"


def test_the_meta_reply_says_plainly_it_is_not_a_doctor():
    reply = non_clinical.reply_for(NonClinicalLane.META)

    assert "không phải bác sĩ" in reply.casefold()
    assert "nhân viên y tế" in reply.casefold()


def test_an_unknown_lane_has_no_reply():
    """`NONE` -> chuỗi rỗng, caller đi tiếp đường lâm sàng. Trả một câu mặc định ở đây sẽ nuốt mọi
    tin nhắn không khớp từ khoá nào."""
    assert non_clinical.reply_for(NonClinicalLane.NONE) == ""


def test_non_clinical_replies_can_vary_without_changing_lane_meaning():
    first = non_clinical.reply_for(NonClinicalLane.OUT_OF_SCOPE, variant_key=1)
    second = non_clinical.reply_for(NonClinicalLane.OUT_OF_SCOPE, variant_key=2)

    assert first != second
    for reply in (first, second):
        assert "y tế" in reply.casefold()
        assert "triệu chứng" in reply.casefold()


def test_opening_out_of_scope_question_is_answered_without_starting_a_checklist(monkeypatch):
    spy = Mock(side_effect=AssertionError("Câu ngoài phạm vi không được gọi model"))
    monkeypatch.setattr(provider_router, "complete", spy)
    monkeypatch.setattr(provider_router, "complete_stream", spy)
    store = ProtocolSessionStore(default_protocol=None)
    session = store.start_session()

    session = store.submit_message(
        session.session_id,
        "Cho em hỏi xe buýt tuyến số 8 hiện tại còn chạy qua đường Nguyễn Trãi không",
    )

    assert session.phase is SessionPhase.OPENING
    assert session.protocol_name == ""
    assert session.current_cluster is None
    assert "y tế" in session.last_question.casefold()
    assert "triệu chứng" in session.last_question.casefold()
    spy.assert_not_called()


def test_opening_punctuation_only_reply_is_not_sent_to_the_checklist(monkeypatch):
    spy = Mock(side_effect=AssertionError("Tin chỉ có dấu câu không được gọi model"))
    monkeypatch.setattr(provider_router, "complete", spy)
    monkeypatch.setattr(provider_router, "complete_stream", spy)
    store = ProtocolSessionStore(default_protocol=None)
    session = store.start_session()

    session = store.submit_message(session.session_id, ".")

    assert session.phase is SessionPhase.OPENING
    assert session.protocol_name == ""
    assert session.current_cluster is None
    assert "triệu chứng" in session.last_question.casefold()
    spy.assert_not_called()


def test_opening_no_symptoms_statement_does_not_start_emergency_screening(monkeypatch):
    spy = Mock(side_effect=AssertionError("Không có triệu chứng thì không được gọi checklist/model"))
    monkeypatch.setattr(provider_router, "complete", spy)
    monkeypatch.setattr(provider_router, "complete_stream", spy)
    store = ProtocolSessionStore(default_protocol=None)
    session = store.start_session()

    session = store.submit_message(session.session_id, "mình không thấy khó chịu")

    assert session.phase is SessionPhase.OPENING
    assert session.protocol_name == ""
    assert session.current_cluster is None
    assert "sức khỏe" in session.last_question.casefold() or "triệu chứng" in session.last_question.casefold()
    assert "Khó thở nặng" not in session.last_question
    spy.assert_not_called()


def test_non_clinical_protocols_stay_out_of_the_clinical_registry():
    """§4.10: trộn hai loại vào một registry sẽ hỏng cả hai. Một `SymptomProtocol` giả không field,
    không cụm, không luật triage sẽ chảy qua `stage_machine`/`coverage` và làm mọi chỉ số độ phủ vô
    nghĩa - mẫu số phình lên bằng những phiên chưa bao giờ là ca lâm sàng."""
    from src.services.symptom_protocol import registry

    assert "lifestyle" not in registry.PROTOCOL_REGISTRY
    assert "meta" not in registry.PROTOCOL_REGISTRY


# --- §4.11 bước 1: shadow mode --------------------------------------------------------------------


def test_stop_is_not_an_admissible_controller_action():
    """§4.11 ràng buộc 2. Ý định dừng chỉ đi qua `user_intent.stop` -> `user_can_continue` ->
    `should_stop`. Một model 4B không được là thứ kết thúc phiên khám."""
    assert "stop" not in controller_shadow.ACTIONS
    for state in ((True, True), (False, True), (False, False)):
        actions = controller_shadow.admissible_actions(
            is_opening=state[0], has_cluster=state[1], has_protocol=True, session_closed=False,
        )
        assert "stop" not in actions


def test_a_closed_session_can_only_summarize_or_hand_off():
    actions = controller_shadow.admissible_actions(
        is_opening=False, has_cluster=True, has_protocol=True, session_closed=True,
    )

    assert set(actions) == {controller_shadow.ACTION_SUMMARIZE, controller_shadow.ACTION_HANDOFF}


def test_a_broken_session_state_only_allows_handoff():
    """Fail closed: thiếu protocol hoặc thiếu cụm thì không có gì để model chọn ngoài bàn giao."""
    actions = controller_shadow.admissible_actions(
        is_opening=False, has_cluster=False, has_protocol=False, session_closed=False,
    )

    assert actions == (controller_shadow.ACTION_HANDOFF,)


def test_an_empty_admissible_set_falls_back_without_calling_the_model(monkeypatch):
    from unittest.mock import Mock

    from src.services.infra import provider_router

    spy = Mock()
    monkeypatch.setattr(provider_router, "complete", spy)

    proposal = controller_shadow.propose("gì đó", admissible=(), state_digest={})

    assert proposal.failed is True
    spy.assert_not_called()


def test_an_action_outside_the_admissible_set_is_rejected_not_guessed(monkeypatch):
    """Giao với tập hợp lệ. Đoán ý model là đúng thứ tập hợp lệ sinh ra để khỏi phải làm."""
    import json
    from unittest.mock import Mock

    from src.services.infra import provider_router

    payload = {"lane": "clinical", "next_action": "route_protocol", "confidence": 0.9}
    monkeypatch.setattr(
        provider_router, "complete",
        Mock(return_value=provider_router.CompletionResult(text=json.dumps(payload), provider="f", model="f")),
    )

    proposal = controller_shadow.propose(
        "gì đó", admissible=(controller_shadow.ACTION_EXTRACT,), state_digest={},
    )

    assert proposal.failed is True


def test_a_dead_model_is_a_fallback_not_a_crash(monkeypatch):
    """Đường fallback CHÍNH LÀ hệ thống hiện tại - đó là lý do rủi ro bước 1 bằng 0."""
    from unittest.mock import Mock

    from src.services.infra import provider_router

    monkeypatch.setattr(provider_router, "complete", Mock(side_effect=TimeoutError("chết")))

    proposal = controller_shadow.propose(
        "gì đó", admissible=(controller_shadow.ACTION_EXTRACT,), state_digest={},
    )

    assert proposal.failed is True


def test_stats_report_every_rate_with_its_denominator():
    """§8 câu cuối: mọi ngưỡng phần trăm phải đi kèm mẫu số. Không có mẫu số thì không phải gate."""
    stats = controller_shadow.ShadowStats()
    stats.record(
        controller_shadow.ControllerProposal(lane="clinical", next_action="extract", latency_ms=120),
        deterministic_action="extract",
    )
    stats.record(
        controller_shadow.ControllerProposal(lane="clinical", next_action="summarize", latency_ms=90),
        deterministic_action="extract",
    )
    stats.record(controller_shadow.ControllerProposal(failed=True), deterministic_action="extract")

    report = stats.as_dict()

    assert report["controller_agreement_rate"] == 0.5
    assert report["n_scored"] == 2
    assert report["n_turns"] == 3
    assert report["controller_fallback_rate"] == round(1 / 3, 4)
    assert report["disagreements"] == [{"model": "summarize", "code": "extract", "lane": "clinical"}]


def test_an_empty_run_reports_none_not_zero():
    """Chưa chạy lượt nào thì `agreement_rate` KHÔNG XÁC ĐỊNH, không phải 0% - gộp nó vào một bảng
    tổng hợp dưới dạng 0 sẽ kéo chỉ số xuống bằng những lần chạy chưa hề diễn ra."""
    report = controller_shadow.ShadowStats().as_dict()

    assert report["controller_agreement_rate"] is None
    assert report["controller_p95_ms"] is None
