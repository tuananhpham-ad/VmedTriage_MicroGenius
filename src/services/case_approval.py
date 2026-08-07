from __future__ import annotations

from datetime import datetime, timezone

from src.models.schemas import (
    ActorRole,
    CaseStatus,
    ConversationMessage,
    ConversationQualityFlag,
    RejectReasonCode,
    TriageCase,
    TriagePriority,
)
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
            continue  # WITHDRAWN/NEEDS_MORE_INFO cũng bị loại tự nhiên qua điều kiện này
        if triage_case.quality_flag == ConversationQualityFlag.LOW_QUALITY and not triage_case.red_flags:
            # Hội thoại bị quality_guard đánh giá vớ vẩn/off-topic -> không đẩy vào hàng đợi để
            # tránh làm đầy queue. Red-flag LUÔN thắng: có red-flag thì không bao giờ bị suppress ở đây.
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


def reject(case_id: str, actor_id: int, reason_code: str, note: str | None = None) -> AuditLogEntry:
    """Điều dưỡng từ chối xử lý case (KHÔNG phải hạ mức ưu tiên - dùng override cho việc đó).

    reason_code BẮT BUỘC là một trong RejectReasonCode: chỉ 'ai_incorrect' được tính vào thống kê
    độ chính xác AI-điều dưỡng; 'already_handled_offline'/'other' không phải tín hiệu AI đúng/sai
    (ví dụ bệnh nhân đã tự đến viện xử lý case ngoài hệ thống) nên phải tách riêng ngay từ audit log.
    """
    triage_case = _require_case(case_id)
    try:
        code = RejectReasonCode(reason_code)
    except ValueError as error:
        raise ValueError(f"reason_code không hợp lệ: {reason_code!r}") from error

    old_value = _ai_priority(triage_case).value
    triage_case.status = CaseStatus.WITHDRAWN
    triage_case.patient_visible_response = None
    case_store.save(triage_case)

    return approval_store.log(
        AuditLogEntry(
            case_id=triage_case.case_id,
            actor=str(actor_id),
            action="reject",
            old_value=old_value,
            new_value=None,
            reason=f"{code.value}: {note}" if note else code.value,
        )
    )


def ask_more(case_id: str, actor_id: int, question: str) -> AuditLogEntry:
    """Điều dưỡng cần thêm thông tin trước khi approve/override/reject.

    Khác với follow-up question tự động của checklist: câu hỏi này do điều dưỡng chỉ định trực
    tiếp, case quay lại hội thoại ở trạng thái NEEDS_MORE_INFO (không lẫn với COLLECTING_INFORMATION
    ban đầu) và tự động rời khỏi hàng đợi cho tới khi bệnh nhân trả lời lượt tiếp theo.
    """
    triage_case = _require_case(case_id)
    cleaned_question = (question or "").strip()
    if not cleaned_question:
        raise ValueError("question không được để trống khi yêu cầu ask_more.")

    triage_case.status = CaseStatus.NEEDS_MORE_INFO
    triage_case.next_message = cleaned_question
    triage_case.summary_ready = False
    triage_case.conversation.append(ConversationMessage(role=ActorRole.NURSE, content=cleaned_question))
    case_store.save(triage_case)

    return approval_store.log(
        AuditLogEntry(
            case_id=triage_case.case_id,
            actor=str(actor_id),
            action="ask_more",
            reason=cleaned_question,
        )
    )


def audit_log_for(case_id: str) -> list[AuditLogEntry]:
    return approval_store.audit_for_case(case_id)
