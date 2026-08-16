"""Duyệt HITL sau khi gộp hai luồng về một (`sessions/hitl_review.py`).

Khoản nợ được trả ở đây: trước kia `/cases/{id}/review` (SPA gọi) chỉ sửa `TriageCase.status`, còn
`/cases/{id}/approve` (đúng đặc tả) chỉ ghi `approval_store`. Một case duyệt bằng đường này thì đường
kia không thấy. Mọi test dưới đây canh đúng một điều: MỘT hành động ghi ĐỦ CẢ HAI.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.database import configure_database, create_tables, dispose_database
from src.models.schemas import (
    CaseStatus,
    HITLAction,
    NurseReviewRequest,
    RejectReasonCode,
    TriageCase,
    TriagePriority,
    TriageProposal,
)
from src.services.sessions.hitl_review import human_review_service
from src.services.stores.approval_store import approval_store
from src.services.stores.case_store import case_store

NURSE_ID = 42


@pytest.fixture(autouse=True)
def _fresh_database(tmp_path):
    """Store giờ nằm ở SQLite nên "dọn store" = dựng một DB mới cho mỗi test.

    Dùng file trong `tmp_path` chứ không `:memory:`: SQLite in-memory gắn với từng connection, mà
    mỗi `session_scope()` mở một connection mới - dữ liệu ghi ở scope này sẽ không thấy được ở scope
    sau."""
    configure_database(f"sqlite+pysqlite:///{(tmp_path / 'test.db').as_posix()}")
    create_tables()
    try:
        yield
    finally:
        dispose_database()


def _case(case_id: str = "case-1", priority: TriagePriority = TriagePriority.URGENT) -> TriageCase:
    triage_case = TriageCase(
        case_id=case_id,
        patient_id=1,
        status=CaseStatus.NEEDS_NURSE_REVIEW,
        created_at=datetime.now(timezone.utc),
        triage_proposal=TriageProposal(priority=priority, reason="test"),
    )
    case_store.save(triage_case)
    return triage_case


def _review(action: HITLAction, **kwargs) -> None:
    human_review_service.review(
        "case-1", NurseReviewRequest(action=action, **kwargs), nurse_id=NURSE_ID, nurse_name="DD A",
    )


# --- một hành động, hai nơi ghi ------------------------------------------------------------------


def test_approve_updates_case_status_and_approval_record_together():
    _case()

    _review(HITLAction.APPROVE, approved_response="Bạn theo dõi tại nhà nhé.")

    assert case_store.get("case-1").status is CaseStatus.APPROVED
    record = approval_store.get("case-1")
    assert record is not None and record.approved_by == NURSE_ID
    assert record.final_priority == TriagePriority.URGENT.value


def test_every_action_leaves_an_audit_entry():
    actions = (
        (HITLAction.APPROVE, {"approved_response": "ok"}),
        (HITLAction.ASK_MORE, {"ask_more_question": "Bạn sốt mấy ngày rồi?"}),
        (HITLAction.REJECT, {"reject_reason_code": RejectReasonCode.AI_INCORRECT}),
    )
    _case()

    for action, kwargs in actions:
        _review(action, **kwargs)

    # Audit CHỈ THÊM: ba hành động trên cùng một case phải để lại đúng ba dòng, theo đúng thứ tự.
    entries = approval_store.audit_for_case("case-1")
    assert [entry.action for entry in entries] == [action.value for action, _ in actions]
    assert {entry.actor for entry in entries} == {str(NURSE_ID)}


def test_edit_records_the_priority_the_nurse_chose_not_the_one_ai_proposed():
    _case(priority=TriagePriority.ROUTINE)

    _review(
        HITLAction.EDIT,
        approved_response="Bạn nên đi khám sớm.",
        edited_priority=TriagePriority.EMERGENCY,
    )

    record = approval_store.get("case-1")
    assert record.final_priority == TriagePriority.EMERGENCY.value
    entry = approval_store.audit_for_case("case-1")[0]
    assert entry.old_value == TriagePriority.ROUTINE.value
    assert entry.new_value == TriagePriority.EMERGENCY.value


def test_second_edit_compares_against_the_first_nurse_decision():
    """`old_value` của lần sửa thứ hai phải là mức điều dưỡng đặt lần đầu, không phải mức AI ban đầu -
    nếu không, log audit sẽ kể sai câu chuyện ai đã đổi từ đâu sang đâu."""
    _case(priority=TriagePriority.ROUTINE)
    _review(HITLAction.EDIT, approved_response="x", edited_priority=TriagePriority.URGENT)

    _review(HITLAction.EDIT, approved_response="y", edited_priority=TriagePriority.EMERGENCY)

    latest = approval_store.audit_for_case("case-1")[-1]
    assert latest.old_value == TriagePriority.URGENT.value
    assert latest.new_value == TriagePriority.EMERGENCY.value


# --- hành động KHÔNG chốt mức ---------------------------------------------------------------------


def test_ask_more_does_not_create_an_approval_record():
    """Hỏi thêm là đưa case về trạng thái đang thu thập, không phải "đã duyệt kết quả". Sinh
    `ApprovalStatusRecord` ở đây sẽ mở cổng `/cases/{id}/result` cho bệnh nhân xem kết quả chưa duyệt."""
    _case()

    _review(HITLAction.ASK_MORE, ask_more_question="Bạn sốt mấy ngày rồi?")

    assert case_store.get("case-1").status is CaseStatus.COLLECTING_INFORMATION
    assert approval_store.get("case-1") is None


def test_reject_does_not_create_an_approval_record():
    _case()

    _review(HITLAction.REJECT, reject_reason_code=RejectReasonCode.ALREADY_HANDLED_OFFLINE)

    assert case_store.get("case-1").status is CaseStatus.REJECTED
    assert approval_store.get("case-1") is None


# --- reason code cho thống kê ---------------------------------------------------------------------


def test_reject_reason_code_is_stored_as_a_code_not_free_text():
    """Chỉ `ai_incorrect` được tính vào thống kê độ chính xác AI-vs-điều dưỡng. Ghi ghi chú tự do
    thay vì mã nghĩa là phép đo đó không còn nguồn dữ liệu."""
    _case()

    _review(
        HITLAction.REJECT,
        reject_reason_code=RejectReasonCode.AI_INCORRECT,
        nurse_notes="ghi chú tự do, KHÔNG được dùng làm lý do",
    )

    assert approval_store.audit_for_case("case-1")[0].reason == RejectReasonCode.AI_INCORRECT.value


def test_reject_without_a_reason_code_still_works():
    """Trường mới nên không bắt buộc - client cũ chưa gửi mã vẫn phải từ chối được case."""
    _case()

    _review(HITLAction.REJECT)

    assert case_store.get("case-1").status is CaseStatus.REJECTED
    assert approval_store.audit_for_case("case-1")[0].action == HITLAction.REJECT.value
