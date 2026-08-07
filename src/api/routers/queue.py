from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from src.models.case_api import (
    ApprovalActionResponse,
    AskMoreRequest,
    AuditActionResponse,
    OverrideRequest,
    QueueItemView,
    RejectRequest,
)
from src.models.schemas import CaseStatus
from src.services import case_approval
from src.services.approval_store import ApprovalStatusRecord, AuditLogEntry
from src.services.priority_labels import priority_label_vi

router = APIRouter(tags=["Feature 2 - Hàng đợi & Duyệt ca (HITL)"])


def _actor_id(request: Request) -> int:
    return int(request.state.auth.sub)


def _to_action_response(record: ApprovalStatusRecord, action: str) -> ApprovalActionResponse:
    return ApprovalActionResponse(
        case_id=record.case_id,
        action=action,
        final_priority=record.final_priority,
        priority_label_vi=priority_label_vi(record.final_priority),
        approved_by=record.approved_by,
        approved_at=record.approved_at,
    )


def _to_audit_response(entry: AuditLogEntry, status_value: str) -> AuditActionResponse:
    return AuditActionResponse(
        case_id=entry.case_id,
        action=entry.action,
        status=status_value,
        reason=entry.reason,
        actor=int(entry.actor),
        timestamp=entry.timestamp,
    )


@router.get("/queue", response_model=list[QueueItemView])
async def get_queue() -> list[QueueItemView]:
    """Danh sách case chờ duyệt, sắp theo priority (Cấp cứu trước) rồi theo thời gian chờ."""
    return [QueueItemView(**item) for item in case_approval.list_queue()]


@router.post("/cases/{case_id}/approve", response_model=ApprovalActionResponse)
async def approve_case(case_id: str, request: Request) -> ApprovalActionResponse:
    """Giữ nguyên đề xuất AI làm final_priority."""
    try:
        record = case_approval.approve(case_id, _actor_id(request))
    except case_approval.CaseNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return _to_action_response(record, "approve")


@router.post("/cases/{case_id}/override", response_model=ApprovalActionResponse)
async def override_case(case_id: str, payload: OverrideRequest, request: Request) -> ApprovalActionResponse:
    """Điều dưỡng đổi mức ưu tiên khác với đề xuất AI (ghi log giá trị cũ/mới)."""
    try:
        record = case_approval.override(case_id, _actor_id(request), payload.new_priority)
    except case_approval.CaseNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    return _to_action_response(record, "override")


@router.post("/cases/{case_id}/escalate", response_model=ApprovalActionResponse)
async def escalate_case(case_id: str, request: Request) -> ApprovalActionResponse:
    """Luôn đặt final_priority = Cấp cứu (mức cao nhất) bất kể AI đề xuất gì."""
    try:
        record = case_approval.escalate(case_id, _actor_id(request))
    except case_approval.CaseNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return _to_action_response(record, "escalate")


@router.post("/cases/{case_id}/reject", response_model=AuditActionResponse)
async def reject_case(case_id: str, payload: RejectRequest, request: Request) -> AuditActionResponse:
    """Từ chối xử lý case (vd: đã xử lý offline). reason_code bắt buộc để tách khỏi thống kê accuracy."""
    try:
        entry = case_approval.reject(case_id, _actor_id(request), payload.reason_code, payload.note)
    except case_approval.CaseNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    return _to_audit_response(entry, CaseStatus.WITHDRAWN.value)


@router.post("/cases/{case_id}/ask_more", response_model=AuditActionResponse)
async def ask_more_case(case_id: str, payload: AskMoreRequest, request: Request) -> AuditActionResponse:
    """Yêu cầu thêm thông tin trước khi quyết định - case quay lại hội thoại với câu hỏi của điều dưỡng."""
    try:
        entry = case_approval.ask_more(case_id, _actor_id(request), payload.question)
    except case_approval.CaseNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    return _to_audit_response(entry, CaseStatus.NEEDS_MORE_INFO.value)
