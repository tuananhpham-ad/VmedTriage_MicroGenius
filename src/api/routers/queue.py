from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from src.models.case_api import ApprovalActionResponse, OverrideRequest, QueueItemView
from src.services import case_approval
from src.services.approval_store import ApprovalStatusRecord
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
