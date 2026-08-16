from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.models.schemas import HandoffSummary, SummaryField, TriagePriority

# `PatientMessageRequest`/`CaseInteractionResponse` đã bị gỡ ngày 2026-08-16 cùng với
# `src/api/routers/cases.py`. Body/response của luồng bệnh nhân khai triệu chứng nay là
# `ChatRequest`/`ChatResponse` trong `src/models/schemas.py` (endpoint POST /chat).


class QueueItemView(BaseModel):
    """GET /queue item."""

    case_id: str
    priority: TriagePriority
    priority_label_vi: str
    red_flag: bool
    waiting_since: datetime
    waiting_minutes: float
    symptom_group: str | None = None


class OverrideRequest(BaseModel):
    new_priority: str = Field(..., min_length=1, description="Priority mới (vd 'Emergency' hoặc 'Cấp cứu')")


class ApprovalActionResponse(BaseModel):
    case_id: str
    action: str
    final_priority: str
    priority_label_vi: str | None = None
    approved_by: int
    approved_at: datetime


class RejectRequest(BaseModel):
    """Body của POST /cases/{id}/reject. reason_code bắt buộc để tách tín hiệu accuracy."""

    reason_code: str = Field(
        ..., description="Một trong: already_handled_offline, ai_incorrect, other (xem RejectReasonCode)"
    )
    note: str | None = Field(default=None, max_length=500)


class AskMoreRequest(BaseModel):
    """Body của POST /cases/{id}/ask_more. Câu hỏi do điều dưỡng chỉ định, khác follow-up tự động."""

    question: str = Field(..., min_length=1, max_length=1000)


class AuditActionResponse(BaseModel):
    """Response chung cho reject/ask_more - không có final_priority như approve/override/escalate."""

    case_id: str
    action: str
    status: str
    reason: str | None = None
    actor: int
    timestamp: datetime


class DisclaimerResponse(BaseModel):
    text: str


class CaseResultResponse(BaseModel):
    """GET /cases/{id}/result."""

    case_id: str
    is_approved: bool
    red_flag: bool
    message: str
    final_priority: str | None = None
    priority_label_vi: str | None = None
    summary: HandoffSummary | None = None
    summary_fields: list[SummaryField] = Field(default_factory=list)
    guidance: str | None = None
    estimated_wait_minutes: int | None = None
