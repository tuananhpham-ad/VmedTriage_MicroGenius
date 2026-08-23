"""Lane phi lâm sàng §4.10 — LLM viết câu trả lời thay cho văn bản tĩnh.

Bài chặn của cả file: **mọi đường hỏng đều rơi về đúng câu tĩnh đang chạy hôm nay.** Tắt cờ, model
chết, guard từ chối - ba đường, một đích. Đó là lý do tầng này bật được mặc định: hành vi tệ nhất
của nó bằng hành vi tốt nhất của bản trước nó.

Phần ĐỊNH TUYẾN (keyword -> zero-shot -> LLM domain classifier) có test riêng ở
`test_non_clinical_and_shadow.py`.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from src import paths
from src.config import get_settings
from src.services.infra import provider_router
from src.services.symptom_protocol import chitchat, non_clinical, output_guard
from src.services.symptom_protocol.non_clinical import NonClinicalLane
from src.services.symptom_protocol.session import ProtocolSessionStore, SessionPhase

_GOOD_REPLY = "Chào bạn, mình đây. Bạn đang thấy khó chịu ở đâu không?"


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LOGS_DIR", tmp_path)
    yield


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
