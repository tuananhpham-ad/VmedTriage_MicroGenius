from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


# Vai trò của người/hệ thống gửi một tin nhắn trong hội thoại triage.
class ActorRole(str, Enum):
    PATIENT = "patient"
    NURSE = "nurse"
    SYSTEM = "system"


# Trạng thái vòng đời của một case, từ lúc bắt đầu thu thập triệu chứng đến khi điều dưỡng xử lý xong.
class CaseStatus(str, Enum):
    COLLECTING_INFORMATION = "collecting_information"
    NEEDS_NURSE_REVIEW = "needs_nurse_review"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"


# Hành động điều dưỡng có thể thực hiện khi duyệt một case (human-in-the-loop).
# Escalate không phải hành động riêng: đổi mức ưu tiên lên Emergency chỉ là một trường hợp của edit.
class HITLAction(str, Enum):
    APPROVE = "approve"
    EDIT = "edit"
    REJECT = "reject"
    ASK_MORE = "ask_more"


# Mức ưu tiên hiển thị trong hàng đợi điều dưỡng (khác với TriagePriority lâm sàng).
class QueuePriority(str, Enum):
    STANDARD = "standard"
    HIGH = "high"


# Mức độ ưu tiên xử trí lâm sàng do triage engine đề xuất.
class TriagePriority(str, Enum):
    EMERGENCY = "Emergency"
    URGENT = "Urgent"
    ROUTINE = "Routine"
    SELF_CARE = "Self-care"
    MANUAL_REVIEW = "Manual review"


# Một tin nhắn trong lịch sử hội thoại của case (từ bệnh nhân, điều dưỡng hoặc hệ thống).
class ConversationMessage(BaseModel):
    role: ActorRole
    content: str = Field(..., min_length=1)


# Dữ liệu triệu chứng đã được semantic mapper trích xuất có cấu trúc từ tin nhắn tự do.
class StructuredSymptomData(BaseModel):
    symptom_group: str = "general"
    fields: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: str = "semantic_mapper"


# Một vấn đề cụ thể (mâu thuẫn, thiếu dữ liệu...) phát hiện được khi validate structured data.
class ValidationIssue(BaseModel):
    code: str
    message: str
    field: str | None = None


# Kết quả tổng hợp của bước checklist validation, gồm các field còn thiếu và câu hỏi cần hỏi thêm.
class ValidationResult(BaseModel):
    is_valid: bool
    missing_fields: list[str] = Field(default_factory=list)
    contradictions: list[ValidationIssue] = Field(default_factory=list)
    low_confidence: bool = False
    follow_up_questions: list[str] = Field(default_factory=list)


# Một dấu hiệu nguy hiểm (red flag) được red-flag layer phát hiện, dùng để ưu tiên đẩy case lên khẩn cấp.
class RedFlagFinding(BaseModel):
    code: str
    label: str
    matched_fields: list[str] = Field(default_factory=list)


# Đề xuất mức ưu tiên xử trí do triage engine sinh ra, luôn cần điều dưỡng duyệt trước khi có hiệu lực.
class TriageProposal(BaseModel):
    priority: TriagePriority
    protocol_id: str | None = None
    reason: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    requires_manual_review: bool = True
    detect_source: str = Field(
        default="",
        description="Nguồn dùng để phát hiện/gợi ý triệu chứng (mô phỏng nội bộ, KHÔNG dùng để kết luận mức độ ưu tiên).",
    )
    grounding_source: str = Field(
        default="",
        description="Nguồn dùng để 'ground' kết luận mức độ ưu tiên (mô phỏng nội bộ theo Bộ Y tế VN/WHO).",
    )


# Một dòng dữ liệu trong phiếu tóm tắt hiển thị cho điều dưỡng (nhãn + giá trị, đánh dấu nếu còn thiếu).
class SummaryField(BaseModel):
    label: str
    value: Any | None = None
    is_missing: bool = False


# Phiếu tóm tắt bàn giao cho điều dưỡng: gộp triệu chứng, red flag và đề xuất ưu tiên vào một khối duy nhất.
class HandoffSummary(BaseModel):
    chief_complaint: str
    onset: str | None = None
    severity: str | int | None = None
    associated_symptoms: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    red_flags: list[RedFlagFinding] = Field(default_factory=list)
    proposed_priority: TriagePriority | None = None
    protocol_reason: str = ""
    detect_source: str = ""
    grounding_source: str = ""


# Một mục trong hàng đợi điều dưỡng, gộp mọi thông tin cần thiết để duyệt một case mà không cần tra lại nơi khác.
class NurseQueueItem(BaseModel):
    case_id: str
    queue_priority: QueuePriority
    status: CaseStatus
    summary: HandoffSummary
    structured_data: StructuredSymptomData
    validation: ValidationResult
    triage_proposal: TriageProposal | None = None


# Trạng thái đầy đủ của một ca triage, là "nguồn sự thật" được lưu trong case_store xuyên suốt hội thoại nhiều lượt.
class TriageCase(BaseModel):
    case_id: str = Field(default_factory=lambda: str(uuid4()))
    conversation: list[ConversationMessage] = Field(default_factory=list)
    structured_data: StructuredSymptomData | None = None
    validation: ValidationResult | None = None
    red_flags: list[RedFlagFinding] = Field(default_factory=list)
    triage_proposal: TriageProposal | None = None
    summary: HandoffSummary | None = None
    queue_item: NurseQueueItem | None = None
    status: CaseStatus = CaseStatus.COLLECTING_INFORMATION
    patient_visible_response: str | None = None
    patient_id: int | None = Field(default=None, description="Chủ sở hữu case (id bệnh nhân đã đăng nhập)")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    field_ask_counts: dict[str, int] = Field(default_factory=dict)
    next_message: str | None = Field(
        default=None, description="Câu hỏi/phản hồi tiếp theo của agent, null nếu đã đủ thông tin"
    )
    summary_ready: bool = False
    summary_fields: list[SummaryField] = Field(default_factory=list)


# Request body của endpoint chat gốc: tin nhắn bệnh nhân + case_id nếu tiếp tục hội thoại đã có.
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000, description="Patient message")
    case_id: str | None = Field(default=None, description="Existing triage case id")


# Một bước trong pipeline trace, dùng để trả về cho client thấy pipeline đã chạy qua những giai đoạn nào.
class PipelineTraceStage(BaseModel):
    stage: str
    title: str
    output: dict[str, Any] = Field(default_factory=dict)


# Response trả về cho bệnh nhân sau mỗi lượt chat, kèm dữ liệu nội bộ (analysis, pipeline_trace) để debug/hiển thị nurse.
class ChatResponse(BaseModel):
    case_id: str
    response: str = Field(..., description="Patient-safe response")
    status: CaseStatus
    analysis: str = Field(default="", description="Internal pipeline summary")
    structured_data: StructuredSymptomData | None = None
    validation: ValidationResult | None = None
    red_flags: list[RedFlagFinding] = Field(default_factory=list)
    triage_proposal: TriageProposal | None = None
    summary: HandoffSummary | None = None
    pipeline_trace: list[PipelineTraceStage] = Field(default_factory=list)
    requires_human_approval: bool = True


# Request body khi điều dưỡng duyệt một case (approve/edit/reject/escalate/ask_more).
class NurseReviewRequest(BaseModel):
    action: HITLAction
    approved_response: str | None = None
    edited_priority: TriagePriority | None = None
    nurse_notes: str | None = None
    ask_more_question: str | None = None


# Response trả về sau khi điều dưỡng duyệt case, xác nhận trạng thái mới và nội dung sẽ gửi cho bệnh nhân.
class NurseReviewResponse(BaseModel):
    case_id: str
    status: CaseStatus
    patient_visible_response: str | None = None
