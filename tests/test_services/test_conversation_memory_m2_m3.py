"""Memory **M2** (nén context) + **M3** (ký ức xuyên phiên) — §4.9, `_guidance/features/F04_memory.md`.

M1 đã có test riêng (`test_conversation_memory.py`) và không được làm hỏng. File này lo hai bài chặn
của hai tầng còn lại, và cả hai đều là bài về thứ **KHÔNG được xảy ra**:

- M2: bản tóm tắt không bao giờ ghi đè snapshot. Bất đồng thì snapshot thắng - nó là thứ có
  `evidence_span`, bản tóm tắt thì không.
- M3: `previous fever = true` của phiên trước KHÔNG được nạp thành `current fever = true`. Đây là
  bất biến 9 (`INVARIANTS.md`), và là lằn ranh giữa "hỏi thăm" với "chẩn đoán bằng hồ sơ cũ".
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from src import paths
from src.config import get_settings
from src.database import configure_database, create_tables, dispose_database
from src.services.engines.fever_protocol import FEVER_PROTOCOL
from src.services.infra import provider_router
from src.services.sessions import history_recall
from src.services.stores.conversation_store import (
    SqliteConversationStore,
    dump_session,
    load_session,
)
from src.services.symptom_protocol import compaction, intake_agent
from src.services.symptom_protocol.session import ProtocolSessionStore, Session, SessionState

PATIENT_A, PATIENT_B = 11, 22
_SUMMARY_TEXT = "Người bệnh kể sốt hai ngày, không co giật."


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
def fake_summarizer(monkeypatch):
    monkeypatch.setattr(
        provider_router,
        "complete",
        Mock(return_value=provider_router.CompletionResult(
            text=_SUMMARY_TEXT, provider="fake", model="fake",
        )),
    )


@pytest.fixture
def tiny_budget(monkeypatch):
    """Ngưỡng nhỏ để test không phải dựng một hội thoại 2400 token chỉ để chạm tới bước nén."""
    settings = get_settings()
    monkeypatch.setattr(settings, "context_compaction_token_budget", 400)
    monkeypatch.setattr(settings, "context_compaction_keep_turns", 4)
    return settings


def _long_session(turns: int = 20) -> Session:
    session = Session(protocol_name=FEVER_PROTOCOL.name)
    for index in range(turns):
        session.conversation.append({"role": "assistant", "content": f"Câu hỏi số {index} " + "x" * 60})
        session.conversation.append({"role": "user", "content": f"Trả lời số {index} " + "y" * 60})
    return session


# --- M2 §5 mục 3: nén KHÔNG ghi đè snapshot -----------------------------------------------------


def test_compaction_never_touches_the_snapshot(fake_summarizer, tiny_budget):
    """CA CHẶN của M2. Summarizer nén PHẦN HỘI THOẠI; snapshot là nguồn sự thật và không nằm trong
    tầm với của nó."""
    session = _long_session()
    session.answers = {"fever_reported": "true", "seizure": "false"}
    snapshot_before = dict(session.answers)

    assert compaction.maybe_compact(session) is True

    assert session.answers == snapshot_before
    assert session.conversation_summary
    assert session.summarized_turns > 0


def test_the_snapshot_wins_when_the_summary_contradicts_it(tiny_budget, monkeypatch):
    """Bản tóm tắt nói "không sốt" trong khi snapshot ghi `fever_reported=true`. Snapshot phải
    thắng - và nó thắng vì bản tóm tắt KHÔNG CÓ đường nào chạm tới `answers`, chứ không vì một câu
    `if` xử lý bất đồng."""
    monkeypatch.setattr(
        provider_router,
        "complete",
        Mock(return_value=provider_router.CompletionResult(
            text="Người bệnh nói KHÔNG sốt.", provider="fake", model="fake",
        )),
    )
    session = _long_session()
    session.answers = {"fever_reported": "true"}

    compaction.maybe_compact(session)

    assert "KHÔNG sốt" in session.conversation_summary
    assert session.answers["fever_reported"] == "true"


def test_a_short_conversation_is_left_alone(fake_summarizer):
    """Ngưỡng chưa chạm thì không gọi model. Nén mọi lượt là trả tiền cho một lời gọi LLM để tiết
    kiệm một context chưa hề chật."""
    session = _long_session(turns=1)

    assert compaction.maybe_compact(session) is False
    assert session.conversation_summary == ""
    assert provider_router.complete.call_count == 0


def test_compaction_never_cuts_into_the_recent_window(fake_summarizer, tiny_budget):
    """Cửa sổ lượt thô gần nhất là thứ model cần đọc từng chữ. Nén không được ăn vào đó."""
    session = _long_session()
    keep = tiny_budget.context_compaction_keep_turns
    last_turns = session.conversation[-keep:]

    compaction.maybe_compact(session)

    assert compaction.history_view(session)[-keep:] == last_turns


def test_the_raw_transcript_is_kept_even_after_compaction(fake_summarizer, tiny_budget):
    """Nén là nén KHUNG NHÌN gửi cho model, không phải nén bản ghi: `raw_conversation` của phiếu bàn
    giao và phần điều dưỡng đọc lại vẫn phải đủ mọi lượt."""
    session = _long_session()
    turns_before = len(session.conversation)

    compaction.maybe_compact(session)

    assert len(session.conversation) == turns_before
    assert len(compaction.history_view(session)) < turns_before


def test_a_dead_provider_falls_back_to_a_deterministic_summary(tiny_budget, monkeypatch):
    """Model chết ⇒ rơi về bản tất định, KHÔNG rơi về chuỗi rỗng: mất bản tóm tắt là mất luôn phần
    hội thoại vừa bị cắt khỏi khung nhìn."""
    monkeypatch.setattr(provider_router, "complete", Mock(side_effect=RuntimeError("provider chết")))
    session = _long_session()

    assert compaction.maybe_compact(session) is True
    assert "Người bệnh đã kể" in session.conversation_summary


def test_the_summary_stays_in_the_prompt_window_however_many_turns_follow(fake_summarizer, tiny_budget):
    """Bản tóm tắt nén hàng chục lượt; để nó bị `[-limit:]` đẩy ra ngoài vì mấy lượt "vâng"/"không"
    mới nhất là đánh mất đúng thứ việc nén sinh ra để giữ."""
    session = _long_session()
    compaction.maybe_compact(session)
    for index in range(10):
        session.conversation.append({"role": "user", "content": f"vâng {index}"})

    rendered = intake_agent._format_history(compaction.history_view(session))

    assert _SUMMARY_TEXT in rendered
    assert "vâng 9" in rendered


def test_the_compaction_state_survives_a_restart(fake_summarizer, tiny_budget):
    """Không persist ranh giới "đã nén / còn thô" thì phiên khôi phục hoặc gửi lại đúng những lượt
    vừa nén, hoặc bỏ qua chúng mà không có bản tóm tắt thay thế."""
    session = _long_session()
    compaction.maybe_compact(session)

    restored = load_session(json.loads(json.dumps(dump_session(session), ensure_ascii=False)))

    assert restored.conversation_summary == session.conversation_summary
    assert restored.summarized_turns == session.summarized_turns
    assert compaction.history_view(restored) == compaction.history_view(session)


def test_a_corrupt_boundary_never_empties_the_prompt_window():
    """`summarized_turns` lớn hơn số lượt thật (bản ghi cũ/hỏng) sẽ cắt sạch hội thoại và gửi cho
    model một cửa sổ RỖNG. Nạp phải kẹp lại thay vì tin thẳng."""
    restored = load_session({
        "protocol_name": FEVER_PROTOCOL.name,
        "conversation": [{"role": "user", "content": "sốt 2 hôm"}],
        "summarized_turns": 99,
    })

    assert restored.summarized_turns == 1
    assert compaction.history_view(restored) == []


# --- M3 §5 mục 4: dữ kiện lịch sử KHÔNG thành dữ kiện hiện tại -----------------------------------


def _close_a_fever_conversation(user_id: int, *, complaint: str = "Sốt", age_days: int = 0) -> str:
    """Một phiên ĐÃ ĐÓNG của `user_id`, kèm phiếu bàn giao - đúng thứ M3 đọc lại."""
    persist = SqliteConversationStore()
    session = Session(protocol_name=FEVER_PROTOCOL.name, state=SessionState.CONFIRMED)
    session.answers = {"fever_reported": "true"}
    session.conversation.append({"role": "user", "content": "bé sốt 2 hôm nay"})
    persist.save(session, user_id=user_id)
    persist.save_nurse_summary(
        session.session_id,
        user_id=user_id,
        summary={
            "chief_complaint": complaint,
            "proposed_priority": "Cấp cứu",
            "narrative": "Người bệnh sốt hai ngày.",
        },
    )
    if age_days:
        _age_the_row(session.session_id, user_id, age_days)
    return session.session_id


def _age_the_row(conversation_id: str, user_id: int, days: int) -> None:
    from src.database import session_scope
    from src.models.case_record import ConversationRow

    with session_scope() as db:
        row = db.get(ConversationRow, (conversation_id, user_id))
        row.updated_at = datetime.now(timezone.utc) - timedelta(days=days)


@pytest.fixture
def long_memory_on(monkeypatch):
    monkeypatch.setattr(get_settings(), "long_memory_enabled", True)


def test_previous_fever_does_not_become_current_fever(long_memory_on):
    """⚠️ BÀI QUAN TRỌNG NHẤT của M3 (bất biến 9). Phiên trước ghi `fever_reported=true`; phiên mới
    được phép HỎI THĂM về nó, nhưng snapshot của phiên mới phải bắt đầu từ rỗng hoàn toàn."""
    _close_a_fever_conversation(PATIENT_A)
    store = ProtocolSessionStore(
        FEVER_PROTOCOL, persist=SqliteConversationStore(), recall=history_recall.greeting_for_user,
    )

    fresh = store.start_session(protocol_name=FEVER_PROTOCOL.name, user_id=PATIENT_A)

    assert fresh.answers == {}
    assert "sốt" in fresh.last_question.lower()  # có hỏi thăm


def test_the_greeting_asks_instead_of_asserting(long_memory_on):
    """Hỏi thăm là một CÂU HỎI. Nhắc lại mức ưu tiên hay văn xuôi phiếu là biến một đề xuất đang chờ
    điều dưỡng duyệt thành một kết luận đã tuyên (`CLAUDE.md` nguyên tắc 1)."""
    _close_a_fever_conversation(PATIENT_A)

    text = history_recall.greeting_for_user(PATIENT_A)

    assert text.endswith("?")
    assert "Cấp cứu" not in text
    assert "Người bệnh sốt hai ngày." not in text


def test_no_path_reads_another_users_history(long_memory_on):
    """§3 điều kiện 2 + `CLAUDE.md` nguyên tắc 5. Khoá composite làm việc này bằng hình dạng bảng,
    không bằng một câu `if` mà ai đó có thể quên."""
    _close_a_fever_conversation(PATIENT_A)

    assert history_recall.recall(PATIENT_A) != ()
    assert history_recall.recall(PATIENT_B) == ()
    assert history_recall.greeting_for_user(PATIENT_B) == ""


def test_a_guest_session_has_no_history(long_memory_on):
    """`user_id = 0` là "chưa biết là ai", không phải một người dùng. Gộp mọi phiên khách vào một hồ
    sơ là rò dữ liệu giữa hai người lạ."""
    _close_a_fever_conversation(0)

    assert history_recall.recall(0) == ()


def test_long_memory_is_off_until_someone_turns_it_on():
    """Mặc định TẮT vì §3 điều kiện 3: consent + retention là câu hỏi cho PM, và câu trả lời phải có
    bằng văn bản TRƯỚC KHI M3 lên production."""
    assert get_settings().long_memory_enabled is False

    _close_a_fever_conversation(PATIENT_A)

    assert history_recall.recall(PATIENT_A) == ()


def test_an_unfinished_conversation_is_not_asked_about(long_memory_on):
    """Phiên còn dở chưa có phiếu. Hỏi thăm về một phiên người bệnh bỏ ngang là nhắc lại đúng lần họ
    đã bỏ đi."""
    persist = SqliteConversationStore()
    persist.save(Session(protocol_name=FEVER_PROTOCOL.name), user_id=PATIENT_A)

    assert history_recall.recall(PATIENT_A) == ()


def test_conversations_older_than_the_retention_ceiling_are_dropped(long_memory_on):
    """Trần tuổi là chỗ giữ hộ câu trả lời retention của PM: chừng nào chưa có chính sách, một trần
    cụ thể vẫn tốt hơn "nhớ mãi mãi"."""
    _close_a_fever_conversation(PATIENT_A, age_days=history_recall._RECALL_MAX_AGE_DAYS + 1)

    assert history_recall.recall(PATIENT_A) == ()


def test_the_history_namespace_never_collides_with_a_protocol_field(long_memory_on):
    """Dữ kiện lịch sử sống ở namespace `history.*` riêng. Kể cả khi có ai đó `update()` nhầm nó vào
    `answers`, không khoá nào trúng một field của protocol."""
    _close_a_fever_conversation(PATIENT_A)

    namespace = history_recall.history_namespace(history_recall.recall(PATIENT_A))

    assert namespace
    assert all(key.startswith("history.") for key in namespace)
    assert not set(namespace) & set(FEVER_PROTOCOL.fields_by_key)


def test_the_handoff_summary_shape_matches_what_recall_reads(long_memory_on):
    """Hợp đồng giữa hai đầu: `nurse_summary_json` được ghi từ `HandoffSummary.model_dump()`, và
    `recall` đọc lại bằng tên khoá. Đổi tên một trường bên phiếu mà không ai báo thì bài này đỏ, chứ
    không phải câu hỏi thăm lặng lẽ rỗng trên production."""
    from src.services.sessions import symptom_case_bridge

    session = Session(protocol_name=FEVER_PROTOCOL.name, state=SessionState.CONFIRMED)
    session.answers = {"fever_reported": "true"}
    summary = symptom_case_bridge.to_triage_case(session, patient_id=PATIENT_A).summary

    persist = SqliteConversationStore()
    persist.save(session, user_id=PATIENT_A)
    persist.save_nurse_summary(
        session.session_id, user_id=PATIENT_A, summary=summary.model_dump(mode="json"),
    )

    recalled = history_recall.recall(PATIENT_A)
    assert recalled and recalled[0].chief_complaint == summary.chief_complaint


def test_recall_never_breaks_the_opening_turn(long_memory_on):
    """Hỏi thăm là phần THÊM VÀO của lượt mở, còn lượt mở thì không. Kho lịch sử hỏng phải làm mất
    câu hỏi thăm, không làm mất câu mở."""
    store = ProtocolSessionStore(FEVER_PROTOCOL, recall=Mock(side_effect=RuntimeError("DB chết")))

    session = store.start_session(protocol_name=FEVER_PROTOCOL.name, user_id=PATIENT_A)

    assert session.last_question
