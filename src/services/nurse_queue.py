from __future__ import annotations

from src.config import get_settings
from src.models.schemas import (
    CaseStatus,
    HandoffSummary,
    NurseQueueItem,
    QueuePriority,
    StructuredSymptomData,
    TriagePriority,
    TriageProposal,
    ValidationResult,
)


class NurseQueueService:
    def build_item(
        self,
        case_id: str,
        data: StructuredSymptomData,
        validation: ValidationResult,
        summary: HandoffSummary,
        proposal: TriageProposal,
    ) -> NurseQueueItem:
        settings = get_settings()
        priority = (
            QueuePriority.HIGH
            if proposal.priority == TriagePriority.EMERGENCY
            else QueuePriority(settings.nurse_queue_standard_priority)
        )
        status = CaseStatus.NEEDS_NURSE_REVIEW if priority == QueuePriority.HIGH else CaseStatus.AWAITING_APPROVAL

        return NurseQueueItem(
            case_id=case_id,
            queue_priority=priority,
            status=status,
            summary=summary,
            structured_data=data,
            validation=validation,
            triage_proposal=proposal,
        )
