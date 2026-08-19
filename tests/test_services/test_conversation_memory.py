"""Memory M1 — persist phiên đang dở + khoá composite (§4.9 + §7.5).

M1 là điều kiện tiên quyết của M2/M3, và bài quan trọng nhất ở đây là
`test_a_half_finished_session_survives_a_restart`: nó mô phỏng đúng cái mà `ARCHITECTURE.md` ghi là
đang hỏng - phiên đang dở mất khi tiến trình khởi động lại.
"""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from src import paths
from src.database import configure_database, create_tables, dispose_database
from src.services.engines.fever_protocol import FEVER_PROTOCOL
from src.services.infra import provider_router
from src.services.stores.conversation_store import (
    GUEST_USER_ID,
    SqliteConversationStore,
    dump_session,
    load_session,
)
from src.services.symptom_protocol.session import ProtocolSessionStore

PATIENT_A, PATIENT_B = 11, 22
_RENDERED_QUESTION = "Dạ cho mình hỏi thêm một ý nữa ạ?"


@pytest.fixture(autouse=True)
def _fresh_database(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LOGS_DIR", tmp_path)
    configure_database(f"sqlite+pysqlite:///{(tmp_path / 'test.db').as_posix()}")
    create_tables()
    try:
        yield
    finally:
        dispose_database()


@pytest.fixture
def fake_llm(monkeypatch):
    def complete(messages, *, credential=None, temperature=None, max_attempts=3, role=None):
        if "Ý CẦN HỎI" in messages[0]["content"]:
            return provider_router.CompletionResult(text=_RENDERED_QUESTION, provider="fake", model="fake")
        return provider_router.CompletionResult(
            text=json.dumps({"answer_quality": "answered"}), provider="fake", model="fake",
        )

    monkeypatch.setattr(provider_router, "complete", Mock(side_effect=complete))


def _store() -> ProtocolSessionStore:
    """Store PRODUCTION-like: có kho bền. Test khác dựng `ProtocolSessionStore(...)` trần và vẫn
    chạy thuần in-memory - đó là lý do `persist` là tham số chứ không phải import cứng."""
    return ProtocolSessionStore(FEVER_PROTOCOL, persist=SqliteConversationStore())


# --- §7.5 mục 1: khoá không đụng nhau ------------------------------------------------------------


def test_two_sessions_opened_in_the_same_second_do_not_collide():
    """⚠️ Lý do `conversation_id` phải là UUID chứ không phải timestamp: hai phiên mở cùng một giây
    sẽ đụng khoá nhau, và một timestamp trong khoá còn là metadata rò ra ngoài."""
    store = _store()

    first = store.start_session(protocol_name=FEVER_PROTOCOL.name)
    second = store.start_session(protocol_name=FEVER_PROTOCOL.name)

    assert first.session_id != second.session_id


def test_the_same_conversation_id_under_two_users_stays_separate():
    """Khoá là composite `user_id + conversation_id`, nên cùng một mã hội thoại dưới hai người dùng
    là hai bản ghi. Đây là thứ chặn đọc chéo hồ sơ - do hình dạng khoá, không do một câu `if`."""
    persist = SqliteConversationStore()
    store = _store()
    session = store.start_session(protocol_name=FEVER_PROTOCOL.name)
    session.answers["fever_reported"] = "true"

    persist.save(session, user_id=PATIENT_A)

    assert persist.get(session.session_id, user_id=PATIENT_A) is not None
    assert persist.get(session.session_id, user_id=PATIENT_B) is None


def test_history_only_returns_the_users_own_sessions():
    """§4.9 M3 điều kiện 2, và `CLAUDE.md` nguyên tắc 5. Cần test riêng vì đây là đường mà M3 sẽ đi."""
    persist = SqliteConversationStore()
    store = _store()
    persist.save(store.start_session(protocol_name=FEVER_PROTOCOL.name), user_id=PATIENT_A)
    persist.save(store.start_session(protocol_name=FEVER_PROTOCOL.name), user_id=PATIENT_B)

    assert len(persist.recent_for_user(PATIENT_A)) == 1
    assert len(persist.recent_for_user(PATIENT_B)) == 1


# --- §7.5 mục 2: sống qua restart ----------------------------------------------------------------


def test_a_half_finished_session_survives_a_restart(fake_llm):
    """CA CHẶN của M1. `_sessions` rỗng = một tiến trình mới; phiên phải quay lại từ DB thay vì rơi
    vào nhánh "phiên đã mất, mở phiên mới" - với người bệnh thì nhánh đó là phải kể lại từ đầu."""
    store = _store()
    session = store.start_session(protocol_name=FEVER_PROTOCOL.name)
    session.user_id = PATIENT_A
    store.submit_message(session.session_id, "bé 3 tuổi, gái")
    stage_before, turns_before = session.stage, session.turn_count

    restarted = _store()  # tiến trình mới: `_sessions` rỗng
    restored = restarted.get(session.session_id, user_id=PATIENT_A)

    assert restored is not None
    assert restored.turn_count == turns_before
    assert restored.stage == stage_before
    assert restored.answers == session.answers


def test_the_restored_session_can_keep_answering(fake_llm):
    """Khôi phục được nhưng không đi tiếp được thì chưa giải quyết gì. Cụm đang hỏi phải sống sót
    nguyên vẹn - lượt sau trích xuất theo schema của chính cụm đó."""
    store = _store()
    session = store.start_session(protocol_name=FEVER_PROTOCOL.name)
    session.user_id = PATIENT_A
    store.submit_message(session.session_id, "bé 3 tuổi, gái")

    restarted = _store()
    restored = restarted.get(session.session_id, user_id=PATIENT_A)
    assert restored is not None and restored.current_cluster is not None
    restarted.submit_message(session.session_id, "sốt 2 hôm nay")

    assert restored.turn_count == 2


def test_a_synthetic_batch_cluster_round_trips():
    """Cụm đang hỏi có thể là cụm TỔNG HỢP không nằm trong `protocol.clusters` (`BATCH-`, `SCREEN-`,
    `CATCH-ALL`). Lưu theo MÃ sẽ tra ra `None` sau restart, và lượt sau trích theo sai schema - im
    lặng, không lỗi nào nổ ra. Vì thế cụm được lưu ĐẦY ĐỦ."""
    from src.services.symptom_protocol import batching
    from src.services.symptom_protocol.models import QuestionCluster

    store = _store()
    session = store.start_session(protocol_name=FEVER_PROTOCOL.name)
    session.current_cluster = batching.batch_cluster(
        "2", (QuestionCluster("Q2-01", "2", ("fever_onset_at",), script_hint="hỏi"),),
    )

    restored = load_session(dump_session(session))

    assert restored.current_cluster is not None
    assert restored.current_cluster.id == session.current_cluster.id
    assert restored.current_cluster.fields == session.current_cluster.fields


# --- không được lưu ------------------------------------------------------------------------------


def test_the_api_credential_is_never_written_to_the_database():
    """Ghi khoá API vào DB để tiện khôi phục là đổi một bất tiện lấy một sự cố bảo mật."""
    store = _store()
    session = store.start_session(protocol_name=FEVER_PROTOCOL.name)
    session.credential = provider_router.LLMCredential(provider="gemini", api_key="SECRET-KEY-123")

    blob = json.dumps(dump_session(session), ensure_ascii=False)

    assert "SECRET-KEY-123" not in blob
    assert load_session(json.loads(blob)).credential is None


# --- khoan dung với payload cũ -------------------------------------------------------------------


def test_a_payload_written_before_a_new_field_existed_still_loads():
    """Từ chối nạp payload cũ nghĩa là mỗi lần deploy lại làm mất đúng những phiên đang dở - tức là
    đúng thứ M1 tồn tại để tránh."""
    restored = load_session({"session_id": "abc", "protocol_name": FEVER_PROTOCOL.name})

    assert restored.session_id == "abc"
    assert restored.turn_count == 0
    assert restored.uncooperative.streak == 0


def test_a_broken_database_never_breaks_the_conversation(monkeypatch):
    """`save` nuốt lỗi có chủ đích: mất một lần persist là mất khả năng khôi phục, còn ném ra ngoài
    là làm hỏng chính lượt người bệnh đang trả lời."""
    from src.services.stores import conversation_store as module

    monkeypatch.setattr(module, "session_scope", Mock(side_effect=RuntimeError("DB chết")))
    persist = SqliteConversationStore()
    store = ProtocolSessionStore(FEVER_PROTOCOL)
    session = store.start_session(protocol_name=FEVER_PROTOCOL.name)

    persist.save(session, user_id=GUEST_USER_ID)  # không được ném
    assert persist.get(session.session_id, user_id=GUEST_USER_ID) is None
