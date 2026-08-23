"""Protocol phi lâm sàng (§4.10) và controller shadow mode (§4.11 bước 1).

Hai cơ chế khác nhau nhưng cùng một bất biến: **cả hai đều không được đụng tới quyết định lâm sàng.**
Lane phi lâm sàng không sinh red flag và không đổi `answers`; shadow mode không đổi gì cả.
"""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from src import paths
from src.config import Settings, get_settings
from src.services.infra import hf_zero_shot, provider_router
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
        "Cho mình hỏi cửa hàng có bán áo thun nam size L không vậy shop?",
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


@pytest.fixture
def no_chitchat_llm(monkeypatch):
    """Tắt tầng LLM của lane phi lâm sàng.

    Ba bài dưới đây kiểm ĐƯỜNG ĐI (lượt này không được chạm vào checklist), không kiểm cách diễn đạt.
    Tắt LLM để câu trả lời là bản tĩnh tất định - nếu không, mỗi lần đổi prompt là một lần ba bài này
    đỏ vì lý do không liên quan gì tới thứ chúng bảo vệ."""
    monkeypatch.setattr(get_settings(), "chitchat_llm_enabled", False)


def test_opening_out_of_scope_question_is_answered_without_starting_a_checklist(
    monkeypatch, no_chitchat_llm,
):
    """⚠️ Hợp đồng đổi 2026-08-23: lane phi lâm sàng nay CÓ gọi model để viết câu trả lời
    (`chitchat.compose`). Thứ KHÔNG được đổi - và là thứ bài này giữ - là nó không bao giờ chạm tới
    extractor, checklist hay snapshot. Spy ở đây vì thế bắt đúng `complete_stream` (bước synthesis
    của đường lâm sàng), còn `complete` bị chặn bằng cách tắt cờ chitchat."""
    spy = Mock(side_effect=AssertionError("Câu ngoài phạm vi không được đi vào đường lâm sàng"))
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


def test_opening_shop_question_is_out_of_scope_not_repeated_as_opening_question(monkeypatch, no_chitchat_llm):
    spy = Mock(side_effect=AssertionError("Câu hỏi mua hàng không được gọi model"))
    monkeypatch.setattr(provider_router, "complete", spy)
    monkeypatch.setattr(provider_router, "complete_stream", spy)
    store = ProtocolSessionStore(default_protocol=None)
    session = store.start_session()

    session = store.submit_message(
        session.session_id,
        "Cho mình hỏi cửa hàng có bán áo thun nam size L không vậy shop?",
    )

    assert session.phase is SessionPhase.OPENING
    assert session.protocol_name == ""
    assert session.current_cluster is None
    assert "ngoài" in session.last_question.casefold() or "chưa hỗ trợ" in session.last_question.casefold()
    assert "khó chịu thế nào" not in session.last_question.casefold()
    spy.assert_not_called()


def test_opening_unknown_non_medical_question_uses_model_domain_classifier(monkeypatch, no_chitchat_llm):
    """`no_chitchat_llm`: bài này ĐẾM số lời gọi model của tầng ĐỊNH TUYẾN. Từ 2026-08-23 lượt phi
    lâm sàng còn thêm một lời gọi nữa để VIẾT câu trả lời (`chitchat.compose`), nên không tắt thì
    `call_count` đếm cả hai và bài đo sai thứ nó định đo."""
    def complete(messages, *, credential=None, temperature=None, max_attempts=3, role=None):
        return provider_router.CompletionResult(
            text=json.dumps({"medical_domain": False, "lane": "out_of_scope", "confidence": 0.96}),
            provider="fake",
            model="fake",
        )

    mock = Mock(side_effect=complete)
    monkeypatch.setattr(provider_router, "complete", mock)
    store = ProtocolSessionStore(default_protocol=None)
    session = store.start_session()

    session = store.submit_message(session.session_id, "Máy in báo lỗi kẹt giấy thì xử lý sao?")

    assert session.phase is SessionPhase.OPENING
    assert session.protocol_name == ""
    assert session.current_cluster is None
    assert "khó chịu thế nào" not in session.last_question.casefold()
    assert "triệu chứng" in session.last_question.casefold()
    assert mock.call_count == 1


def test_domain_classifier_fail_open_keeps_the_opening_flow(monkeypatch):
    calls = {"n": 0}

    def complete(messages, *, credential=None, temperature=None, max_attempts=3, role=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("domain classifier timeout")
        return provider_router.CompletionResult(text=json.dumps({}), provider="fake", model="fake")

    monkeypatch.setattr(provider_router, "complete", Mock(side_effect=complete))
    store = ProtocolSessionStore(default_protocol=None)
    session = store.start_session()

    session = store.submit_message(session.session_id, "Tôi hơi mệt trong người")

    assert session.phase is SessionPhase.OPENING
    assert session.protocol_name == ""
    assert session.last_question
    assert calls["n"] >= 2


def test_low_confidence_domain_classifier_does_not_block_clinical_flow(monkeypatch):
    calls = {"n": 0}

    def complete(messages, *, credential=None, temperature=None, max_attempts=3, role=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return provider_router.CompletionResult(
                text=json.dumps({"medical_domain": False, "lane": "out_of_scope", "confidence": 0.4}),
                provider="fake",
                model="fake",
            )
        return provider_router.CompletionResult(text=json.dumps({}), provider="fake", model="fake")

    monkeypatch.setattr(provider_router, "complete", Mock(side_effect=complete))
    store = ProtocolSessionStore(default_protocol=None)
    session = store.start_session()

    session = store.submit_message(session.session_id, "Tôi thấy người không ổn")

    assert session.phase is SessionPhase.OPENING
    assert session.protocol_name == ""
    assert "khó chịu thế nào" in session.last_question.casefold()
    assert calls["n"] >= 2


def _zero_shot_settings(**overrides) -> Settings:
    return Settings(_env_file=None, huggingface_api_key="hf_test_key", **overrides)


def test_zero_shot_classifier_is_off_by_default(monkeypatch):
    """Công tắc mặc định TẮT (§ config.py) - dịch vụ phụ trợ chưa eval không được tự bật, và test
    không được gọi mạng thật chỉ vì máy dev có sẵn `HUGGINGFACE_API_KEY` trong `.env`."""
    monkeypatch.setattr(
        hf_zero_shot, "classify",
        Mock(side_effect=AssertionError("bộ lọc tắt thì không được gọi HF Inference API")),
    )

    assert non_clinical.classify_with_zero_shot("cửa hàng có bán áo thun size L không").lane is NonClinicalLane.NONE


def test_confident_zero_shot_result_skips_the_llm_domain_classifier(monkeypatch):
    """Đúng lý do dùng bộ lọc rẻ: kết luận chắc chắn thì không cần gọi thêm một lượt LLM."""
    settings = _zero_shot_settings(enable_hf_zero_shot_domain_classifier=True)
    monkeypatch.setattr(non_clinical, "get_settings", lambda: settings)
    monkeypatch.setattr(
        hf_zero_shot, "classify",
        Mock(
            return_value=[
                hf_zero_shot.ZeroShotResult(label="triệu chứng hoặc vấn đề sức khỏe cụ thể", score=0.1),
                hf_zero_shot.ZeroShotResult(
                    label="mua bán, cửa hàng, giao thông, hoặc chủ đề không liên quan y tế", score=0.9,
                ),
            ]
        ),
    )
    spy = Mock(side_effect=AssertionError("kết quả zero-shot đủ tin cậy thì không được gọi LLM"))
    monkeypatch.setattr(provider_router, "complete", spy)

    verdict = non_clinical.classify_with_model("cửa hàng có bán áo thun size L không")

    assert verdict.lane is NonClinicalLane.OUT_OF_SCOPE
    spy.assert_not_called()


def test_inconclusive_zero_shot_falls_through_to_the_llm_domain_classifier(monkeypatch):
    """Bộ lọc rẻ không chắc (tắt/lỗi/điểm thấp) -> vẫn phải rơi xuống LLM domain classifier như cũ,
    không được bỏ sót ca chỉ vì dịch vụ phụ trợ không trả lời được."""
    settings = _zero_shot_settings(enable_hf_zero_shot_domain_classifier=True)
    monkeypatch.setattr(non_clinical, "get_settings", lambda: settings)
    monkeypatch.setattr(hf_zero_shot, "classify", Mock(return_value=None))

    def complete(messages, *, credential=None, temperature=None, max_attempts=3, role=None):
        return provider_router.CompletionResult(
            text=json.dumps({"medical_domain": False, "lane": "out_of_scope", "confidence": 0.96}),
            provider="fake",
            model="fake",
        )

    mock = Mock(side_effect=complete)
    monkeypatch.setattr(provider_router, "complete", mock)

    verdict = non_clinical.classify_with_model("máy in báo lỗi kẹt giấy thì xử lý sao")

    assert verdict.lane is NonClinicalLane.OUT_OF_SCOPE
    mock.assert_called_once()


def test_opening_punctuation_only_reply_is_not_sent_to_the_checklist(monkeypatch, no_chitchat_llm):
    spy = Mock(side_effect=AssertionError("Tin chỉ có dấu câu không được đi vào đường lâm sàng"))
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


def test_opening_no_symptoms_statement_does_not_start_emergency_screening(
    monkeypatch, no_chitchat_llm,
):
    spy = Mock(side_effect=AssertionError("Không có triệu chứng thì không được gọi checklist"))
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


def test_opening_joking_gross_message_does_not_start_clinical_screening(monkeypatch, no_chitchat_llm):
    """Câu đùa ở lượt mở không được kéo phiên vào bộ câu hỏi lâm sàng.

    `no_chitchat_llm`: từ 2026-08-23 lane phi lâm sàng CÓ gọi model để viết câu trả lời, nên spy
    "không gọi model nào" chỉ còn đúng khi tắt cờ đó. Thứ bài này bảo vệ - không vào checklist -
    không đổi."""
    spy = Mock(side_effect=AssertionError("Câu đùa ở opening không được đi vào đường lâm sàng"))
    monkeypatch.setattr(provider_router, "complete", spy)
    monkeypatch.setattr(provider_router, "complete_stream", spy)
    store = ProtocolSessionStore(default_protocol=None)
    session = store.start_session()

    session = store.submit_message(session.session_id, "tôi muốn ăn cứt")

    assert session.phase is SessionPhase.OPENING
    assert session.protocol_name == ""
    assert session.current_cluster is None
    assert "triệu chứng" in session.last_question.casefold()
    assert "Khó thở nặng" not in session.last_question
    spy.assert_not_called()


def test_turning_the_chitchat_llm_off_restores_the_old_static_behaviour(monkeypatch, no_chitchat_llm):
    """`INVARIANTS.md` §4: tắt cờ thì hệ thống phải chạy đúng như trước khi có tính năng. Ở đây nghĩa
    là KHÔNG một lời gọi model nào cho lượt phi lâm sàng, và câu trả lời là bản tĩnh nguyên văn."""
    spy = Mock(side_effect=AssertionError("Tắt cờ mà vẫn gọi model"))
    monkeypatch.setattr(provider_router, "complete", spy)
    store = ProtocolSessionStore(default_protocol=None)
    session = store.start_session()

    session = store.submit_message(session.session_id, "chào bạn")

    assert session.last_question in non_clinical.CHITCHAT_REPLIES
    assert session.llm_used_last_turn is False
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
