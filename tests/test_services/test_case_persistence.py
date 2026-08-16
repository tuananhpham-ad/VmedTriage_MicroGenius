"""Case và audit sống qua restart (`stores/case_store.py`, `stores/approval_store.py`).

Bất biến duy nhất đáng canh ở đây: dispose engine rồi mở lại - đúng thứ xảy ra khi Render redeploy -
thì dữ liệu vẫn còn. Bản in-memory cũ trượt mọi test dưới đây, và đó là lý do chúng tồn tại.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.database import configure_database, create_tables, dispose_database
from src.models.schemas import CaseStatus, TriageCase, TriagePriority, TriageProposal
from src.services.stores.approval_store import ApprovalStatusRecord, AuditLogEntry, approval_store
from src.services.stores.case_store import case_store


@pytest.fixture
def database_path(tmp_path):
    path = (tmp_path / "restart.db").as_posix()
    configure_database(f"sqlite+pysqlite:///{path}")
    create_tables()
    try:
        yield path
    finally:
        dispose_database()


def _restart(database_path: str) -> None:
    """Mô phỏng redeploy: bỏ engine hiện tại rồi nối lại vào ĐÚNG file đó."""
    dispose_database()
    configure_database(f"sqlite+pysqlite:///{database_path}")
    create_tables()


def _case(case_id: str, priority: TriagePriority = TriagePriority.EMERGENCY) -> TriageCase:
    return TriageCase(
        case_id=case_id,
        patient_id=7,
        status=CaseStatus.NEEDS_NURSE_REVIEW,
        created_at=datetime.now(timezone.utc),
        triage_proposal=TriageProposal(priority=priority, reason="test"),
    )


def test_case_survives_a_restart(database_path):
    case_store.save(_case("case-restart"))

    _restart(database_path)

    restored = case_store.get("case-restart")
    assert restored is not None
    assert restored.status is CaseStatus.NEEDS_NURSE_REVIEW
    assert restored.triage_proposal.priority is TriagePriority.EMERGENCY


def test_nested_payload_round_trips_unchanged(database_path):
    """Cột JSON phải trả lại NGUYÊN model, không phải một dict gần giống. Phần lồng
    (`triage_proposal`, `summary`, `red_flags`...) là chỗ dễ mất nhất khi qua serialize."""
    original = _case("case-nested")
    case_store.save(original)

    _restart(database_path)

    assert case_store.get("case-nested").model_dump(mode="json") == original.model_dump(mode="json")


def test_audit_log_survives_a_restart(database_path):
    case_store.save(_case("case-audit"))
    approval_store.log(
        AuditLogEntry(case_id="case-audit", actor="42", action="approve", old_value="Urgent", new_value="Emergency")
    )

    _restart(database_path)

    entries = approval_store.audit_for_case("case-audit")
    assert len(entries) == 1
    assert (entries[0].old_value, entries[0].new_value) == ("Urgent", "Emergency")


def test_approval_record_survives_a_restart(database_path):
    """Đây là cổng chặn của `GET /cases/{id}/result`. Mất nó sau restart nghĩa là một ca ĐÃ được
    điều dưỡng duyệt lại quay về trạng thái chưa duyệt với bệnh nhân."""
    case_store.save(_case("case-approved"))
    approval_store.upsert(
        ApprovalStatusRecord(
            case_id="case-approved",
            approved_by=42,
            approved_at=datetime.now(timezone.utc),
            final_priority=TriagePriority.URGENT.value,
        )
    )

    _restart(database_path)

    assert approval_store.get("case-approved").final_priority == TriagePriority.URGENT.value


def test_saving_the_same_case_twice_updates_instead_of_duplicating(database_path):
    triage_case = _case("case-twice")
    case_store.save(triage_case)

    triage_case.status = CaseStatus.APPROVED
    case_store.save(triage_case)

    assert [c.case_id for c in case_store.list_cases()] == ["case-twice"]
    assert case_store.get("case-twice").status is CaseStatus.APPROVED


def test_audit_log_only_ever_appends(database_path):
    """Ghi lại cùng một case nhiều lần phải CỘNG DỒN dòng, không ghi đè - một audit log ghi đè được
    thì không còn là bằng chứng."""
    case_store.save(_case("case-many"))
    for index in range(3):
        approval_store.log(AuditLogEntry(case_id="case-many", actor="42", action=f"action-{index}"))

    assert [e.action for e in approval_store.audit_for_case("case-many")] == [
        "action-0", "action-1", "action-2",
    ]
