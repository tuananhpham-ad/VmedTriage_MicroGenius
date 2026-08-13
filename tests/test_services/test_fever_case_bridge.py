"""`fever_case_bridge` - dịch `Session` của agent fever sang `TriageCase` của luồng case/HITL.

Hàm dịch là THUẦN nên test không cần LLM, không cần client HTTP: dựng `Session` bằng tay, kiểm đúng
những field mà màn hình điều dưỡng/bệnh nhân thực sự đọc. Trọng tâm là hai thứ dễ hỏng nhất khi
đổi luồng: (1) case có vào hàng đợi điều dưỡng không, (2) có lộ kết luận nội bộ cho bệnh nhân sớm
hơn mức được phép không.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.models.schemas import CaseStatus, TriagePriority
from src.services.sessions import fever_case_bridge
from src.services.symptom_protocol.session import Session, SessionState


def _session(**overrides) -> Session:
    session = Session()
    session.conversation = [
        {"role": "assistant", "content": "Người cần tư vấn bao nhiêu tuổi ạ?"},
        {"role": "user", "content": "Bé 3 tuổi, sốt 39 độ."},
    ]
    session.answers = {"age_value": "3", "age_unit": "year", "temp_c": "39.0", "cyanosis": "unknown"}
    session.last_question = "Bé có bị co giật không ạ?"
    for key, value in overrides.items():
        setattr(session, key, value)
    return session


# --- đang thu thập: chưa có kết luận, chưa vào hàng đợi ------------------------------------------


def test_collecting_session_has_no_proposal_and_no_queue_item():
    case = fever_case_bridge.to_triage_case(_session(), patient_id=7)

    assert case.status is CaseStatus.COLLECTING_INFORMATION
    assert case.triage_proposal is None  # chưa chốt thì KHÔNG được đoán trước mức ưu tiên
    assert case.queue_item is None
    assert case.summary_ready is False


def test_summary_fields_exist_while_collecting_so_the_patient_sees_labels_not_raw_keys():
    case = fever_case_bridge.to_triage_case(_session(), patient_id=7)
    by_label = {row.label: row for row in case.summary_fields}

    assert by_label["Nhiệt độ đo được (°C)"].value == "39.0"
    assert by_label["Nhiệt độ đo được (°C)"].is_missing is False
    assert by_label["Mức tỉnh táo"].is_missing is True
    # Chỉ M0/M1 lên phiếu - tier C/O/H là thông tin bổ trợ, đưa hết lên chỉ làm nhiễu.
    assert "Sợ ánh sáng" not in by_label


def test_collecting_session_shows_next_question_to_patient():
    case = fever_case_bridge.to_triage_case(_session(), patient_id=7)
    # Trong lúc hỏi, "phản hồi cho bệnh nhân" chính là câu hỏi kế tiếp của agent.
    assert case.patient_visible_response == "Bé có bị co giật không ạ?"
    assert case.next_message == "Bé có bị co giật không ạ?"


def test_case_id_is_the_agent_session_id():
    session = _session()
    case = fever_case_bridge.to_triage_case(session, patient_id=7)
    # Một phiên hội thoại = một case, không có bảng ánh xạ phụ nào để lệch.
    assert case.case_id == session.session_id


def test_unknown_values_are_not_reported_as_collected():
    case = fever_case_bridge.to_triage_case(_session(), patient_id=7)
    assert "cyanosis" not in case.structured_data.fields
    assert case.structured_data.fields["temp_c"] == "39.0"
    assert case.structured_data.symptom_group == "fever"


# --- chốt đỏ: vào hàng đợi ưu tiên cao, hiện thông điệp cấp cứu ----------------------------------


def test_emergency_session_becomes_escalated_case_with_high_priority_queue_item():
    session = _session(
        state=SessionState.EMERGENCY,
        triage_level="EMERGENCY",
        reason_codes=["RF-02"],
        triggered_rules=["R-E-02"],
        stop_reason="RED_FLAG",
        last_question="",
    )
    case = fever_case_bridge.to_triage_case(session, patient_id=7)

    assert case.status is CaseStatus.ESCALATED
    assert case.queue_item is not None
    assert case.queue_item.queue_priority.value == "high"
    assert case.triage_proposal.priority is TriagePriority.EMERGENCY
    assert case.triage_proposal.requires_manual_review is True
    assert "115" in case.patient_visible_response


def test_reason_codes_get_vietnamese_labels_for_the_nurse():
    session = _session(state=SessionState.EMERGENCY, triage_level="EMERGENCY", reason_codes=["RF-02", "RF-13"])
    case = fever_case_bridge.to_triage_case(session, patient_id=7)

    labels = {finding.code: finding.label for finding in case.red_flags}
    assert labels["RF-02"] == "Đang co giật / vừa co giật"
    assert labels["RF-13"] == "Dấu hiệu sốc"


def test_unknown_reason_code_falls_back_to_the_code_itself():
    session = _session(state=SessionState.EMERGENCY, triage_level="EMERGENCY", reason_codes=["RF-99"])
    case = fever_case_bridge.to_triage_case(session, patient_id=7)
    assert case.red_flags[0].label == "RF-99"


# --- kết thúc bình thường: chờ điều dưỡng duyệt, KHÔNG hiện gì cho bệnh nhân ---------------------


def test_finished_session_waits_for_nurse_and_hides_guidance_from_patient():
    session = _session(
        state=SessionState.AWAITING_CONFIRMATION,
        triage_level="SELF_CARE",
        stop_reason="SUFFICIENT_EVIDENCE",
        last_question="",
    )
    case = fever_case_bridge.to_triage_case(session, patient_id=7)

    assert case.status is CaseStatus.NEEDS_NURSE_REVIEW
    assert case.patient_visible_response is None  # hướng dẫn chỉ hiện SAU khi điều dưỡng duyệt
    assert case.queue_item is not None
    assert case.summary_ready is True
    assert any(row.label and row.is_missing for row in case.summary_fields)


def test_confirmed_session_is_still_pending_nurse_review():
    # Bệnh nhân xác nhận phiếu KHÔNG phải một bước duyệt - case vẫn phải qua điều dưỡng.
    session = _session(state=SessionState.CONFIRMED, triage_level="SELF_CARE", last_question="")
    assert fever_case_bridge.to_triage_case(session, patient_id=7).status is CaseStatus.NEEDS_NURSE_REVIEW


def test_early_visit_maps_to_urgent_priority():
    session = _session(state=SessionState.AWAITING_CONFIRMATION, triage_level="EARLY_VISIT", last_question="")
    case = fever_case_bridge.to_triage_case(session, patient_id=7)
    assert case.triage_proposal.priority is TriagePriority.URGENT


# --- giữ lại phần do điều dưỡng ghi khi dựng lại case mỗi lượt -----------------------------------


def test_nurse_written_fields_survive_a_rebuild():
    reviewed_at = datetime(2026, 8, 13, tzinfo=timezone.utc)
    first = fever_case_bridge.to_triage_case(_session(), patient_id=7)
    first.nurse_feedback = "Đã gọi lại cho người nhà."
    first.reviewed_by_id = 42
    first.reviewed_by_name = "ĐD Lan"
    first.reviewed_at = reviewed_at

    rebuilt = fever_case_bridge.to_triage_case(_session(), patient_id=7, previous=first)

    assert rebuilt.nurse_feedback == "Đã gọi lại cho người nhà."
    assert rebuilt.reviewed_by_id == 42
    assert rebuilt.reviewed_by_name == "ĐD Lan"
    assert rebuilt.reviewed_at == reviewed_at
    assert rebuilt.created_at == first.created_at  # mốc tạo case không được nhảy mỗi lượt


def test_empty_conversation_entries_are_dropped():
    # `ConversationMessage.content` có min_length=1 - một câu hỏi rỗng sẽ làm hỏng cả case.
    session = _session()
    session.conversation.append({"role": "assistant", "content": ""})
    case = fever_case_bridge.to_triage_case(session, patient_id=7)

    assert len(case.conversation) == 2
    assert [message.role.value for message in case.conversation] == ["system", "patient"]
