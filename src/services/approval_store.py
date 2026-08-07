from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class ApprovalStatusRecord(BaseModel):
    """approval_status(case_id, approved_by, approved_at, final_priority)"""

    case_id: str
    approved_by: int
    approved_at: datetime
    final_priority: str


class AuditLogEntry(BaseModel):
    """audit_log(case_id, actor, action, old_value, new_value, timestamp, reason)"""

    case_id: str
    actor: str
    action: str
    old_value: str | None = None
    new_value: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # Bắt buộc cho action="reject" (xem RejectReasonCode) để tách tín hiệu accuracy khỏi lý do
    # ngoài chuyên môn (vd: đã xử lý offline). Tự do cho các action khác (vd: nội dung câu hỏi ask_more).
    reason: str | None = None


class InMemoryApprovalStore:
    """In-memory store for HITL approval status + audit log, mirroring InMemoryCaseStore."""

    def __init__(self) -> None:
        self._approvals: dict[str, ApprovalStatusRecord] = {}
        self._audit_log: list[AuditLogEntry] = []

    def get(self, case_id: str) -> ApprovalStatusRecord | None:
        return self._approvals.get(case_id)

    def upsert(self, record: ApprovalStatusRecord) -> ApprovalStatusRecord:
        self._approvals[record.case_id] = record
        return record

    def log(self, entry: AuditLogEntry) -> AuditLogEntry:
        self._audit_log.append(entry)
        return entry

    def audit_for_case(self, case_id: str) -> list[AuditLogEntry]:
        return [entry for entry in self._audit_log if entry.case_id == case_id]

    def all_audit_entries(self) -> list[AuditLogEntry]:
        return list(self._audit_log)


approval_store = InMemoryApprovalStore()
