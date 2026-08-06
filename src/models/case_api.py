from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.models.schemas import HandoffSummary, SummaryField, TriagePriority


class PatientMessageRequest(BaseModel):
    """Body dùng chung cho POST /cases và POST /cases/{id}/responses.

    Cố ý KHÔNG dùng min_length/field_validator để chặn chuỗi rỗng ở tầng Pydantic: theo đặc tả,
    input rỗng/không hợp lệ phải trả 400 kèm message rõ ràng (không phải 422 mặc định của FastAPI),
    nên việc kiểm tra "rỗng/whitespace-only" được thực hiện tường minh trong src/services/case_flow.py.
    """

    message: str = Field(default="", max_length=5000, description="Tin nhắn tự do của bệnh nhân")


class CaseInteractionResponse(BaseModel):
    """Response chung cho Feature #1 (POST /cases, POST /cases/{id}/responses)."""

    case_id: str
    next_message: str | None = Field(default=None, description="Câu hỏi tiếp theo, null nếu đã đủ thông tin")
    detected_symptom_group: str
    summary_ready: bool
    red_flag: bool
    red_flag_reason: str | None = None
    priority: TriagePriority | None = None
    priority_label_vi: str | None = None
    detect_source: str
    grounding_source: str
    status: str
    summary: HandoffSummary | None = None
    summary_fields: list[SummaryField] = Field(default_factory=list)


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
