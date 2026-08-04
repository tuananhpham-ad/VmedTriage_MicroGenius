from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ActorRole(str, Enum):
    PATIENT = "patient"
    NURSE = "nurse"
    SYSTEM = "system"


class CaseStatus(str, Enum):
    COLLECTING_INFORMATION = "collecting_information"
    NEEDS_NURSE_REVIEW = "needs_nurse_review"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"


class HITLAction(str, Enum):
    APPROVE = "approve"
    EDIT = "edit"
    REJECT = "reject"
    ESCALATE = "escalate"
    ASK_MORE = "ask_more"


class QueuePriority(str, Enum):
    STANDARD = "standard"
    HIGH = "high"


class TriagePriority(str, Enum):
    EMERGENCY = "Emergency"
    URGENT = "Urgent"
    ROUTINE = "Routine"
    SELF_CARE = "Self-care"
    MANUAL_REVIEW = "Manual review"


class ConversationMessage(BaseModel):
    role: ActorRole
    content: str = Field(..., min_length=1)


class StructuredSymptomData(BaseModel):
    symptom_group: str = "general"
    fields: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: str = "semantic_mapper"


class ValidationIssue(BaseModel):
    code: str
    message: str
    field: str | None = None


class ValidationResult(BaseModel):
    is_valid: bool
    missing_fields: list[str] = Field(default_factory=list)
    contradictions: list[ValidationIssue] = Field(default_factory=list)
    low_confidence: bool = False
    follow_up_questions: list[str] = Field(default_factory=list)


class RedFlagFinding(BaseModel):
    code: str
    label: str
    matched_fields: list[str] = Field(default_factory=list)


class TriageProposal(BaseModel):
    priority: TriagePriority
    protocol_id: str | None = None
    reason: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    requires_manual_review: bool = True


class HandoffSummary(BaseModel):
    chief_complaint: str
    onset: str | None = None
    severity: str | int | None = None
    associated_symptoms: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    red_flags: list[RedFlagFinding] = Field(default_factory=list)
    proposed_priority: TriagePriority | None = None
    protocol_reason: str = ""


class NurseQueueItem(BaseModel):
    case_id: str
    queue_priority: QueuePriority
    status: CaseStatus
    summary: HandoffSummary
    structured_data: StructuredSymptomData
    validation: ValidationResult
    triage_proposal: TriageProposal | None = None


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


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000, description="Patient message")
    case_id: str | None = Field(default=None, description="Existing triage case id")


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
    requires_human_approval: bool = True


class NurseReviewRequest(BaseModel):
    action: HITLAction
    approved_response: str | None = None
    edited_priority: TriagePriority | None = None
    nurse_notes: str | None = None
    ask_more_question: str | None = None


class NurseReviewResponse(BaseModel):
    case_id: str
    status: CaseStatus
    patient_visible_response: str | None = None
