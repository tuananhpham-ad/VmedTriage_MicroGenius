"""L1 `controller` — kế hoạch lượt, fail closed, và cổng router (§9 P2).

Hai bài quan trọng nhất ở đây là hai bài an toàn của §11:

- mục 5: "Controller luôn tạo plan hợp lệ bằng code; state lạ/thiếu phải fail closed về đường
  extraction + handoff, không gọi model để đoán plan";
- mục 7: "Router model KHÔNG được gọi ngoài bốn trigger ở §3.1" - đếm trên một transcript nhiều lượt,
  lượt trả lời bình thường trong cùng protocol phải là 0.

Bài thứ ba canh phần tiết kiệm chi phí (§7.4): lời chào thuần KHÔNG được gọi extractor, nhưng một
lời chào có kèm dấu hiệu đỏ thì PHẢI gọi - đây là chỗ hai tầng an toàn nối vào nhau.
"""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from src import paths
from src.services.engines.fever_protocol import FEVER_PROTOCOL
from src.services.infra import provider_router
from src.services.symptom_protocol import controller
from src.services.symptom_protocol.dialogue import DialogueAct
from src.services.symptom_protocol.models import QuestionCluster
from src.services.symptom_protocol.session import ProtocolSessionStore, SessionState

_CLUSTER = QuestionCluster("T-01", "1", ("fever_reported",), script_hint="Có sốt không")


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LOGS_DIR", tmp_path)
    controller.reset_router_gate_stats()


def _plan(**kwargs) -> controller.ExecutionPlan:
    defaults = {
        "message": "bé sốt 39 độ",
        "cluster": _CLUSTER,
        "protocol_name": "fever",
        "is_opening": False,
        "has_safety_signal": False,
    }
    return controller.build_execution_plan(**{**defaults, **kwargs})


# --- kế hoạch mặc định ----------------------------------------------------------------------------


def test_a_normal_turn_invokes_the_extractor() -> None:
    plan = _plan()
    assert plan.invoke_extractor is True
    assert plan.fail_closed is False
    assert plan.forced_act is None


def test_the_plan_is_deterministic() -> None:
    """§11 an toàn mục 5: plan do CODE tạo nên cùng input phải cho cùng plan, lần nào cũng vậy."""
    assert _plan() == _plan()


# --- fail closed (tiêu chí nghiệm thu 3) ------------------------------------------------------------


def test_a_missing_cluster_fails_closed_instead_of_guessing() -> None:
    plan = _plan(cluster=None)
    assert plan.fail_closed_reason == controller.FAIL_CLOSED_NO_CLUSTER
    assert plan.invoke_extractor is False


def test_a_missing_protocol_fails_closed() -> None:
    plan = _plan(protocol_name="")
    assert plan.fail_closed_reason == controller.FAIL_CLOSED_NO_PROTOCOL


def test_the_opening_turn_has_neither_cluster_nor_protocol_and_that_is_valid() -> None:
    """Lượt mở CHƯA có protocol lẫn cụm theo đúng thiết kế - fail closed ở đây là chặn nhầm chính
    lượt đầu tiên của mọi phiên."""
    plan = _plan(cluster=None, protocol_name="", is_opening=True)
    assert plan.fail_closed is False
    assert plan.invoke_extractor is True


# --- bỏ extractor cho lời chào (§7.4) ---------------------------------------------------------------


@pytest.mark.parametrize("message", ["chào bạn", "Xin chào!", "hello", "  chào bác sĩ  "])
def test_a_pure_greeting_skips_the_extractor(message: str) -> None:
    plan = _plan(message=message)
    assert plan.invoke_extractor is False
    assert plan.forced_act is DialogueAct.GREETING


@pytest.mark.parametrize(
    "message",
    ["chào bạn, bé nhà mình sốt 39 độ", "bé sốt", "không biết", "ok", "alo"],
)
def test_anything_beyond_a_greeting_still_invokes_the_extractor(message: str) -> None:
    """Danh sách lời chào là danh sách ĐÓNG: chỉ bỏ extractor khi tin nhắn KHÔNG THỂ chứa dữ kiện
    lâm sàng, không phải khi nó "trông giống lời chào"."""
    assert _plan(message=message).invoke_extractor is True


def test_a_greeting_with_a_safety_signal_still_invokes_the_extractor() -> None:
    """Chỗ hai tầng an toàn nối vào nhau: L0 thấy gì đó thì controller không được tự tin bỏ qua."""
    plan = _plan(message="chào bạn", has_safety_signal=True)
    assert plan.invoke_extractor is True
    assert plan.forced_act is None


# --- cổng router: đúng bốn trigger (§3.1) -----------------------------------------------------------


def _gate(**kwargs) -> str:
    defaults = {
        "is_opening": False,
        "act": DialogueAct.ANSWER,
        "recent_fields": frozenset(),
        "chief_complaint_field": "chief_complaint",
        "protocol_ruled_out": False,
    }
    return controller.should_consult_group_router(**{**defaults, **kwargs})


def test_a_normal_answer_in_the_same_protocol_consults_no_router() -> None:
    """§11 an toàn mục 7 - chốt chặn chống "chỉ gọi khi cần" trôi thành "gọi mọi lượt"."""
    assert _gate() == ""
    assert controller.router_gate_stats() == {"turns": 1, "consulted": 0}


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"is_opening": True}, controller.ROUTER_TRIGGER_OPENING),
        ({"act": DialogueAct.NEW_SYMPTOM}, controller.ROUTER_TRIGGER_NEW_SYMPTOM),
        ({"recent_fields": frozenset({"chief_complaint"})}, controller.ROUTER_TRIGGER_CHIEF_COMPLAINT),
        ({"protocol_ruled_out": True}, controller.ROUTER_TRIGGER_PROTOCOL_RULED_OUT),
    ],
)
def test_each_of_the_four_triggers_opens_the_gate(kwargs: dict, expected: str) -> None:
    assert _gate(**kwargs) == expected


def test_a_protocol_without_a_chief_complaint_field_does_not_trigger_on_it() -> None:
    """Fever biết trước than phiền là gì nên không khai `chief_complaint_field` - trigger 3 phải im."""
    assert _gate(chief_complaint_field="", recent_fields=frozenset({"chief_complaint"})) == ""


def test_the_gate_counts_every_turn_for_the_ratio_metric() -> None:
    _gate()
    _gate()
    _gate(is_opening=True)
    assert controller.router_gate_stats() == {"turns": 3, "consulted": 1}


# --- nối vào luồng phiên thật -----------------------------------------------------------------------


def _fake_llm(monkeypatch) -> Mock:
    def complete(messages, *, credential=None, temperature=None, max_attempts=3, role=None):
        system = messages[0]["content"]
        if "Ý CẦN HỎI" in system:
            return provider_router.CompletionResult(
                text="Dạ chào bạn, bé nhà mình bao nhiêu tuổi ạ?", provider="fake", model="fake",
            )
        return provider_router.CompletionResult(text=json.dumps({}), provider="fake", model="fake")

    mock = Mock(side_effect=complete)
    monkeypatch.setattr(provider_router, "complete", mock)
    return mock


def test_a_greeting_turn_costs_one_model_call_instead_of_two(monkeypatch) -> None:
    """Đo được: bỏ bước trích xuất tiết kiệm ~3.8s/lượt (`eval/baselines/2026-08-17-p0-summary.md`)."""
    mock = _fake_llm(monkeypatch)
    store = ProtocolSessionStore(default_protocol=FEVER_PROTOCOL)
    session = store.start_session()

    store.submit_message(session.session_id, "chào bạn")

    assert mock.call_count == 1
    prompts = [call.args[0][0]["content"] for call in mock.call_args_list]
    assert all("Ý CẦN HỎI" in prompt for prompt in prompts), "van con goi trich xuat"
    assert session.state is SessionState.COLLECTING
    assert session.last_question


def test_a_greeting_turn_keeps_the_current_cluster(monkeypatch) -> None:
    _fake_llm(monkeypatch)
    store = ProtocolSessionStore(default_protocol=FEVER_PROTOCOL)
    session = store.start_session()
    before = session.current_cluster

    store.submit_message(session.session_id, "xin chào")

    assert session.current_cluster is before


def test_an_invalid_session_state_hands_off_instead_of_going_silent(monkeypatch) -> None:
    """§11 an toàn mục 5. Bản cũ `return session` lặng lẽ: người bệnh gõ tin nhắn và không nhận được
    gì - kiểu hỏng tệ nhất vì nó trông giống như đang hoạt động bình thường."""
    mock = _fake_llm(monkeypatch)
    store = ProtocolSessionStore(default_protocol=FEVER_PROTOCOL)
    session = store.start_session()
    session.current_cluster = None  # trạng thái lạ: còn COLLECTING mà không có cụm nào

    store.submit_message(session.session_id, "bé sốt 39 độ")

    assert session.state is SessionState.AWAITING_CONFIRMATION
    assert session.last_question == controller.HANDOFF_MESSAGE
    assert session.stop_reason.startswith("INVALID_STATE")
    assert mock.call_count == 0, "fail closed ma van goi model de doan"
