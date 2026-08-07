"""Test cho agent hỏi-đáp theo checklist từng bệnh (disease_x mock, mục 10 solution design).

Chỉ test phần deterministic (checklist ratio, state machine, fallback) - không gọi LLM thật để test
chạy nhanh và không phụ thuộc API key, giống test_intake.py."""

from __future__ import annotations

import pytest

from src.services import disease_session
from src.services.disease_checklist import (
    ChecklistNotFoundError,
    completion_ratio,
    is_complete_enough,
    load_checklist,
    missing_required_keys,
)
from src.services.disease_session import SessionState

DISEASE_ID = "disease_x"


@pytest.fixture
def no_llm(monkeypatch):
    """Ép agent chạy nhánh fallback deterministic: giả lập không provider nào có API key."""
    from src.services import provider_router

    def _no_provider(*args, **kwargs):
        raise provider_router.NoProviderConfiguredError("test: không có provider")

    monkeypatch.setattr(provider_router, "available_providers", lambda: [])
    monkeypatch.setattr(provider_router, "complete", _no_provider)


class TestChecklistLoading:
    def test_loads_disease_x_with_three_null_fields(self):
        checklist = load_checklist(DISEASE_ID)
        assert checklist.disease_id == "disease_x"
        assert [item.key for item in checklist.fields] == ["name", "condition", "onset"]
        assert checklist.required_keys == ("name", "condition", "onset")
        assert checklist.completion_threshold == 0.85

    def test_unknown_disease_raises(self):
        with pytest.raises(ChecklistNotFoundError):
            load_checklist("does-not-exist")


class TestChecklistCompletion:
    def test_empty_is_zero(self):
        checklist = load_checklist(DISEASE_ID)
        assert completion_ratio(checklist, {}) == 0.0
        assert not is_complete_enough(checklist, {})

    def test_two_of_three_not_enough(self):
        """0.85 trên 3 trường bắt buộc => 2/3 (0.667) chưa đủ, phải đủ cả 3."""
        checklist = load_checklist(DISEASE_ID)
        answers = {"name": "Nguyễn Văn A", "condition": "sốt cao"}
        assert not is_complete_enough(checklist, answers)
        assert missing_required_keys(checklist, answers) == ["onset"]

    def test_all_three_filled_is_complete(self):
        checklist = load_checklist(DISEASE_ID)
        answers = {"name": "Nguyễn Văn A", "condition": "sốt cao", "onset": "sáng nay"}
        assert completion_ratio(checklist, answers) == 1.0
        assert is_complete_enough(checklist, answers)

    def test_blank_string_does_not_count_as_filled(self):
        checklist = load_checklist(DISEASE_ID)
        answers = {"name": "  ", "condition": "sốt cao", "onset": "sáng nay"}
        assert not is_complete_enough(checklist, answers)


class TestSessionFlow:
    def test_start_session_asks_opening_question(self):
        session = disease_session.start_session(DISEASE_ID)
        assert session.state == SessionState.COLLECTING
        assert session.last_question
        assert session.conversation[0]["role"] == "assistant"

    def test_empty_message_rejected(self, no_llm):
        session = disease_session.start_session(DISEASE_ID)
        with pytest.raises(disease_session.EmptyMessageError):
            disease_session.submit_message(session.session_id, "   ")

    def test_unknown_session_raises(self):
        with pytest.raises(disease_session.SessionNotFoundError):
            disease_session.submit_message("does-not-exist", "xin chào")

    def test_fallback_fills_one_field_per_turn_until_complete(self, no_llm):
        """Không có LLM: mỗi lượt fallback gán nguyên tin nhắn cho trường thiếu đầu tiên."""
        session = disease_session.start_session(DISEASE_ID)

        session = disease_session.submit_message(session.session_id, "Nguyễn Văn A")
        assert session.answers.get("name") == "Nguyễn Văn A"
        assert session.state == SessionState.COLLECTING
        assert not session.llm_used_last_turn

        session = disease_session.submit_message(session.session_id, "sốt cao, mệt mỏi")
        assert session.answers.get("condition") == "sốt cao, mệt mỏi"
        assert session.state == SessionState.COLLECTING

        session = disease_session.submit_message(session.session_id, "sáng nay")
        assert session.answers.get("onset") == "sáng nay"
        assert session.state == SessionState.AWAITING_CONFIRMATION
        assert session.last_question == ""

    def test_confirm_before_summary_is_rejected(self, no_llm):
        session = disease_session.start_session(DISEASE_ID)
        with pytest.raises(ValueError, match="chưa có phiếu tóm tắt"):
            disease_session.confirm_summary(session.session_id, is_correct=True)

    def test_force_summary_after_max_turns(self, no_llm, monkeypatch):
        """Không hỏi vòng vô hạn khi người dùng liên tục không cung cấp được thông tin."""
        monkeypatch.setattr(disease_session._agent_for(load_checklist(DISEASE_ID)), "extract", lambda message, answers: ({}, False))

        session = disease_session.start_session(DISEASE_ID)
        for _ in range(disease_session.MAX_TURNS_BEFORE_FORCE_SUMMARY):
            session = disease_session.submit_message(session.session_id, "tôi không biết")

        assert session.state == SessionState.AWAITING_CONFIRMATION
        assert not is_complete_enough(session.checklist, session.answers)

    def test_summary_rows_mark_missing_without_inventing_values(self, no_llm):
        session = disease_session.start_session(DISEASE_ID)
        session = disease_session.submit_message(session.session_id, "Nguyễn Văn A")
        rows = disease_session.build_summary_rows(session)

        missing = [row for row in rows if row["is_missing"]]
        assert missing, "phải có trường thiếu"
        assert all(row["value"] is None for row in missing), "trường thiếu phải để None, không bịa giá trị"

    def test_summary_text_lists_all_fields(self, no_llm):
        session = disease_session.start_session(DISEASE_ID)
        session.answers = {"name": "Nguyễn Văn A", "condition": "sốt cao", "onset": "sáng nay"}
        text = disease_session.build_summary_text(session)

        assert "Disease X (mock test)" in text
        assert "Nguyễn Văn A" in text
        assert "sốt cao" in text
        assert "sáng nay" in text

    def test_confirm_correct_finalizes_session(self, no_llm):
        session = disease_session.start_session(DISEASE_ID)
        session.answers = {"name": "A", "condition": "B", "onset": "C"}
        session.state = SessionState.AWAITING_CONFIRMATION

        session = disease_session.confirm_summary(session.session_id, is_correct=True)
        assert session.state == SessionState.CONFIRMED

    def test_reject_without_correction_asks_what_to_fix(self, no_llm):
        session = disease_session.start_session(DISEASE_ID)
        session.answers = {"name": "A", "condition": "B", "onset": "C"}
        session.state = SessionState.AWAITING_CONFIRMATION

        session = disease_session.confirm_summary(session.session_id, is_correct=False, correction=None)
        assert session.state == SessionState.COLLECTING
        assert "chưa đúng" in session.last_question.lower()


class TestProgressReporting:
    def test_progress_reports_missing_labels(self, no_llm):
        session = disease_session.start_session(DISEASE_ID)
        progress = disease_session.progress_of(session)

        assert progress["percent"] == 0
        assert progress["filled_required"] == 0
        assert progress["total_required"] == 3
        assert "Tên" in progress["missing_required_labels"]
