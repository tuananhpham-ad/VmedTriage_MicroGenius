from __future__ import annotations

from datetime import datetime, timezone

from src.models.schemas import CaseStatus, TriageCase, TriagePriority
from src.services.approval_store import ApprovalStatusRecord, AuditLogEntry, approval_store
from src.services.case_store import case_store
from src.services.priority_labels import PRIORITY_RANK, normalize_priority_value, priority_label_vi


class CaseNotFoundError(ValueError):
    pass


def _require_case(case_id: str) -> TriageCase:
    triage_case = case_store.get(case_id)
    if not triage_case:
        raise CaseNotFoundError("Không tìm thấy case")
    return triage_case


def _ai_priority(triage_case: TriageCase) -> TriagePriority:
    if triage_case.triage_proposal:
        return triage_case.triage_proposal.priority
    return TriagePriority.MANUAL_REVIEW


def list_queue() -> list[dict]:
    """GET /queue: sắp theo priority (Cấp cứu trước) rồi theo thời gian chờ (chờ lâu hơn ưu tiên hơn)."""
    now = datetime.now(timezone.utc)
    items: list[dict] = []
    for triage_case in case_store.list_cases():
        approval = approval_store.get(triage_case.case_id)
        if approval and approval.final_priority:
            continue  # đã duyệt/override/escalate -> ra khỏi hàng đợi chờ duyệt
        if triage_case.status not in (CaseStatus.NEEDS_NURSE_REVIEW, CaseStatus.AWAITING_APPROVAL):
            continue

        priority = _ai_priority(triage_case)
        waiting_minutes = max(0.0, (now - triage_case.created_at).total_seconds() / 60)
        items.append(
            {
                "case_id": triage_case.case_id,
                "priority": priority,
                "priority_label_vi": priority_label_vi(priority),
                "red_flag": bool(triage_case.red_flags),
                "waiting_since": triage_case.created_at,
                "waiting_minutes": round(waiting_minutes, 1),
                "symptom_group": triage_case.structured_data.symptom_group if triage_case.structured_data else None,
            }
        )

    items.sort(key=lambda item: (PRIORITY_RANK.get(item["priority"], 9), -item["waiting_minutes"]))
    return items


def approve(case_id: str, actor_id: int) -> ApprovalStatusRecord:
    """Giữ nguyên đề xuất AI làm final_priority."""
    triage_case = _require_case(case_id)
    final_priority = _ai_priority(triage_case).value
    return _record_decision(triage_case, actor_id, "approve", final_priority)


def override(case_id: str, actor_id: int, new_priority: str) -> ApprovalStatusRecord:
    """Điều dưỡng đổi mức ưu tiên khác với đề xuất AI."""
    triage_case = _require_case(case_id)
    final_priority = normalize_priority_value(new_priority)
    return _record_decision(triage_case, actor_id, "override", final_priority)


def escalate(case_id: str, actor_id: int) -> ApprovalStatusRecord:
    """Luôn đặt final_priority = Cấp cứu (mức cao nhất) bất kể AI đề xuất gì."""
    triage_case = _require_case(case_id)
    final_priority = TriagePriority.EMERGENCY.value
    return _record_decision(triage_case, actor_id, "escalate", final_priority, status=CaseStatus.ESCALATED)


def _record_decision(
    triage_case: TriageCase,
    actor_id: int,
    action: str,
    final_priority: str,
    status: CaseStatus = CaseStatus.APPROVED,
) -> ApprovalStatusRecord:
    existing = approval_store.get(triage_case.case_id)
    old_value = existing.final_priority if existing else _ai_priority(triage_case).value

    record = ApprovalStatusRecord(
        case_id=triage_case.case_id,
        approved_by=actor_id,
        approved_at=datetime.now(timezone.utc),
        final_priority=final_priority,
    )
    approval_store.upsert(record)
    approval_store.log(
        AuditLogEntry(
            case_id=triage_case.case_id,
            actor=str(actor_id),
            action=action,
            old_value=old_value,
            new_value=final_priority,
        )
    )

    triage_case.status = status
    case_store.save(triage_case)
    return record


def audit_log_for(case_id: str) -> list[AuditLogEntry]:
    return approval_store.audit_for_case(case_id)
