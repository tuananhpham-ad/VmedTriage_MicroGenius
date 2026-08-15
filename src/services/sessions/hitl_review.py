from __future__ import annotations

from src.models.schemas import (
    ActorRole,
    CaseStatus,
    ConversationMessage,
    HITLAction,
    NurseReviewRequest,
    NurseReviewResponse,
    TriageCase,
)
from src.services.stores.case_store import case_store


class HumanReviewService:
    def review(
        self,
        case_id: str,
        request: NurseReviewRequest,
        *,
        nurse_id: int | None = None,
        nurse_name: str | None = None,
    ) -> NurseReviewResponse:
        triage_case = case_store.get(case_id)
        if not triage_case:
            raise ValueError("Case not found.")

        match request.action:
            case HITLAction.APPROVE:
                self._approve(triage_case, request)
            case HITLAction.EDIT:
                self._edit(triage_case, request)
            case HITLAction.REJECT:
                triage_case.status = CaseStatus.REJECTED
                triage_case.patient_visible_response = None
            case HITLAction.ASK_MORE:
                self._ask_more(triage_case, request)

        if nurse_id is not None:
            from datetime import datetime, timezone

            triage_case.reviewed_by_id = nurse_id
            triage_case.reviewed_by_name = nurse_name
            triage_case.reviewed_at = datetime.now(timezone.utc)
            # Ghi chú nội bộ không được lộ sang lịch sử bệnh nhân. Chỉ phản hồi
            # đã được gửi cho bệnh nhân mới được dùng như feedback hiển thị.
            triage_case.nurse_feedback = triage_case.patient_visible_response

        case_store.save(triage_case)
        return NurseReviewResponse(
            case_id=triage_case.case_id,
            status=triage_case.status,
            patient_visible_response=triage_case.patient_visible_response,
        )

    def _approve(self, triage_case: TriageCase, request: NurseReviewRequest) -> None:
        if not request.approved_response:
            raise ValueError("approved_response is required when approving a case.")

        triage_case.status = CaseStatus.APPROVED
        triage_case.patient_visible_response = request.approved_response
        triage_case.conversation.append(
            ConversationMessage(role=ActorRole.NURSE, content=request.approved_response)
        )

    def _edit(self, triage_case: TriageCase, request: NurseReviewRequest) -> None:
        if not request.approved_response:
            raise ValueError("approved_response is required when editing a case.")

        if request.edited_priority and triage_case.triage_proposal:
            triage_case.triage_proposal.priority = request.edited_priority

        triage_case.status = CaseStatus.APPROVED
        triage_case.patient_visible_response = request.approved_response
        triage_case.conversation.append(
            ConversationMessage(role=ActorRole.NURSE, content=request.approved_response)
        )

    def _ask_more(self, triage_case: TriageCase, request: NurseReviewRequest) -> None:
        if not request.ask_more_question:
            raise ValueError("ask_more_question is required when asking for more information.")

        triage_case.status = CaseStatus.COLLECTING_INFORMATION
        triage_case.patient_visible_response = request.ask_more_question
        triage_case.conversation.append(
            ConversationMessage(role=ActorRole.NURSE, content=request.ask_more_question)
        )


human_review_service = HumanReviewService()
