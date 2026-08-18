"""Sự kiện `unset` + cổng xác nhận đính chính, chạy QUA `session.submit_message` (§4/§5, P2.4-P2.5).

`test_reducer.py` kiểm reducer ở mức đơn vị. File này kiểm cái mà mức đơn vị không thấy được: sự kiện
có đi trọn đường từ JSON của model, qua guard bằng chứng, qua reducer, tới hồ sơ phiên hay không - và
lúc cổng xác nhận bật thì hội thoại có DỪNG lại đúng chỗ không.

LLM giả, không gọi mạng: cả hai cơ chế đều là tầng "KHÔNG model" hoặc guard quanh model, nên chúng
phải kiểm được mà không cần model thật.
"""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from src import paths
from src.services.engines.fever_protocol import FEVER_PROTOCOL
from src.services.infra import provider_router
from src.services.symptom_protocol.session import ProtocolSessionStore

_RENDERED_QUESTION = "Dạ cho mình hỏi thêm một ý nữa ạ?"


@pytest.fixture(autouse=True)
def _isolated_log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LOGS_DIR", tmp_path)


@pytest.fixture
def fake_llm(monkeypatch):
    """Trả về `feed(payload)` - đặt JSON mà bộ trích xuất sẽ "đọc được" ở lượt kế tiếp.

    Chỉ những khoá CÓ trong schema của lượt đó mới được trả về, giống hệt một model ngoan: nếu test
    có thể nhét field ngoài schema thì nó đang kiểm một hệ thống khác với hệ thống chạy thật."""
    pending: dict[str, object] = {}

    def complete(messages, *, credential=None, temperature=None, max_attempts=3, role=None):
        system = messages[0]["content"]
        if "Ý CẦN HỎI" in system:
            return provider_router.CompletionResult(text=_RENDERED_QUESTION, provider="fake", model="fake")
        body = {key: value for key, value in pending.items() if key in system}
        body["answer_quality"] = "answered"
        return provider_router.CompletionResult(text=json.dumps(body), provider="fake", model="fake")

    monkeypatch.setattr(provider_router, "complete", Mock(side_effect=complete))

    def feed(payload: dict[str, object]) -> None:
        pending.clear()
        pending.update(payload)

    return feed


def _session_with_fever_record(store: ProtocolSessionStore):
    """Phiên sốt đã có sẵn lời khai "39 độ, đo ở nách" - trạng thái mà mọi bài dưới đây đính chính."""
    session = store.start_session(protocol_name=FEVER_PROTOCOL.name)
    session.answers.update({"fever_reported": "true", "temp_c": "39", "temp_site": "axillary"})
    return session


# --- `unset`: năng lực mà một dict giá trị không diễn đạt được ------------------------------------


def test_unset_clears_a_number_without_negating_its_parent(fake_llm) -> None:
    """"Con số 39 đó là nhiệt độ phòng" KHÔNG phủ định `fever_reported`, nên không có field cha nào
    để xoá dây chuyền. Trước khi có sự kiện `unset`, `temp_c=39` đi thẳng vào phiếu bàn giao."""
    store = ProtocolSessionStore(default_protocol=FEVER_PROTOCOL)
    session = _session_with_fever_record(store)
    session.current_cluster = next(c for c in FEVER_PROTOCOL.clusters if "temp_c" in c.fields)

    fake_llm({"temp_c": {"operation": "unset", "evidence_span": "39 đó là nhiệt độ phòng"}})
    store.submit_message(session.session_id, "À con số 39 đó là nhiệt độ phòng, mình chưa đo lại.")

    assert session.answers["temp_c"] == "unknown"
    assert session.answers["fever_reported"] == "true"


def test_an_unset_without_evidence_is_refused(fake_llm) -> None:
    """§4.4: `unset` cũng phải có bằng chứng. Một lệnh xoá không chứng minh được là đường ngắn nhất
    để mất hồ sơ, và nó tốn của model đúng bằng một lệnh xoá thật."""
    store = ProtocolSessionStore(default_protocol=FEVER_PROTOCOL)
    session = _session_with_fever_record(store)
    session.current_cluster = next(c for c in FEVER_PROTOCOL.clusters if "temp_c" in c.fields)

    fake_llm({"temp_c": {"operation": "unset", "evidence_span": "câu này không có trong tin nhắn"}})
    store.submit_message(session.session_id, "Bé vẫn vậy thôi ạ.")

    assert session.answers["temp_c"] == "39"


def test_an_unknown_operation_label_is_never_read_as_a_delete(fake_llm) -> None:
    """Nhãn lạ rơi về `"set"`, không rơi về `"unset"`. Một lỗi chính tả của model không được biến
    thành lệnh xoá hồ sơ."""
    store = ProtocolSessionStore(default_protocol=FEVER_PROTOCOL)
    session = _session_with_fever_record(store)
    session.current_cluster = next(c for c in FEVER_PROTOCOL.clusters if "temp_c" in c.fields)

    fake_llm({"temp_c": {"operation": "delete", "value": "39", "evidence_span": "39 độ"}})
    store.submit_message(session.session_id, "Vẫn 39 độ ạ.")

    assert session.answers["temp_c"] == "39"


# --- cổng xác nhận: hội thoại phải DỪNG, không chỉ ghi log ----------------------------------------


def test_a_disease_name_negation_asks_before_erasing_anything(fake_llm) -> None:
    """Bug C2 ở dạng nguyên bản: "bé không sốt xuất huyết" phủ định một TÊN BỆNH.

    Ba điều phải cùng đúng - hồ sơ không đổi, người bệnh được hỏi lại, và câu hỏi là câu TĨNH chứ
    không phải câu do model viết (renderer trả `_RENDERED_QUESTION` cho mọi lượt diễn đạt)."""
    store = ProtocolSessionStore(default_protocol=FEVER_PROTOCOL)
    session = _session_with_fever_record(store)
    session.current_cluster = FEVER_PROTOCOL.clusters[0]

    fake_llm({"fever_reported": {"value": "false", "evidence_span": "không phải sốt xuất huyết"}})
    store.submit_message(session.session_id, "Bác sĩ bảo không phải sốt xuất huyết đâu ạ.")

    assert session.answers["fever_reported"] == "true"
    assert session.answers["temp_c"] == "39"
    assert session.last_question != _RENDERED_QUESTION
    assert "xác nhận" in session.last_question.casefold()


def test_the_cluster_does_not_advance_while_the_confirmation_is_pending(fake_llm) -> None:
    """Giữ nguyên cụm để lượt sau vẫn trích theo đúng schema đó - cùng lý do với `_safety_confirmation`.
    Đi tiếp lúc này nghĩa là câu xác nhận vừa hỏi sẽ không có chỗ nào đọc câu trả lời."""
    store = ProtocolSessionStore(default_protocol=FEVER_PROTOCOL)
    session = _session_with_fever_record(store)
    session.current_cluster = FEVER_PROTOCOL.clusters[0]
    before = session.current_cluster.id

    fake_llm({"fever_reported": {"value": "false", "evidence_span": "không phải sốt xuất huyết"}})
    store.submit_message(session.session_id, "Bác sĩ bảo không phải sốt xuất huyết đâu ạ.")

    assert session.current_cluster.id == before


def test_the_confirmation_is_asked_once_and_then_the_correction_lands(fake_llm) -> None:
    """Hỏi ĐÚNG MỘT LẦN mỗi field. Không có cổng này thì một người bệnh diễn đạt kiểu khó trích dẫn
    sẽ bị hỏi mãi cùng một câu và không bao giờ sửa được lời khai."""
    store = ProtocolSessionStore(default_protocol=FEVER_PROTOCOL)
    session = _session_with_fever_record(store)
    session.current_cluster = FEVER_PROTOCOL.clusters[0]

    fake_llm({"fever_reported": {"value": "false", "evidence_span": "không phải sốt xuất huyết"}})
    store.submit_message(session.session_id, "Bác sĩ bảo không phải sốt xuất huyết đâu ạ.")
    assert session.answers["fever_reported"] == "true"

    store.submit_message(session.session_id, "Đúng rồi, không phải sốt xuất huyết ạ.")
    assert session.answers["fever_reported"] == "false"
    assert session.answers["temp_c"] == "unknown"


def test_a_plain_correction_still_lands_on_the_first_try(fake_llm) -> None:
    """Cổng xác nhận phải HẸP. "Mình quên mất, mình không sốt" trích được nguyên văn triệu chứng nên
    nó đi thẳng - không lượt hỏi lại nào."""
    store = ProtocolSessionStore(default_protocol=FEVER_PROTOCOL)
    session = _session_with_fever_record(store)
    session.current_cluster = FEVER_PROTOCOL.clusters[0]

    fake_llm({"fever_reported": {"value": "false", "evidence_span": "mình không sốt"}})
    store.submit_message(session.session_id, "Mình quên mất, mình không sốt.")

    assert session.answers["fever_reported"] == "false"
    assert session.answers["temp_c"] == "unknown"
