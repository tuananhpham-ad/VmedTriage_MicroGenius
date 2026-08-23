"""Lane phi lâm sàng §4.10 — classifier bằng model NLI + LLM viết câu trả lời.

Hai tầng mới, và mỗi tầng có đúng một bài chặn:

- `lane_model`: **model không bao giờ được nhìn thấy một tin nhắn đã có dấu hiệu lâm sàng.** Đó là
  thứ khiến một classifier xác suất không thể lật một ca thật thành chitchat.
- `chitchat`: **mọi đường hỏng đều rơi về đúng câu tĩnh đang chạy hôm nay.** Tắt cờ, model chết,
  guard từ chối - ba đường, một đích.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from src import paths
from src.config import get_settings
from src.services.infra import provider_router
from src.services.symptom_protocol import chitchat, lane_model, non_clinical, output_guard
from src.services.symptom_protocol.non_clinical import NonClinicalLane
from src.services.symptom_protocol.session import ProtocolSessionStore, SessionPhase

_GOOD_REPLY = "Chào bạn, mình đây. Bạn đang thấy khó chịu ở đâu không?"


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LOGS_DIR", tmp_path)
    lane_model.reset_for_tests()
    yield
    lane_model.reset_for_tests()


@pytest.fixture
def model_on(monkeypatch):
    monkeypatch.setattr(get_settings(), "enable_hf_zero_shot_domain_classifier", True)


def _fake_model(label: str, score: float) -> Mock:
    """Giả `transformers.pipeline(...)` - một callable trả về dict labels/scores đã xếp hạng."""
    return Mock(return_value={"labels": [label], "scores": [score]})


def _install(monkeypatch, model: Mock) -> None:
    monkeypatch.setattr(lane_model, "_build_classifier", Mock(return_value=model))


# --- lane_model: ai được hỏi, khi nào -----------------------------------------------------------


def test_the_model_never_sees_a_message_that_already_looks_clinical(monkeypatch, model_on):
    """⚠️ BÀI CHẶN của tầng model. "tôi bị sốt" đã có marker lâm sàng ⇒ tầng keyword CHỐT, và model
    không được gọi. Nếu nó được gọi thì một phán quyết xác suất có cửa lật một ca thật thành lượt
    tán gẫu - đúng thứ không được phép xảy ra dù model tốt tới đâu."""
    model = _fake_model("lời chào hỏi, cảm ơn hoặc trò chuyện xã giao", 0.99)
    _install(monkeypatch, model)

    keyword = non_clinical.classify("tôi bị sốt 2 hôm nay")
    verdict = lane_model.classify("tôi bị sốt 2 hôm nay", keyword_verdict=keyword)

    assert keyword.is_undecided is False
    assert verdict.lane is NonClinicalLane.NONE
    model.assert_not_called()


def test_the_model_is_asked_only_when_keywords_cannot_decide(monkeypatch, model_on):
    """Câu tiếng Anh, không marker lâm sàng, không cụm từ nào khớp - đây đúng là phần đuôi dài mà
    sàn tất định mù, và là lý do model được chọn là model ĐA NGỮ."""
    model = _fake_model("lời chào hỏi, cảm ơn hoặc trò chuyện xã giao", 0.93)
    _install(monkeypatch, model)
    message = "just wondering what this thing does"

    keyword = non_clinical.classify(message)
    verdict = lane_model.classify(message, keyword_verdict=keyword)

    assert keyword.is_undecided is True
    assert verdict.lane is NonClinicalLane.CHITCHAT
    assert verdict.source == "model"
    assert verdict.score == pytest.approx(0.93)


def test_a_low_confidence_verdict_falls_back_to_the_clinical_path(monkeypatch, model_on):
    """"Không chắc" ở lane này phải rơi về đường LÂM SÀNG. Định tuyến nhầm một câu tán gẫu vào bộ
    câu hỏi chỉ tốn một câu hỏi thừa; nhầm theo chiều kia là bỏ một ca."""
    _install(monkeypatch, _fake_model("câu hỏi về chủ đề không liên quan tới sức khỏe", 0.41))
    message = "cho mình hỏi cái này với"

    verdict = lane_model.classify(message, keyword_verdict=non_clinical.classify(message))

    assert verdict.lane is NonClinicalLane.NONE
    assert verdict.source == "keyword"


def test_the_clinical_label_must_exist_so_the_model_can_say_no(monkeypatch, model_on):
    """Zero-shot chấm điểm TƯƠNG ĐỐI giữa các nhãn được đưa - nó không có quyền trả lời "không nhãn
    nào cả". Thiếu nhãn lâm sàng thì mọi tin nhắn, kể cả lời kể bệnh, buộc phải rơi vào một lane phi
    lâm sàng nào đó."""
    assert lane_model.CLINICAL_LABEL in lane_model._LABEL_LIST

    _install(monkeypatch, _fake_model(lane_model.CLINICAL_LABEL, 0.97))
    message = "chuyện này hơi khó nói"

    verdict = lane_model.classify(message, keyword_verdict=non_clinical.classify(message))

    assert verdict.lane is NonClinicalLane.NONE


def test_a_dead_model_never_breaks_the_turn(monkeypatch, model_on):
    _install(monkeypatch, Mock(side_effect=RuntimeError("model chết")))
    message = "cho mình hỏi cái này với"

    verdict = lane_model.classify(message, keyword_verdict=non_clinical.classify(message))

    assert verdict.lane is NonClinicalLane.NONE


def test_a_missing_library_is_remembered_instead_of_retried_every_turn(monkeypatch, model_on):
    """Thiếu `transformers` hay thiếu trọng số là một sự thật ổn định của môi trường. Thử lại mỗi
    lượt chỉ là trả tiền cho cùng một lỗi, mỗi lượt một lần."""
    build = Mock(side_effect=ImportError("No module named 'transformers'"))
    monkeypatch.setattr(lane_model, "_build_classifier", build)

    for _ in range(3):
        lane_model.classify("gì đó", keyword_verdict=non_clinical.classify("gì đó"))

    assert build.call_count == 1
    assert lane_model.available() is False


def test_the_flag_off_means_the_model_is_never_built(monkeypatch):
    """`INVARIANTS.md` §4: tắt cờ thì hệ thống chạy y hệt hôm nay - kể cả không nạp model."""
    build = Mock(side_effect=AssertionError("Tắt cờ mà vẫn dựng model"))
    monkeypatch.setattr(lane_model, "_build_classifier", build)

    verdict = lane_model.classify("hello", keyword_verdict=non_clinical.classify("hello"))

    assert verdict.source == "keyword"
    build.assert_not_called()


# --- chitchat: ba đường hỏng, một đích ----------------------------------------------------------


def test_the_llm_reply_is_used_when_the_guard_accepts_it(monkeypatch):
    monkeypatch.setattr(
        provider_router, "complete",
        Mock(return_value=provider_router.CompletionResult(text=_GOOD_REPLY, provider="f", model="f")),
    )

    text, used = chitchat.compose("chào bạn", NonClinicalLane.CHITCHAT, fallback="TĨNH?")

    assert text == _GOOD_REPLY
    assert used is True


@pytest.mark.parametrize(
    ("reply", "violation"),
    [
        ("Không sao đâu bạn, yên tâm nhé. Bạn thấy trong người thế nào?", output_guard.VIOLATION_REASSURANCE),
        ("Nghe như bạn bị cúm rồi. Bạn thấy trong người thế nào?", output_guard.VIOLATION_DIAGNOSIS),
        ("Bạn nên uống paracetamol nhé. Bạn thấy sao rồi?", output_guard.VIOLATION_DIAGNOSIS),
        ("Chào bạn nhé.", output_guard.VIOLATION_NOT_A_QUESTION),
    ],
)
def test_a_reply_that_breaks_a_rule_falls_back_to_the_static_text(monkeypatch, reply, violation):
    """Trấn an là vi phạm dễ bỏ qua nhất vì nó không trông giống lỗi - nó trông giống sự tử tế.
    "Không sao đâu" là một KẾT LUẬN lâm sàng khi hệ thống chưa hỏi được gì."""
    monkeypatch.setattr(
        provider_router, "complete",
        Mock(return_value=provider_router.CompletionResult(text=reply, provider="f", model="f")),
    )
    assert violation in output_guard.check_chitchat(reply).violations

    text, used = chitchat.compose("chào bạn", NonClinicalLane.CHITCHAT, fallback="TĨNH?")

    assert text == "TĨNH?"
    assert used is False


def test_a_dead_provider_falls_back_to_the_static_text(monkeypatch):
    monkeypatch.setattr(provider_router, "complete", Mock(side_effect=RuntimeError("provider chết")))

    text, used = chitchat.compose("chào bạn", NonClinicalLane.CHITCHAT, fallback="TĨNH?")

    assert (text, used) == ("TĨNH?", False)


def test_the_flag_off_falls_back_without_calling_anything(monkeypatch):
    monkeypatch.setattr(get_settings(), "chitchat_llm_enabled", False)
    spy = Mock(side_effect=AssertionError("Tắt cờ mà vẫn gọi model"))
    monkeypatch.setattr(provider_router, "complete", spy)

    text, used = chitchat.compose("chào bạn", NonClinicalLane.CHITCHAT, fallback="TĨNH?")

    assert (text, used) == ("TĨNH?", False)
    spy.assert_not_called()


def test_the_lifestyle_prompt_forbids_answering_the_question_itself(monkeypatch):
    """Lifestyle là lane sát y khoa nhất: "uống bia khi đang dùng kháng sinh có sao không" phải được
    THU THẬP rồi BÀN GIAO, không được trả lời (§4.10, `CLAUDE.md` nguyên tắc 2)."""
    captured: list[str] = []

    def capture(messages, **kwargs):
        captured.append(messages[0]["content"])
        return provider_router.CompletionResult(text=_GOOD_REPLY, provider="f", model="f")

    monkeypatch.setattr(provider_router, "complete", capture)

    chitchat.compose("uống bia có sao không", NonClinicalLane.LIFESTYLE, fallback="TĨNH?")

    assert "TUYỆT ĐỐI không tự trả lời câu hỏi đó" in captured[0]
    assert "nhân viên y tế" in captured[0]


def test_the_static_text_is_handed_to_the_model_as_the_intent(monkeypatch):
    """Câu tĩnh đi vào prompt làm "Ý CẦN NÓI" chứ không phải để model chép. Bỏ nó ra thì model tự
    nghĩ mục đích của lượt, và cái nó hay nghĩ ra là trấn an."""
    captured: list[str] = []

    def capture(messages, **kwargs):
        captured.append(messages[0]["content"])
        return provider_router.CompletionResult(text=_GOOD_REPLY, provider="f", model="f")

    monkeypatch.setattr(provider_router, "complete", capture)

    chitchat.compose("chào bạn", NonClinicalLane.CHITCHAT, fallback="CÂU TĨNH CỦA LANE?")

    assert "CÂU TĨNH CỦA LANE?" in captured[0]
    assert "Ý CẦN NÓI" in captured[0]


# --- ráp vào phiên -------------------------------------------------------------------------------


def test_a_greeting_now_gets_an_answer_instead_of_the_opening_question_again(monkeypatch):
    """Trước 2026-08-23: người bệnh chào, hệ thống lặp lại câu hỏi mở. Đó không phải một câu trả lời.

    Vẫn phải đúng ba thứ cũ: không vào protocol, không có cụm, snapshot rỗng."""
    monkeypatch.setattr(
        provider_router, "complete",
        Mock(return_value=provider_router.CompletionResult(text=_GOOD_REPLY, provider="f", model="f")),
    )
    store = ProtocolSessionStore(default_protocol=None)
    session = store.start_session()

    session = store.submit_message(session.session_id, "chào bạn")

    assert session.last_question == _GOOD_REPLY
    assert session.llm_used_last_turn is True
    assert session.phase is SessionPhase.OPENING
    assert session.protocol_name == ""
    assert session.current_cluster is None
    assert session.answers == {}


def test_the_weather_message_no_longer_pays_for_a_clinical_extraction(monkeypatch):
    """Bug đo được 2026-08-23: `"hôm nay trời đẹp nhỉ"` khớp marker `"om"` (ốm) NẰM TRONG chữ "hom",
    nên nó bị coi là chuyện lâm sàng và nạp trọn schema y tế (~2.530 token) để trích xuất. Khớp theo
    ranh giới từ đã chữa ca này."""
    monkeypatch.setattr(
        provider_router, "complete",
        Mock(return_value=provider_router.CompletionResult(text=_GOOD_REPLY, provider="f", model="f")),
    )
    verdict = non_clinical.classify("hôm nay trời đẹp nhỉ")

    assert verdict.clinical_markers == ()
    assert verdict.lane is NonClinicalLane.CHITCHAT


def test_a_clinical_message_still_goes_down_the_clinical_path(monkeypatch):
    """Lưới an toàn của cả file: mọi thứ ở trên không được đổi đường đi của một lời kể bệnh."""
    verdict = non_clinical.classify("tôi đau bụng dữ dội từ tối qua")

    assert verdict.is_non_clinical is False
    assert verdict.is_undecided is False
    assert "dau bung" in verdict.clinical_markers
