"""Fever intake API - Bước 6 (`_guidance/fever-detect-agent-task.md`).

PHẠM VI DEMO: giống `src/api/routers/intake.py` - KHÔNG yêu cầu auth (không nằm trong
`ROUTE_POLICIES` của `src/middleware/auth.py`), KHÔNG đẩy case sang điều dưỡng. Chỉ phục vụ luồng
"phát hiện triệu chứng sốt" độc lập; nối vào luồng case/HITL thật là việc ngoài phạm vi task này
(xem `_guidance/fever-detect-agent-task.md` mục 9).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from src.models.fever_api import (
    FeverConfirmRequest,
    FeverCredentialRequest,
    FeverMessageRequest,
    FeverSessionResponse,
)
from src.services.infra import provider_router
from src.services.sessions import fever_session
from src.services.sessions.fever_session import FeverSession

router = APIRouter(prefix="/fever", tags=["Demo - Fever intake (phát hiện triệu chứng sốt)"])


def _build_credential(payload: FeverCredentialRequest | None) -> provider_router.LLMCredential | None:
    if payload is None or not payload.provider or not payload.api_key or not payload.api_key.strip():
        return None
    if payload.provider not in provider_router.SPECS_BY_NAME:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider không hợp lệ: {payload.provider}. Chọn một trong: "
            + ", ".join(provider_router.SPECS_BY_NAME),
        )
    return provider_router.LLMCredential(
        provider=payload.provider,
        api_key=payload.api_key.strip(),
        model=(payload.model or "").strip() or None,
    )


def _to_response(session: FeverSession) -> FeverSessionResponse:
    return FeverSessionResponse(
        session_id=session.session_id,
        state=session.state.value,
        stage=session.stage,
        next_question=session.last_question or None,
        turn_count=session.turn_count,
        answers=dict(session.answers),
        conversation=session.conversation,
        triage_level=session.triage_level,
        reason_codes=session.reason_codes,
        triggered_rules=session.triggered_rules,
        stop_reason=session.stop_reason,
        llm_used=session.llm_used_last_turn,
    )


@router.post("/sessions", response_model=FeverSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(payload: FeverCredentialRequest | None = None) -> FeverSessionResponse:
    """Bắt đầu phiên phát hiện triệu chứng sốt, trả câu hỏi mở đầu (Q0-01: tuổi/người khai)."""
    return _to_response(fever_session.start_session(_build_credential(payload)))


@router.get("/sessions/{session_id}", response_model=FeverSessionResponse)
async def get_session(session_id: str) -> FeverSessionResponse:
    try:
        session = fever_session.get_session(session_id)
    except fever_session.SessionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return _to_response(session)


@router.post("/sessions/{session_id}/messages", response_model=FeverSessionResponse)
async def send_message(session_id: str, payload: FeverMessageRequest) -> FeverSessionResponse:
    """Gửi câu trả lời của người dùng; agent trích xuất + hỏi tiếp, hoặc dừng theo Part 1.3 CS
    (chốt đỏ EMERGENCY / đủ căn cứ / hết ngân sách)."""
    try:
        session = fever_session.submit_message(session_id, payload.message)
    except fever_session.SessionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except fever_session.EmptyMessageError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    return _to_response(session)


@router.post("/sessions/{session_id}/confirm", response_model=FeverSessionResponse)
async def confirm(session_id: str, payload: FeverConfirmRequest) -> FeverSessionResponse:
    """Xác nhận phiếu tóm tắt cuối phiên (Stage 6 CS) trước khi bàn giao HITL."""
    try:
        session = fever_session.confirm_summary(session_id, payload.is_correct, force=payload.force)
    except fever_session.SessionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    return _to_response(session)
