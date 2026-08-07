"""Demo intake conversation - Feature #1 phần thu thập triệu chứng.

PHẠM VI DEMO: router này KHÔNG yêu cầu auth (không nằm trong ROUTE_POLICIES của
src/middleware/auth.py) để chạy demo nhanh, và KHÔNG đẩy case sang điều dưỡng. Trước khi dùng thật
phải bổ sung auth + ownership check như luồng Gen2 (src/api/routers/cases.py).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from src.api.routers.result import DISCLAIMER_TEXT
from src.models.intake_api import (
    IntakeConfirmRequest,
    IntakeMessageRequest,
    IntakeProgress,
    IntakeSessionResponse,
    SummaryRow,
)
from src.services import intake_session, provider_router
from src.services.intake_session import IntakeSession, SessionState

router = APIRouter(prefix="/intake", tags=["Demo - Hỏi đáp thu thập triệu chứng"])


def _to_response(session: IntakeSession) -> IntakeSessionResponse:
    summary_ready = session.state in (SessionState.AWAITING_CONFIRMATION, SessionState.CONFIRMED)
    return IntakeSessionResponse(
        session_id=session.session_id,
        state=session.state.value,
        next_question=session.last_question or None,
        progress=IntakeProgress(**intake_session.progress_of(session)),
        summary_rows=[SummaryRow(**row) for row in intake_session.build_summary_rows(session)]
        if summary_ready
        else [],
        summary_ready=summary_ready,
        red_flag=bool(session.red_flags),
        red_flag_labels=session.red_flag_labels(),
        conversation=session.conversation,
        llm_used=session.llm_used_last_turn,
        disclaimer=DISCLAIMER_TEXT,
    )


@router.get("/health")
async def intake_health() -> dict[str, object]:
    """Cho biết demo đang chạy bằng LLM thật hay fallback, và provider nào đang khả dụng."""
    available = provider_router.available_providers()
    return {
        "llm_available": bool(available),
        "active_provider": available[0] if available else None,
        "available_providers": available,
        "fallback_chain": available[1:],
        "all_known_providers": [spec.name for spec in provider_router.PROVIDER_SPECS],
        "note": "llm_available=false nghĩa là câu hỏi sẽ dùng mẫu cố định thay vì sinh tự nhiên.",
    }


@router.post("/sessions", response_model=IntakeSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session() -> IntakeSessionResponse:
    """Bắt đầu phiên hỏi-đáp mới, trả về câu hỏi mở đầu."""
    return _to_response(intake_session.start_session())


@router.get("/sessions/{session_id}", response_model=IntakeSessionResponse)
async def get_session(session_id: str) -> IntakeSessionResponse:
    try:
        session = intake_session.get_session(session_id)
    except intake_session.SessionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return _to_response(session)


@router.post("/sessions/{session_id}/messages", response_model=IntakeSessionResponse)
async def send_message(session_id: str, payload: IntakeMessageRequest) -> IntakeSessionResponse:
    """Gửi câu trả lời; agent trích xuất checklist và hỏi tiếp, hoặc chuyển sang phiếu tóm tắt."""
    try:
        session = intake_session.submit_message(session_id, payload.message)
    except intake_session.SessionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except intake_session.EmptyMessageError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    return _to_response(session)


@router.post("/sessions/{session_id}/confirm", response_model=IntakeSessionResponse)
async def confirm(session_id: str, payload: IntakeConfirmRequest) -> IntakeSessionResponse:
    """Người bệnh xác nhận phiếu tóm tắt đúng/chưa đúng (kèm nội dung cần sửa)."""
    try:
        session = intake_session.confirm_summary(session_id, payload.is_correct, payload.correction)
    except intake_session.SessionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    return _to_response(session)
