"""Memory **M3**, phần "hỏi luôn khi mở hội thoại" — câu hỏi thăm được CHẮT LỌC SẴN và LƯU SẴN.

Ba tầng, ba bài chặn khác nhau:

- **Chắt lọc** (`_ranked_complaints` + `greeting`): ba phiếu vào, MỘT nhãn ra - và nhãn được chọn là
  nhãn lặp lại nhiều nhất, không phải nhãn mới nhất.
- **Lưu sẵn** (`followup_store`): lượt mở đọc một hàng theo khoá chính, không chạy lại phép chắt lọc.
- **Ranh giới cũ không được nới**: câu hỏi thăm vẫn không mang mức ưu tiên/văn xuôi phiếu ra ngoài,
  vẫn không có với khách, vẫn không đi vào `answers`, và vẫn không được phép làm hỏng lượt mở.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from src import paths
from src.config import get_settings
from src.database import configure_database, create_tables, dispose_database
from src.services.engines.fever_protocol import FEVER_PROTOCOL
from src.services.infra import provider_router
from src.services.sessions import followup_writer, history_recall
from src.services.stores.conversation_store import SqliteConversationStore
from src.services.stores.followup_store import followup_store
from src.services.symptom_protocol.session import ProtocolSessionStore, Session, SessionState

PATIENT_A, PATIENT_B = 31, 32


@pytest.fixture(autouse=True)
def _fresh_database(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LOGS_DIR", tmp_path)
    configure_database(f"sqlite+pysqlite:///{(tmp_path / 'test.db').as_posix()}")
    create_tables()
    try:
        yield
    finally:
        dispose_database()


@pytest.fixture(autouse=True)
def _static_question_by_default(monkeypatch):
    """Mặc định TẮT con LLM viết câu hỏi thăm. Các bài dưới đây kiểm phần TẤT ĐỊNH (chắt lọc, lưu
    sẵn, ranh giới truy cập); để nguyên cờ thì mỗi bài sẽ gọi provider thật rồi mới rơi về câu tĩnh -
    chậm, và xanh/đỏ phụ thuộc mạng. Các bài về chính con LLM tự bật lại bằng `llm_writer`."""
    monkeypatch.setattr(get_settings(), "followup_question_llm_enabled", False)


@pytest.fixture
def long_memory_on(monkeypatch):
    monkeypatch.setattr(get_settings(), "long_memory_enabled", True)


@pytest.fixture
def llm_writer(monkeypatch):
    """Bật con LLM viết câu hỏi thăm, và trả về hàm đặt câu model sẽ "viết"."""
    monkeypatch.setattr(get_settings(), "followup_question_llm_enabled", True)

    def say(text: str) -> Mock:
        mock = Mock(return_value=provider_router.CompletionResult(
            text=text, provider="fake", model="fake",
        ))
        monkeypatch.setattr(provider_router, "complete", mock)
        return mock

    return say


def _close(user_id: int, complaint: str) -> str:
    """Một phiên đã đóng kèm phiếu bàn giao - đúng thứ phép chắt lọc đọc lại."""
    persist = SqliteConversationStore()
    session = Session(protocol_name=FEVER_PROTOCOL.name, state=SessionState.CONFIRMED)
    session.answers = {"fever_reported": "true"}
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
    return session.session_id


# --- chắt lọc ---------------------------------------------------------------------------------


def test_the_repeated_complaint_wins_over_the_most_recent_one(long_memory_on):
    """Bài chính của phép chắt lọc. Ba phiếu: đau bụng (cũ), đau bụng, đau đầu (mới nhất). Thứ đáng
    hỏi là cái QUAY LẠI hai lần, không phải cái vừa xảy ra - lấy phiếu mới nhất thì không cần tới ba
    phiếu làm gì."""
    _close(PATIENT_A, "Đau bụng")
    _close(PATIENT_A, "Đau bụng")
    _close(PATIENT_A, "Đau đầu")

    question = history_recall.refresh_for_user(PATIENT_A)

    assert "đau bụng" in question.lower()
    assert "đau đầu" not in question.lower()
    assert question.endswith("?")


def test_only_one_complaint_is_ever_read_back(long_memory_on):
    """Ba phiếu vào, MỘT nhãn ra. Đọc cả danh sách là mở đầu bằng một bản tóm tắt hồ sơ chứ không
    phải một câu hỏi thăm."""
    for complaint in ("Đau bụng", "Đau đầu", "Khó thở"):
        _close(PATIENT_A, complaint)

    question = history_recall.refresh_for_user(PATIENT_A).lower()

    assert sum(label in question for label in ("đau bụng", "đau đầu", "khó thở")) == 1


def test_the_stored_question_never_carries_the_priority_or_the_narrative(long_memory_on):
    """Ranh giới cũ giữ nguyên sau khi câu hỏi được đem đi LƯU: mức ưu tiên là đề xuất đang chờ điều
    dưỡng duyệt (`CLAUDE.md` nguyên tắc 1), văn xuôi phiếu là hồ sơ đọc ra loa."""
    _close(PATIENT_A, "Sốt")

    question = history_recall.refresh_for_user(PATIENT_A)

    assert "Cấp cứu" not in question
    assert "Người bệnh sốt hai ngày." not in question


# --- lưu sẵn ----------------------------------------------------------------------------------


def test_the_opening_turn_reads_the_stored_question_without_recomputing(long_memory_on, monkeypatch):
    """Lý do tồn tại của bảng: lượt mở KHÔNG chạy lại phép chắt lọc. `recall` (truy vấn 3 hàng) phải
    không được gọi một lần nào ở đường đọc khi câu đã có sẵn."""
    _close(PATIENT_A, "Sốt")
    history_recall.refresh_for_user(PATIENT_A)
    monkeypatch.setattr(
        history_recall, "recall", lambda *a, **k: pytest.fail("lượt mở đã chắt lọc lại"),
    )

    assert "sốt" in history_recall.greeting_for_user(PATIENT_A).lower()


def test_a_question_is_asked_once_not_at_every_opening(long_memory_on):
    """Hỏi thăm là một câu HỎI, không phải một dòng chào. Lặp lại nó ở mọi lần mở dạy người bệnh bỏ
    qua nó - kể cả những lần nó đáng đọc."""
    _close(PATIENT_A, "Sốt")
    history_recall.refresh_for_user(PATIENT_A)

    assert history_recall.greeting_for_user(PATIENT_A) != ""
    assert history_recall.greeting_for_user(PATIENT_A) == ""


def test_closing_a_new_conversation_arms_the_next_opening(long_memory_on):
    """Vòng đời đầy đủ: hỏi xong -> im lặng -> phiên mới đóng -> lại có câu để hỏi. Nếu `save` không
    đặt lại `asked_at` thì người bệnh sẽ không bao giờ được hỏi thăm lần thứ hai."""
    _close(PATIENT_A, "Sốt")
    history_recall.refresh_for_user(PATIENT_A)
    history_recall.greeting_for_user(PATIENT_A)

    _close(PATIENT_A, "Đau bụng")
    history_recall.refresh_for_user(PATIENT_A)

    assert history_recall.greeting_for_user(PATIENT_A) != ""


def test_the_backfill_runs_once_for_a_user_with_no_stored_question(long_memory_on):
    """Người dùng đã có lịch sử từ TRƯỚC khi bảng tồn tại (và lần đầu bật cờ) vẫn phải được hỏi thăm
    - nhưng phép chắt lọc bù chỉ chạy đúng một lần, không phải mỗi lần mở."""
    _close(PATIENT_A, "Sốt")

    assert "sốt" in history_recall.greeting_for_user(PATIENT_A).lower()
    assert followup_store.exists(PATIENT_A)


def test_a_user_with_no_history_stores_an_empty_answer(long_memory_on):
    """"Đã chắt lọc, không có gì để hỏi" là một câu trả lời và nó phải được ghi lại: thiếu hàng rỗng
    thì mọi lần mở của người dùng chưa có lịch sử đều chạy lại một truy vấn không bao giờ có kết quả.
    """
    assert history_recall.greeting_for_user(PATIENT_A) == ""
    assert followup_store.exists(PATIENT_A)
    assert followup_store.pending(PATIENT_A) is None


# --- ranh giới --------------------------------------------------------------------------------


def test_no_path_reads_another_users_stored_question(long_memory_on):
    """Khoá chính là `user_id`: không có đường nào đọc trúng câu hỏi thăm của người khác."""
    _close(PATIENT_A, "Sốt")
    history_recall.refresh_for_user(PATIENT_A)

    assert history_recall.greeting_for_user(PATIENT_B) == ""


def test_a_guest_never_gets_a_stored_question(long_memory_on):
    """`user_id = 0` là "chưa biết là ai". Một hàng chung cho mọi khách là rò dữ liệu giữa người lạ."""
    _close(0, "Sốt")

    assert history_recall.refresh_for_user(0) == ""
    assert history_recall.greeting_for_user(0) == ""
    assert followup_store.pending(0) is None


def test_nothing_is_stored_while_the_flag_is_off():
    """Cờ tắt ⇒ không chắt lọc, không ghi. Cờ này là công tắc consent/retention (`F04` §3 điều kiện
    3), nên "chỉ ghi sẵn thôi chứ chưa hỏi" vẫn là ghi một dẫn xuất của PHI."""
    assert get_settings().long_memory_enabled is False
    _close(PATIENT_A, "Sốt")

    assert history_recall.refresh_for_user(PATIENT_A) == ""
    assert followup_store.exists(PATIENT_A) is False


def test_the_stored_question_never_becomes_a_current_fact(long_memory_on):
    """Bất biến 9 vẫn nguyên sau khi câu hỏi đi qua DB: phiên mới hỏi thăm được, nhưng snapshot của
    nó bắt đầu từ rỗng hoàn toàn."""
    _close(PATIENT_A, "Sốt")
    history_recall.refresh_for_user(PATIENT_A)
    store = ProtocolSessionStore(
        FEVER_PROTOCOL, persist=SqliteConversationStore(), recall=history_recall.greeting_for_user,
    )

    fresh = store.start_session(protocol_name=FEVER_PROTOCOL.name, user_id=PATIENT_A)

    assert fresh.answers == {}
    assert "sốt" in fresh.last_question.lower()


# --- con LLM viết câu hỏi thăm (`ROLE_FOLLOWUP_QUESTION`) --------------------------------------


def test_the_model_writes_the_question_when_it_clears_the_guard(long_memory_on, llm_writer):
    """Việc của model đúng bằng CÁCH NÓI. Nội dung (nhắc tới sốt) đã do `_ranked_complaints` chốt."""
    llm_writer("Mình vẫn nhớ lần trước bạn kể bị sốt, mấy hôm nay bạn thấy trong người thế nào rồi?")
    _close(PATIENT_A, "Sốt")

    question = history_recall.refresh_for_user(PATIENT_A)

    assert question.startswith("Mình vẫn nhớ")


def test_the_writer_runs_under_its_own_role_not_the_compaction_one(long_memory_on, llm_writer):
    """Hai con LLM, hai vai trò. Gộp lại thì không bao giờ đọc được số liệu riêng của cái nào, và
    ghim model rẻ cho phần nén là vô tình ghim luôn cho câu đi thẳng tới người bệnh."""
    complete = llm_writer("Lần trước bạn có kể bị sốt, giờ bạn thấy đỡ hơn chưa?")
    _close(PATIENT_A, "Sốt")

    history_recall.refresh_for_user(PATIENT_A)

    assert complete.call_args.kwargs["role"] == provider_router.ROLE_FOLLOWUP_QUESTION
    assert provider_router.ROLE_FOLLOWUP_QUESTION != provider_router.ROLE_CONTEXT_SUMMARY


def test_the_model_never_sees_the_priority_or_the_narrative(long_memory_on, llm_writer):
    """Siết ở ĐẦU VÀO: không đưa vào thì không có gì để rò ra. Đây là lớp chặn rẻ hơn và chắc hơn mọi
    câu dặn trong prompt."""
    complete = llm_writer("Lần trước bạn có kể bị sốt, giờ bạn thấy đỡ hơn chưa?")
    _close(PATIENT_A, "Sốt")

    history_recall.refresh_for_user(PATIENT_A)

    prompt = complete.call_args.args[0][0]["content"]
    assert "Cấp cứu" not in prompt
    assert "Người bệnh sốt hai ngày." not in prompt


@pytest.mark.parametrize(
    ("written", "vì_sao"),
    [
        ("Lần trước bạn kể sốt ba mươi chín độ, giờ còn 39 không?", "chữ số = chi tiết lâm sàng bịa"),
        ("Bạn kể bị sốt, giờ có cần đi cấp cứu không?", "mức ưu tiên là đề xuất chờ điều dưỡng duyệt"),
        ("Dạo này bạn thấy trong người thế nào rồi?", "mất nhãn = hỏi thăm về một chuyện khác"),
        ("Bạn còn sốt không? Bạn đã đỡ chưa?", "hai câu hỏi = hỏi dồn ngay ở câu đầu"),
        ("Bạn kể bị sốt, đã uống thuốc gì chưa?", "kê đơn/thuốc là nguyên tắc 2"),
    ],
)
def test_a_question_that_fails_the_guard_falls_back_to_the_static_one(
    long_memory_on, llm_writer, written, vì_sao,
):
    """Trượt guard ⇒ dùng câu tĩnh, KHÔNG sửa câu model viết: thứ còn lại sau khi cắt không phải câu
    model định nói, và không ai đọc lại nó trước khi nó tới người bệnh."""
    llm_writer(written)
    _close(PATIENT_A, "Sốt")

    question = history_recall.refresh_for_user(PATIENT_A)

    assert question == "Lần trước bạn có nhắc tới sốt. Tình trạng đó giờ đã đỡ hơn chưa?", vì_sao


def test_a_dead_provider_still_leaves_a_question_to_ask(long_memory_on, monkeypatch):
    """Model chết phải rơi về câu tĩnh, không rơi về chuỗi rỗng - mất câu hỏi thăm ở đây là mất luôn
    lượt hỏi thăm đó, vì `save` ghi thẳng kết quả này vào DB."""
    monkeypatch.setattr(get_settings(), "followup_question_llm_enabled", True)
    monkeypatch.setattr(provider_router, "complete", Mock(side_effect=RuntimeError("provider chết")))
    _close(PATIENT_A, "Sốt")

    assert history_recall.refresh_for_user(PATIENT_A).endswith("?")


def test_the_guard_reads_the_label_the_distiller_chose_not_the_one_the_model_liked(long_memory_on, llm_writer):
    """Model nhắc đúng nhãn đã chắt lọc, không phải nhãn nào khác trong lịch sử: hai lần mở hội thoại
    của cùng một lịch sử phải hỏi về cùng một chuyện."""
    llm_writer("Bạn kể bị đau đầu mấy lần rồi, giờ bạn thấy sao rồi?")
    _close(PATIENT_A, "Đau bụng")
    _close(PATIENT_A, "Đau bụng")
    _close(PATIENT_A, "Đau đầu")

    assert "đau bụng" in history_recall.refresh_for_user(PATIENT_A).lower()


def test_the_guard_is_code_not_a_prompt():
    """`_accept` chạy được không cần DB, không cần provider - đó là điều làm nó là một guard chứ
    không phải một câu dặn."""
    assert followup_writer._accept("Lần trước bạn kể bị sốt, giờ đỡ hơn chưa?", "sốt")
    assert not followup_writer._accept("Lần trước bạn kể bị sốt, giờ đỡ hơn chưa.", "sốt")
    assert not followup_writer._accept("x" * 300 + " sốt?", "sốt")
    assert not followup_writer._accept("", "sốt")
