"""Đồng hồ SLA cho ca nghi ngờ red-flag (ADR-008 / §4.12 §7.7).

`SLA_BREACH_MESSAGE` vô nghĩa nếu không có trần thời gian, và cam kết "điều dưỡng trực 24/7" không
kiểm chứng được nếu không ai đo. Đây là bộ test của cái trần đó.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.services.sessions import red_flag_sla
from src.services.sessions.red_flag_sla import SlaState
from src.services.symptom_protocol.common_safety import emergency_message

NOW = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)


def _at(seconds: int):
    return red_flag_sla.evaluate(queued_at=NOW, now=NOW + timedelta(seconds=seconds))


def test_a_fresh_case_is_within_sla():
    assert _at(10).state is SlaState.OK


def test_the_shift_is_warned_before_the_ceiling_is_hit():
    """Cảnh báo nội bộ ở 60% SLA - để `SLA_BREACH_MESSAGE` là ngoại lệ chứ không phải chuyện thường
    ngày."""
    status = _at(red_flag_sla.SLA_WARNING_SECONDS + 1)

    assert status.state is SlaState.WARNING
    assert status.notify_shift is True
    assert status.notify_patient is False, "cảnh báo NỘI BỘ - bệnh nhân chưa đọc gì cả"


def test_past_the_ceiling_the_patient_is_told_to_call_115():
    """Lưới đỡ khi đường chính (HITL) kẹt. Không có nó thì "chờ điều dưỡng" có thể âm thầm trở thành
    "chờ vô hạn" khi ca trực quá tải."""
    status = _at(red_flag_sla.SLA_CLINICAL_SECONDS + 1)

    assert status.state is SlaState.BREACHED
    assert status.notify_patient is True
    assert "115" in emergency_message.SLA_BREACH_MESSAGE


def test_the_clock_stops_when_a_nurse_opens_the_case():
    """Mở ca là lúc có người THẬT nhìn thấy nó - đó mới là thứ SLA an toàn quan tâm. Ca mở rồi mà
    chưa duyệt là vấn đề thông lượng, và trộn hai thứ vào một chỉ số làm `sla_breach_rate` mất khả
    năng phát hiện cái thứ hai."""
    status = red_flag_sla.evaluate(
        queued_at=NOW,
        first_opened_at=NOW + timedelta(seconds=30),
        now=NOW + timedelta(hours=2),
    )

    assert status.state is SlaState.NOT_APPLICABLE


def test_a_case_that_is_not_a_red_flag_has_no_clock():
    assert red_flag_sla.evaluate(queued_at=NOW, is_red_flag=False, now=NOW).state is SlaState.NOT_APPLICABLE


def test_a_case_that_never_entered_the_queue_has_no_clock():
    assert red_flag_sla.evaluate(queued_at=None, now=NOW).state is SlaState.NOT_APPLICABLE


def test_a_naive_timestamp_does_not_crash_the_clock():
    """`created_at` sinh ra đã aware, nhưng dữ liệu đọc lại từ SQLite có thể mất tzinfo - và trừ hai
    datetime lệch awareness thì ném `TypeError` giữa đường chạy chứ không phải lúc test."""
    naive = NOW.replace(tzinfo=None)

    status = red_flag_sla.evaluate(queued_at=naive, now=NOW + timedelta(seconds=10))

    assert status.state is SlaState.OK


def test_the_warning_threshold_sits_below_the_ceiling():
    """Hai số, không phải một. Cảnh báo bằng trần thì nó không còn là cảnh báo."""
    assert 0 < red_flag_sla.SLA_WARNING_SECONDS < red_flag_sla.SLA_CLINICAL_SECONDS


# --- ADR-008: ba câu, ba người nói ---------------------------------------------------------------


def test_the_in_session_message_suspects_instead_of_concluding():
    """Hệ thống nêu NGHI NGỜ, không khẳng định cấp cứu - công cụ sàng lọc nêu nghi ngờ, lâm sàng
    viên kết luận."""
    from src.services.engines.fever_protocol import FEVER_PROTOCOL

    message = FEVER_PROTOCOL.patient_red_flag_message

    assert message == emergency_message.SUSPECTED_RED_FLAG_MESSAGE
    assert "cần nhân viên y tế xem" in message
    assert "cần được cấp cứu ngay" not in message, "đó là câu của ĐIỀU DƯỠNG, sau khi duyệt"


def test_the_universal_safety_net_is_present_from_t_zero():
    """Đoạn "nếu thấy xấu đi hãy gọi 115" đúng với MỌI người bệnh trong mọi tình huống, nên nói ra
    không phải là chẩn đoán. Đây là chỗ ADR-008 khác với phương án im lặng hoàn toàn."""
    assert "115" in emergency_message.SUSPECTED_RED_FLAG_MESSAGE


def test_the_assertive_message_still_exists_for_the_nurse_to_send():
    """Câu cũ không sai - nó chỉ đang được nói bởi sai người ở sai thời điểm. Giữ nguyên văn, dùng
    làm mặc định cho `approved_response`."""
    assert "cần được cấp cứu ngay" in emergency_message.EMERGENCY_MESSAGE


def test_the_three_messages_are_distinct():
    messages = {
        emergency_message.SUSPECTED_RED_FLAG_MESSAGE,
        emergency_message.SLA_BREACH_MESSAGE,
        emergency_message.EMERGENCY_MESSAGE,
    }

    assert len(messages) == 3
