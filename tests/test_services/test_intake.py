"""Test cho demo intake. Chỉ test phần deterministic (red-flag, checklist, state machine) -
không gọi LLM thật để test chạy nhanh và không phụ thuộc API key."""

from __future__ import annotations

import pytest

from src.services.agents.intake_agent import scan_red_flags, strip_diacritics
from src.services.checklists.intake_checklist import (
    REQUIRED_KEYS,
    completion_ratio,
    is_complete_enough,
    missing_required_keys,
)
from src.services.sessions import intake_session
from src.services.sessions.intake_session import SessionState


@pytest.fixture
def no_llm(monkeypatch):
    """Ép agent chạy nhánh fallback deterministic: giả lập không provider nào có API key."""
    from src.services.infra import provider_router

    def _no_provider(*args, **kwargs):
        raise provider_router.NoProviderConfiguredError("test: không có provider")

    monkeypatch.setattr(provider_router, "available_providers", lambda: [])
    monkeypatch.setattr(provider_router, "complete", _no_provider)


class TestRedFlagScan:
    def test_detects_with_diacritics(self):
        assert [hit.code for hit in scan_red_flags("cháu bị co giật")] == ["seizure"]

    def test_detects_without_diacritics(self):
        """Người Việt gõ không dấu rất phổ biến - bỏ sót ở đây là lỗi an toàn."""
        assert [hit.code for hit in scan_red_flags("chau bi co giat")] == ["seizure"]

    def test_detects_across_multiple_sources(self):
        """Quét được cả text thô lẫn giá trị field LLM đã chuẩn hoá."""
        hits = scan_red_flags("benh nhan met", "li bì")
        assert [hit.code for hit in hits] == ["altered_consciousness"]

    def test_no_false_positive_on_normal_text(self):
        assert scan_red_flags("cháu sốt nhẹ, vẫn chơi bình thường") == []

    def test_multiple_red_flags(self):
        codes = {hit.code for hit in scan_red_flags("bị ngất và co giật")}
        assert codes == {"loss_of_consciousness", "seizure"}

    def test_strip_diacritics_handles_d_stroke(self):
        assert strip_diacritics("Đau ngực dữ dội") == "dau nguc du doi"


class TestChecklistCompletion:
    def test_empty_is_zero(self):
        assert completion_ratio({}) == 0.0
        assert not is_complete_enough({})

    def test_blank_string_does_not_count_as_filled(self):
        assert completion_ratio({key: "   " for key in REQUIRED_KEYS}) == 0.0

    def test_all_required_filled_is_complete(self):
        answers = {key: "x" for key in REQUIRED_KEYS}
        assert completion_ratio(answers) == 1.0
        assert is_complete_enough(answers)
        assert missing_required_keys(answers) == []

    def test_threshold_needs_six_of_seven(self):
        """Ngưỡng 0.85 trên 7 trường bắt buộc => 6/7 đủ, 5/7 chưa đủ."""
        six = {key: "x" for key in REQUIRED_KEYS[:6]}
        five = {key: "x" for key in REQUIRED_KEYS[:5]}
        assert is_complete_enough(six)
        assert not is_complete_enough(five)

    def test_optional_field_does_not_affect_ratio(self):
        answers = {key: "x" for key in REQUIRED_KEYS}
        answers["medical_history"] = None
        assert completion_ratio(answers) == 1.0


class TestSessionFlow:
    def test_start_session_asks_opening_question(self):
        session = intake_session.start_session()
        assert session.state == SessionState.COLLECTING
        assert session.last_question == intake_session.OPENING_QUESTION
        assert session.conversation[0]["role"] == "assistant"

    def test_empty_message_rejected(self, no_llm):
        session = intake_session.start_session()
        with pytest.raises(intake_session.EmptyMessageError):
            intake_session.submit_message(session.session_id, "   ")

    def test_unknown_session_raises(self):
        with pytest.raises(intake_session.SessionNotFoundError):
            intake_session.submit_message("does-not-exist", "xin chào")

    def test_red_flag_detected_on_first_message_before_checklist_complete(self, no_llm):
        """Ràng buộc an toàn cốt lõi: red-flag không được đợi checklist đủ mới báo."""
        session = intake_session.start_session()
        session = intake_session.submit_message(session.session_id, "bố tôi vừa bị ngất")

        assert session.red_flags, "phải bắt được red-flag ngay lượt đầu"
        assert "loss_of_consciousness" in session.red_flag_codes()
        assert session.state == SessionState.COLLECTING  # vẫn hỏi tiếp, không dừng phiên
        assert not is_complete_enough(session.answers)

    def test_confirm_before_summary_is_rejected(self, no_llm):
        session = intake_session.start_session()
        with pytest.raises(ValueError, match="chưa có phiếu tóm tắt"):
            intake_session.confirm_summary(session.session_id, is_correct=True)

    def test_force_summary_after_max_turns(self, no_llm, monkeypatch):
        """Không hỏi vòng vô hạn khi người bệnh liên tục không cung cấp được thông tin.

        Mock extract trả rỗng để mô phỏng đúng kịch bản đó - fallback deterministic mặc định vẫn
        gán được giá trị nên sẽ đạt ngưỡng trước khi chạm MAX_TURNS.
        """
        monkeypatch.setattr(intake_session.intake_agent, "extract", lambda message, answers: ({}, False))

        session = intake_session.start_session()
        for _ in range(intake_session.MAX_TURNS_BEFORE_FORCE_SUMMARY):
            session = intake_session.submit_message(session.session_id, "tôi không biết")

        assert session.state == SessionState.AWAITING_CONFIRMATION
        assert not is_complete_enough(session.answers), "chuyển sang tóm tắt dù chưa đủ trường"

    def test_summary_rows_mark_missing_without_inventing_values(self, no_llm):
        session = intake_session.start_session()
        session = intake_session.submit_message(session.session_id, "đau đầu")
        rows = intake_session.build_summary_rows(session)

        missing = [row for row in rows if row["is_missing"]]
        assert missing, "phải có trường thiếu"
        assert all(row["value"] is None for row in missing), "trường thiếu phải để None, không bịa giá trị"

    def test_confirm_correct_finalizes_session(self, no_llm):
        session = intake_session.start_session()
        session.answers = {key: "x" for key in REQUIRED_KEYS}
        session.state = SessionState.AWAITING_CONFIRMATION

        session = intake_session.confirm_summary(session.session_id, is_correct=True)
        assert session.state == SessionState.CONFIRMED

    def test_reject_without_correction_asks_what_to_fix(self, no_llm):
        session = intake_session.start_session()
        session.answers = {key: "x" for key in REQUIRED_KEYS}
        session.state = SessionState.AWAITING_CONFIRMATION

        session = intake_session.confirm_summary(session.session_id, is_correct=False, correction=None)
        assert session.state == SessionState.COLLECTING
        assert "chưa đúng" in session.last_question.lower()

    def test_correction_scans_red_flags_too(self, no_llm):
        """Đính chính cũng phải được quét red-flag, không chỉ lượt hỏi-đáp thường."""
        session = intake_session.start_session()
        session.answers = {key: "x" for key in REQUIRED_KEYS}
        session.state = SessionState.AWAITING_CONFIRMATION

        session = intake_session.confirm_summary(
            session.session_id, is_correct=False, correction="quên mất, cháu có co giật nữa"
        )
        assert "seizure" in session.red_flag_codes()


class TestProgressReporting:
    def test_progress_reports_missing_labels(self, no_llm):
        session = intake_session.start_session()
        progress = intake_session.progress_of(session)

        assert progress["percent"] == 0
        assert progress["filled_required"] == 0
        assert progress["total_required"] == len(REQUIRED_KEYS)
        assert "Họ và tên" in progress["missing_required_labels"]
