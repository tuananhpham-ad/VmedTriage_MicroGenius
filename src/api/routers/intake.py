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
    IntakeCredentialRequest,
    IntakeMessageRequest,
    IntakeProgress,
    IntakeSessionResponse,
    SummaryRow,
)
from src.services.infra import provider_router
from src.services.sessions import intake_session
from src.services.sessions.intake_session import IntakeSession, SessionState

router = APIRouter(prefix="/intake", tags=["Demo - Hỏi đáp thu thập triệu chứng"])


def _build_credential(payload: IntakeCredentialRequest | None) -> provider_router.LLMCredential | None:
    """Dựng credential từ request. Thiếu provider hoặc key -> None (dùng key server)."""
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


def _to_response(session: IntakeSession) -> IntakeSessionResponse:
    summary_ready = session.state in (SessionState.AWAITING_CONFIRMATION, SessionState.CONFIRMED)
    credential = session.credential
    agent = session.agent()
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
        llm_source="user" if credential else "server",
        llm_provider=agent.active_provider,
        llm_model=credential.model if credential else None,
        # Chỉ trả bản đã che - không bao giờ đưa key nguyên văn ra khỏi server.
        llm_key_masked=credential.masked() if credential else None,
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


@router.get("/providers")
async def list_providers() -> dict[str, object]:
    """Danh sách provider + model gợi ý để UI render dropdown chọn LLM."""
    server_available = provider_router.available_providers()
    return {
        "providers": [
            {
                "name": spec.name,
                "env_var": spec.env_var,
                "suggested_models": list(provider_router.SUGGESTED_MODELS.get(spec.name, ())),
                "server_has_key": spec.name in server_available,
            }
            for spec in provider_router.PROVIDER_SPECS
        ],
        "server_default_provider": server_available[0] if server_available else None,
        "note": "Nhập API key của bạn để dùng key riêng; bỏ trống sẽ dùng key server (nếu có).",
    }


@router.post("/providers/test")
async def test_credential(payload: IntakeCredentialRequest) -> dict[str, object]:
    """Gọi thử một request rất ngắn để người test biết key/model của họ có dùng được không."""
    credential = _build_credential(payload)
    if credential is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cần chọn provider và nhập API key để kiểm tra.",
        )
    try:
        result = provider_router.complete(
            [{"role": "user", "content": "Trả lời đúng một từ: OK"}],
            credential=credential,
        )
    except provider_router.NoProviderConfiguredError as error:
        # Thông báo từ provider_router đã được lọc, không chứa API key.
        return {"ok": False, "detail": str(error)}
    return {
        "ok": True,
        "provider": result.provider,
        "model": result.model,
        "sample": result.text[:80],
        "key_masked": credential.masked(),
    }


@router.post("/sessions", response_model=IntakeSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(payload: IntakeCredentialRequest | None = None) -> IntakeSessionResponse:
    """Bắt đầu phiên hỏi-đáp mới, trả về câu hỏi mở đầu.

    Body tuỳ chọn: `{"provider": "deepseek", "api_key": "...", "model": "deepseek-chat"}` để dùng
    key riêng của người test cho cả phiên.
    """
    return _to_response(intake_session.start_session(_build_credential(payload)))


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
