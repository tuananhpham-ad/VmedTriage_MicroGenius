"""Kho quyết định duyệt + audit log, lưu bằng SQLite (`approval_records`, `audit_log`).

API công khai (`get`/`upsert`/`log`/`audit_for_case`/`all_audit_entries`) GIỮ NGUYÊN so với bản
in-memory. Hai model Pydantic dưới đây vẫn là hình dạng dữ liệu mà phần còn lại của hệ thống thấy;
ORM row chỉ là cách lưu.

Audit log mất khi restart là mất thứ duy nhất trả lời được câu "ai đã đổi mức của ca này, lúc nào,
vì lý do gì" - trong một hệ y tế có HITL bắt buộc thì đó không phải log tiện ích, nó là hồ sơ.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field
from sqlalchemy import select

from src.database import session_scope
from src.models.case_record import ApprovalRecordRow, AuditLogRow


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


class SqliteApprovalStore:
    def get(self, case_id: str) -> ApprovalStatusRecord | None:
        with session_scope() as session:
            row = session.get(ApprovalRecordRow, case_id)
            if row is None:
                return None
            return ApprovalStatusRecord(
                case_id=row.case_id,
                approved_by=row.approved_by,
                approved_at=row.approved_at,
                final_priority=row.final_priority,
            )

    def upsert(self, record: ApprovalStatusRecord) -> ApprovalStatusRecord:
        with session_scope() as session:
            row = session.get(ApprovalRecordRow, record.case_id)
            if row is None:
                row = ApprovalRecordRow(case_id=record.case_id)
                session.add(row)
            row.approved_by = record.approved_by
            row.approved_at = record.approved_at
            row.final_priority = record.final_priority
        return record

    def log(self, entry: AuditLogEntry) -> AuditLogEntry:
        """CHỈ THÊM. Không có hàm sửa/xoá, và đó là chủ đích - một audit log sửa được thì không còn
        là bằng chứng."""
        with session_scope() as session:
            session.add(
                AuditLogRow(
                    case_id=entry.case_id,
                    actor=entry.actor,
                    action=entry.action,
                    old_value=entry.old_value,
                    new_value=entry.new_value,
                    reason=entry.reason,
                    timestamp=entry.timestamp,
                )
            )
        return entry

    def audit_for_case(self, case_id: str) -> list[AuditLogEntry]:
        with session_scope() as session:
            rows = session.execute(
                select(AuditLogRow).where(AuditLogRow.case_id == case_id).order_by(AuditLogRow.id)
            ).scalars()
            return [self._to_entry(row) for row in rows]

    def all_audit_entries(self) -> list[AuditLogEntry]:
        with session_scope() as session:
            rows = session.execute(select(AuditLogRow).order_by(AuditLogRow.id)).scalars()
            return [self._to_entry(row) for row in rows]

    def _to_entry(self, row: AuditLogRow) -> AuditLogEntry:
        return AuditLogEntry(
            case_id=row.case_id,
            actor=row.actor,
            action=row.action,
            old_value=row.old_value,
            new_value=row.new_value,
            timestamp=row.timestamp,
            reason=row.reason,
        )


approval_store = SqliteApprovalStore()
