"""Công tắc ngắt (§9 P4 mục 5) - và điều quan trọng hơn: những gì KHÔNG tắt được.

Một đường quay lui chỉ đáng tin khi có người đi thử. Mỗi công tắc ở đây có hai bài: một bài chứng
minh nó thật sự đổi hành vi, một bài chứng minh nó KHÔNG đụng tới tầng an toàn. Nhóm thứ hai mới là
lý do file này tồn tại - công tắc mà vô tình tắt được `rule_engine` hay `output_guard` thì nguy hiểm
hơn hẳn bug mà nó định vá.
"""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from src import paths
from src.config import get_settings
from src.services.engines.fever_protocol import FEVER_PROTOCOL
from src.services.infra import provider_router
from src.services.symptom_protocol import coverage, flags, ranking, reducer, stage_machine
from src.services.symptom_protocol import intake_agent as agent
from src.services.symptom_protocol.session import ProtocolSessionStore, SessionState

_RENDERED_QUESTION = "Dạ cho mình hỏi thêm một ý nữa ạ?"


@pytest.fixture(autouse=True)
def _isolated_log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LOGS_DIR", tmp_path)


@pytest.fixture
def switch(monkeypatch):
    """Đổi một công tắc trên bản `Settings` đang được `lru_cache` giữ.

    Sửa thẳng đối tượng đã cache chứ không xoá cache: `get_settings` được import ở nhiều module,
    xoá cache giữa chừng sẽ dựng lại `Settings` từ `.env` của máy chạy test và bài test hoá ra phụ
    thuộc môi trường."""
    settings = get_settings()
    def _set(name: str, value: bool) -> None:
        monkeypatch.setattr(settings, name, value)
    return _set


@pytest.fixture
def fake_llm(monkeypatch):
    pending: dict[str, object] = {}

    def complete(messages, *, credential=None, temperature=None, max_attempts=3, role=None):
        system = messages[0]["content"]
        if "Ý CẦN HỎI" in system:
            return provider_router.CompletionResult(text=_RENDERED_QUESTION, provider="fake", model="fake")
        body = {key: value for key, value in pending.items() if key in system}
        body["answer_quality"] = "answered"
        return provider_router.CompletionResult(text=json.dumps(body), provider="fake", model="fake")

    mock = Mock(side_effect=complete)
    monkeypatch.setattr(provider_router, "complete", mock)

    def feed(payload: dict[str, object]) -> None:
        pending.clear()
        pending.update(payload)

    feed.mock = mock  # type: ignore[attr-defined]
    return feed


def _fever_session(store: ProtocolSessionStore):
    session = store.start_session(protocol_name=FEVER_PROTOCOL.name)
    session.answers.update({"fever_reported": "true", "temp_c": "39", "temp_site": "axillary"})
    return session


# --- mặc định: mọi công tắc BẬT ------------------------------------------------------------------


def test_every_switch_defaults_to_on() -> None:
    """Đây là đường quay lui, không phải nút bật tính năng: cấu hình trống phải cho hành vi ĐẦY ĐỦ.

    Nếu bài này đỏ thì một môi trường quên khai biến sẽ lặng lẽ chạy bản rút gọn - đúng loại sai lệch
    mà không ai phát hiện ra cho tới khi đọc transcript."""
    assert flags.ranking_enabled()
    assert flags.synthesis_enabled()
    assert flags.retraction_confirmation_enabled()
    assert flags.unset_operation_enabled()


def test_a_switch_is_read_per_call_not_frozen_at_import(switch) -> None:
    """Không có hằng số module nào đóng băng giá trị ở thời điểm import - nếu có thì THỨ TỰ IMPORT
    quyết định hành vi, loại lỗi rất khó nhìn ra.

    Lưu ý phạm vi: `get_settings()` vẫn được `lru_cache` giữ, nên đổi biến môi trường thật vẫn cần
    khởi động lại tiến trình. Công tắc rút quy trình xuống "đổi biến + restart", không phải "bật tắt
    nóng"."""
    switch("agent_synthesis_enabled", False)
    assert not flags.synthesis_enabled()


# --- công tắc `unset` ------------------------------------------------------------------------------


def test_turning_off_unset_keeps_the_value_the_model_wanted_to_delete(switch, fake_llm) -> None:
    switch("agent_unset_operation_enabled", False)
    store = ProtocolSessionStore(default_protocol=FEVER_PROTOCOL)
    session = _fever_session(store)
    session.current_cluster = next(c for c in FEVER_PROTOCOL.clusters if "temp_c" in c.fields)

    fake_llm({"temp_c": {"operation": "unset", "evidence_span": "39 đó là nhiệt độ phòng"}})
    store.submit_message(session.session_id, "À con số 39 đó là nhiệt độ phòng, mình chưa đo lại.")

    assert session.answers["temp_c"] == "39"


def test_turning_off_unset_does_not_disable_the_parent_negation_path(switch, fake_llm) -> None:
    """Công tắc chỉ tắt cơ chế MỚI. Đường xoá dây chuyền qua phủ định field cha có từ trước P2.4 và
    phải chạy nguyên vẹn - nếu không, công tắc này đang tắt nhiều hơn nó hứa."""
    switch("agent_unset_operation_enabled", False)
    store = ProtocolSessionStore(default_protocol=FEVER_PROTOCOL)
    session = _fever_session(store)
    session.current_cluster = FEVER_PROTOCOL.clusters[0]

    fake_llm({"fever_reported": {"value": "false", "evidence_span": "mình không sốt"}})
    store.submit_message(session.session_id, "Mình quên mất, mình không sốt.")

    assert session.answers["fever_reported"] == "false"
    assert session.answers["temp_c"] == "unknown"


# --- công tắc cổng xác nhận đính chính -------------------------------------------------------------


def test_turning_off_the_confirmation_applies_the_risky_correction_immediately(switch, fake_llm) -> None:
    switch("agent_retraction_confirmation_enabled", False)
    store = ProtocolSessionStore(default_protocol=FEVER_PROTOCOL)
    session = _fever_session(store)
    session.current_cluster = FEVER_PROTOCOL.clusters[0]

    fake_llm({"fever_reported": {"value": "false", "evidence_span": "không phải sốt xuất huyết"}})
    store.submit_message(session.session_id, "Bác sĩ bảo không phải sốt xuất huyết đâu ạ.")

    assert session.answers["fever_reported"] == "false"
    assert session.last_question == _RENDERED_QUESTION  # không có câu xác nhận nào chen vào


def test_turning_off_the_confirmation_leaves_the_l0_safety_layer_untouched(switch, fake_llm) -> None:
    """Cổng xác nhận đính chính và tầng L0 là hai cơ chế khác nhau dùng chung một kiểu "câu tĩnh, giữ
    nguyên cụm". Tắt cái này không được đụng cái kia - L0 là tầng an toàn (§8.1 loại 1), không có
    công tắc nào, và nó phải chạy ngay cả khi model không trích được gì."""
    switch("agent_retraction_confirmation_enabled", False)
    store = ProtocolSessionStore(default_protocol=FEVER_PROTOCOL)
    session = store.start_session(protocol_name=FEVER_PROTOCOL.name)
    session.current_cluster = FEVER_PROTOCOL.clusters[0]

    fake_llm({})  # model không trích được gì - đúng kịch bản L0 sinh ra để chặn
    store.submit_message(session.session_id, "Bé đang co giật, tay chân giật liên tục.")

    assert session.state is SessionState.EMERGENCY
    assert session.escalation_lock


# --- công tắc xếp hạng -----------------------------------------------------------------------------


def test_turning_off_ranking_hands_the_selector_no_signal_at_all(switch) -> None:
    """`None` là ĐƯỜNG QUAY LUI của §8.3, không phải nhánh mới: không tín hiệu nào ⇒ mọi cụm hoà điểm
    ⇒ giữ thứ tự khai báo, tức first-fit. Cả hai hành vi dùng chung một đoạn code."""
    ledger = coverage.CoverageLedger()
    ledger.record_turn("Q4-02", frozenset({"Q4-01"}))
    recent = frozenset({"cough"})

    switch("agent_ranking_enabled", True)
    assert agent._ranking_context(recent, ledger) is not None

    switch("agent_ranking_enabled", False)
    assert agent._ranking_context(recent, ledger) is None


def test_ranking_off_really_changes_which_cluster_is_asked_next() -> None:
    """Công tắc phải đổi được hành vi thật, nếu không nó là một dòng cấu hình chết.

    Cùng `answers`, cùng `asked_ids`: có tín hiệu `recent_fields` thì cụm chứa field vừa được nhắc
    tới phải thắng; không có tín hiệu thì cụm đầu theo thứ tự khai báo thắng."""
    stage = "3A"
    clusters = [c for c in FEVER_PROTOCOL.clusters if c.stage == stage]
    assert len(clusters) > 1, "bài này cần một stage có nhiều cụm để so thứ tự"
    later = clusters[-1]

    first_fit = stage_machine.select_cluster(
        FEVER_PROTOCOL, stage, {}, asked_ids=frozenset(), context=None,
    )
    followed = stage_machine.select_cluster(
        FEVER_PROTOCOL, stage, {}, asked_ids=frozenset(),
        context=ranking.RankingContext(recent_fields=frozenset(later.fields)),
    )
    assert first_fit.cluster is not None and followed.cluster is not None
    assert first_fit.cluster.id == clusters[0].id
    assert followed.cluster.id == later.id


def test_ranking_off_does_not_touch_the_definition_of_coverage(switch) -> None:
    """Bất biến §8.2 mục 1: xếp hạng đổi THỨ TỰ, không đổi ĐỘ PHỦ. Độ phủ đọc tier field, và công tắc
    không đụng tới tier - hồ sơ rỗng phải "chưa đủ phủ" dù công tắc bật hay tắt."""
    empty: dict[str, object] = {}
    switch("agent_ranking_enabled", True)
    with_ranking = stage_machine.mandatory_fields_covered(FEVER_PROTOCOL, empty)
    switch("agent_ranking_enabled", False)
    assert stage_machine.mandatory_fields_covered(FEVER_PROTOCOL, empty) == with_ranking
    assert with_ranking is False


# --- những gì KHÔNG có công tắc --------------------------------------------------------------------


def test_no_switch_can_turn_off_a_safety_layer() -> None:
    """§8.1 loại 1. Danh sách này là hợp đồng: thêm một công tắc cho tầng an toàn sẽ làm bài này đỏ,
    và đó là lúc phải dừng lại chứ không phải sửa test."""
    public = {name for name in dir(flags) if not name.startswith("_")}
    switches = {name for name in public if name.endswith("_enabled")}
    assert switches == {
        "ranking_enabled",
        "synthesis_enabled",
        "retraction_confirmation_enabled",
        "unset_operation_enabled",
    }


def test_the_reducer_still_erases_dependents_with_every_switch_off(switch) -> None:
    """Xoá dây chuyền (§5 quy tắc 4) không phải tính năng hội thoại - nó là thứ giữ cho phiếu bàn giao
    khỏi mang một con số mà người bệnh đã rút lại."""
    switch("agent_retraction_confirmation_enabled", False)
    switch("agent_unset_operation_enabled", False)
    before = {"fever_reported": "true", "temp_c": "39"}
    event = reducer.FieldEvent("fever_reported", operation="set", value="false", evidence_span="không sốt")
    result = reducer.reduce(FEVER_PROTOCOL, before, (event,))
    assert result.answers["temp_c"] == "unknown"
