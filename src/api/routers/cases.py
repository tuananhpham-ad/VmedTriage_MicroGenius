from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from src.config import DETECT_SOURCE_LABEL, GROUNDING_SOURCE_LABEL
from src.models.case_api import CaseInteractionResponse, PatientMessageRequest
from src.models.schemas import TriageCase
from src.services import case_flow
from src.services.priority_labels import priority_label_vi

router = APIRouter(tags=["Feature 1 - AI Agent khai thác triệu chứng"])


def _current_patient_id(request: Request) -> int:
    return int(request.state.auth.sub)


def _to_response(triage_case: TriageCase) -> CaseInteractionResponse:
    proposal = triage_case.triage_proposal
    priority = proposal.priority if proposal else None
    red_flag_reason = "; ".join(item.label for item in triage_case.red_flags) if triage_case.red_flags else None

    return CaseInteractionResponse(
        case_id=triage_case.case_id,
        next_message=triage_case.next_message,
        detected_symptom_group=triage_case.structured_data.symptom_group if triage_case.structured_data else "unknown",
        summary_ready=triage_case.summary_ready,
        red_flag=bool(triage_case.red_flags),
        red_flag_reason=red_flag_reason,
        priority=priority,
        priority_label_vi=priority_label_vi(priority),
        detect_source=proposal.detect_source if proposal else DETECT_SOURCE_LABEL,
        grounding_source=proposal.grounding_source if proposal else GROUNDING_SOURCE_LABEL,
        status=triage_case.status.value,
        summary=triage_case.summary if triage_case.summary_ready else None,
        summary_fields=triage_case.summary_fields if triage_case.summary_ready else [],
    )


@router.post("/cases", response_model=CaseInteractionResponse, status_code=status.HTTP_201_CREATED)
async def create_case(payload: PatientMessageRequest, request: Request) -> CaseInteractionResponse:
    """Bệnh nhân gửi tin nhắn tự do đầu tiên để tạo case mới. Agent detect nhóm triệu chứng ngay."""
    try:
        triage_case = await case_flow.start_case(payload.message, _current_patient_id(request))
    except case_flow.EmptyMessageError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    return _to_response(triage_case)


@router.post("/cases/{case_id}/responses", response_model=CaseInteractionResponse)
async def continue_case(case_id: str, payload: PatientMessageRequest, request: Request) -> CaseInteractionResponse:
    """Bệnh nhân gửi tin nhắn tự do tiếp theo trong hội thoại đã có."""
    try:
        triage_case = await case_flow.continue_case(case_id, payload.message, _current_patient_id(request))
    except case_flow.EmptyMessageError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except case_flow.CaseNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except case_flow.CaseAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    return _to_response(triage_case)
