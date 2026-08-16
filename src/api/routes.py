from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from src.config import get_settings
from src.database import get_db_session

# Module này chỉ import stdlib + pydantic ở top-level; mọi thứ cần torch nằm trong hàm của nó, nên
# import ở đây không kéo requirements-graph.txt thành bắt buộc để app khởi động.
from src.graph_triage import service as graph_triage_service
from src.models.auth import (
    ChangePasswordRequest,
    EmailVerificationConfirmRequest,
    LoginRequest,
    MessageResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RegisterRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserResponse,
)
from src.models.schemas import (
    CaseStatus,
    ChatRequest,
    ChatResponse,
    NurseReviewRequest,
    NurseReviewResponse,
    PipelineTraceStage,
    TriageCase,
)
from src.services.infra.account_mailer import account_mailer
from src.services.infra.auth import (
    EmailNotVerifiedError,
    InvalidCredentialsError,
    NurseRegistrationDeniedError,
    UserAlreadyExistsError,
    auth_service,
)
from src.services.sessions import symptom_case_bridge, symptom_session
from src.services.sessions.hitl_review import human_review_service
from src.services.stores.case_store import case_store
from src.services.symptom_protocol.session import EmptyMessageError, SessionNotFoundError
from src.tool.base import MCPToolCallRequest, MCPToolCallResult, MCPToolDescriptor
from src.tool.registry import tool_registry

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, db: Session = Depends(get_db_session)) -> UserResponse:
    """Create a patient account, or a nurse account with the private registration code."""
    try:
        user = auth_service.register(db, request)
    except UserAlreadyExistsError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except NurseRegistrationDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    verification_code = auth_service.create_email_verification_code(db, user)
    account_mailer.send_email_verification_code(recipient=user.email, code=verification_code)
    return UserResponse.model_validate(user)


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db_session)) -> TokenResponse:
    """Authenticate an account and issue a short-lived JWT access token."""
    try:
        user = auth_service.authenticate(db, request)
    except InvalidCredentialsError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(error),
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    except EmailNotVerifiedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    access_token, expires_in = auth_service.create_access_token(user)
    return TokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        user=UserResponse.model_validate(user),
    )


@router.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_alias(request: RegisterRequest, db: Session = Depends(get_db_session)) -> UserResponse:
    """Alias của POST /register theo đặc tả Feature #3 (POST /auth/register). Giữ /register để tương thích ngược."""
    return register(request, db)


@router.post("/auth/login", response_model=TokenResponse)
def login_alias(request: LoginRequest, db: Session = Depends(get_db_session)) -> TokenResponse:
    """Alias của POST /login theo đặc tả Feature #3 (POST /auth/login). Giữ /login để tương thích ngược."""
    return login(request, db)


@router.post("/auth/email-verification/confirm", response_model=MessageResponse)
def confirm_email_verification(
    payload: EmailVerificationConfirmRequest, db: Session = Depends(get_db_session)
) -> MessageResponse:
    if not auth_service.verify_email(db, email=str(payload.email), code=payload.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mã xác thực không hợp lệ hoặc đã hết hạn.")
    return MessageResponse(message="Email đã được xác thực. Bạn có thể đăng nhập.")


@router.post("/auth/email-verification/resend", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
def resend_email_verification(payload: PasswordResetRequest, db: Session = Depends(get_db_session)) -> MessageResponse:
    result = auth_service.resend_email_verification_code(db, str(payload.email))
    if result is not None:
        user, code = result
        account_mailer.send_email_verification_code(recipient=user.email, code=code)
    return MessageResponse(message="Nếu tài khoản chưa xác thực tồn tại, chúng tôi đã gửi mã mới.")


@router.post("/auth/password-reset/request", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
def request_password_reset(payload: PasswordResetRequest, db: Session = Depends(get_db_session)) -> MessageResponse:
    result = auth_service.create_password_reset_token(db, str(payload.email))
    if result is not None:
        user, token = result
        base_url = get_settings().password_reset_base_url.rstrip("/")
        account_mailer.send_password_reset_email(
            recipient=user.email,
            reset_url=f"{base_url}/?reset_token={token}",
        )
    return MessageResponse(message="Nếu email tồn tại, chúng tôi đã gửi liên kết đặt lại mật khẩu.")


@router.post("/auth/password-reset/confirm", response_model=MessageResponse)
def confirm_password_reset(
    payload: PasswordResetConfirmRequest, db: Session = Depends(get_db_session)
) -> MessageResponse:
    if not auth_service.reset_password(db, token=payload.token, new_password=payload.new_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Liên kết đặt lại mật khẩu không hợp lệ hoặc đã hết hạn.")
    return MessageResponse(message="Đã đặt lại mật khẩu. Bạn có thể đăng nhập bằng mật khẩu mới.")


@router.post("/auth/change-password", response_model=MessageResponse)
def change_password(
    request: Request, payload: ChangePasswordRequest, db: Session = Depends(get_db_session)
) -> MessageResponse:
    user = auth_service.get_user_by_id(db, int(request.state.auth.sub))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tài khoản không còn hoạt động")
    if not auth_service.change_password(
        db, user=user, current_password=payload.current_password, new_password=payload.new_password
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mật khẩu hiện tại không đúng.")
    return MessageResponse(message="Đã đổi mật khẩu. Vui lòng đăng nhập lại.")


@router.get("/me", response_model=UserResponse)
def current_user(request: Request, db: Session = Depends(get_db_session)) -> UserResponse:
    """Return the user represented by the validated Bearer token."""
    user = auth_service.get_user_by_id(db, int(request.state.auth.sub))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tài khoản không còn hoạt động")
    return UserResponse.model_validate(user)


@router.put("/me", response_model=UserResponse)
def update_current_user(
    request: Request, payload: UpdateProfileRequest, db: Session = Depends(get_db_session)
) -> UserResponse:
    user = auth_service.get_user_by_id(db, int(request.state.auth.sub))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tài khoản không còn hoạt động")
    try:
        return UserResponse.model_validate(auth_service.update_profile(db, user=user, payload=payload))
    except UserAlreadyExistsError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    """Nhận tin nhắn tự do của bệnh nhân và chạy AGENT triệu chứng (`symptom_protocol/`).

    Trước đây endpoint này chạy pipeline rule-based `src/agents/graph.py`. Đã chuyển sang agent vì
    agent hỏi theo cụm/stage đúng tài liệu CS, chốt đỏ ngay khi phát hiện red flag, và mọi kết luận
    vẫn do rule engine THUẦN quyết định (LLM chỉ trích xuất field, không xếp mức khẩn cấp).

    Phiên mở ở LƯỢT MỞ, không ghim sẵn protocol nào: tin nhắn đầu là lời kể tự do, protocol
    (`fever` / `general`) chỉ được chọn sau khi đã trích xuất được lời kể đó. Ghim sẵn fever ở đây
    từng khiến người nhắn "tôi đau ngực, đi vài bước là hụt hơi" bị hỏi "bé hay người lớn, bao nhiêu
    tuổi" rồi đi hết bộ câu hỏi về sốt, và không luật đỏ nào quét được ca đó.

    HỢP ĐỒNG API KHÔNG ĐỔI (`ChatRequest`/`ChatResponse`) và case vẫn được ghi vào `case_store` qua
    `symptom_case_bridge` - hàng đợi điều dưỡng, lịch sử bệnh nhân và luồng duyệt HITL chạy y như cũ.
    `case_id` chính là `session_id` của phiên agent."""
    patient_id = int(request.state.auth.sub)
    previous = case_store.get(payload.case_id) if payload.case_id else None
    if previous and previous.patient_id not in (None, patient_id):
        raise HTTPException(status_code=403, detail="Bạn không có quyền tiếp tục case này")

    session_id = payload.case_id
    if session_id is None or symptom_session.session_store.get(session_id) is None:
        # Chưa có phiên (case mới, hoặc phiên đã mất do restart server - store là in-memory): mở
        # phiên mới rồi đưa luôn tin nhắn đầu tiên vào, không bắt người dùng gõ lại.
        session_id = symptom_session.session_store.start_session().session_id
        previous = None

    try:
        session = symptom_session.session_store.submit_message(session_id, payload.message)
    except EmptyMessageError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except SessionNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    triage_case = symptom_case_bridge.to_triage_case(session, patient_id=patient_id, previous=previous)
    await _attach_graph_decision(triage_case, previous)
    case_store.save(triage_case)
    return _patient_chat_response(triage_case)


async def _attach_graph_decision(triage_case: TriageCase, previous: TriageCase | None) -> None:
    """Gắn ý kiến tham khảo thứ hai từ `src/graph_triage/` khi phiếu vừa chốt.

    `to_triage_case` là hàm THUẦN, dựng lại `TriageCase` từ đầu mỗi lượt và không biết gì về trường
    này - nên phải mang kết quả cũ sang bằng tay, nếu không nó biến mất ngay lượt chat kế tiếp.

    Chạy đúng một lần cho mỗi case KHI THÀNH CÔNG: mỗi lượt chạy tốn một lời gọi DeepSeek cộng một
    lời gọi LLM quyết định. Thất bại (`None`) thì lượt sau thử lại - lỗi mạng thoáng qua đáng được
    thử lại, còn lỗi cố định (thiếu thư viện/artifact/API key) đã bị `service._get_agent` nhớ lại nên
    không dựng model lần hai.
    """
    if previous is not None and previous.graph_decision is not None:
        triage_case.graph_decision = previous.graph_decision
        return
    if not triage_case.summary_ready:
        return
    # `decide_for_case` không bao giờ raise (best-effort), nhưng nó đồng bộ và nặng - đẩy sang
    # threadpool để không chặn event loop của các request khác.
    triage_case.graph_decision = await run_in_threadpool(graph_triage_service.decide_for_case, triage_case)


@router.get("/status")
async def agent_status():
    """Check VMedTriage agent status."""
    return {"status": "ready", "agent": "VMedTriage Controlled Pipeline v1.0"}


@router.get("/tools", response_model=list[MCPToolDescriptor])
async def list_tools() -> list[MCPToolDescriptor]:
    """List configured MCP tool descriptors."""
    return tool_registry.list_tools()


@router.post("/tools/{tool_name}/call", response_model=MCPToolCallResult)
async def call_tool(tool_name: str, request: MCPToolCallRequest) -> MCPToolCallResult:
    """Call an external MCP tool through the registry."""
    result = await tool_registry.call(tool_name, request.arguments)
    if not result.ok and result.error and "not configured" in result.error:
        raise HTTPException(status_code=503, detail=result.error)
    if not result.ok and result.error and "not registered" in result.error:
        raise HTTPException(status_code=404, detail=result.error)
    return result


@router.get("/nurse/queue", response_model=list[TriageCase])
async def nurse_queue() -> list[TriageCase]:
    """List triage cases visible to the nurse dashboard."""
    return case_store.list_cases()


@router.get("/patient/history", response_model=list[TriageCase])
async def patient_history(request: Request) -> list[TriageCase]:
    patient_id = int(request.state.auth.sub)
    return sorted(
        (_patient_case_view(case) for case in case_store.list_cases() if case.patient_id == patient_id),
        key=lambda case: case.updated_at,
        reverse=True,
    )


@router.get("/cases/{case_id}", response_model=TriageCase)
async def get_case(case_id: str, request: Request) -> TriageCase:
    triage_case = case_store.get(case_id)
    if not triage_case:
        raise HTTPException(status_code=404, detail="Case not found")
    if request.state.auth.role.value == "patient" and triage_case.patient_id != int(request.state.auth.sub):
        raise HTTPException(status_code=403, detail="Bạn không có quyền xem case này")
    if request.state.auth.role.value == "patient":
        return _patient_case_view(triage_case)
    return triage_case


@router.post("/cases/{case_id}/review", response_model=NurseReviewResponse)
async def review_case(
    case_id: str,
    payload: NurseReviewRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> NurseReviewResponse:
    try:
        nurse = auth_service.get_user_by_id(db, int(request.state.auth.sub))
        return human_review_service.review(
            case_id,
            payload,
            nurse_id=int(request.state.auth.sub),
            nurse_name=nurse.full_name if nurse else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


_PENDING_REVIEW_MESSAGE = "Thông tin của bạn đã được ghi nhận và đang chờ nhân viên y tế duyệt."
_FINAL_PATIENT_STATUSES = {CaseStatus.APPROVED, CaseStatus.ESCALATED}


def _patient_chat_response(triage_case: TriageCase) -> ChatResponse:
    """Return a fixed emergency alert immediately; other guidance still needs review."""
    is_patient_visible = triage_case.status in {
        CaseStatus.COLLECTING_INFORMATION,
        CaseStatus.ESCALATED,
    }
    response = triage_case.patient_visible_response if is_patient_visible else None
    return ChatResponse(
        case_id=triage_case.case_id,
        response=response or _PENDING_REVIEW_MESSAGE,
        status=triage_case.status,
        requires_human_approval=triage_case.status != CaseStatus.ESCALATED,
    )


def _patient_case_view(triage_case: TriageCase) -> TriageCase:
    """Redact internal rule output until a nurse has made a final decision."""
    patient_case = triage_case.model_copy(deep=True)
    if patient_case.status not in _FINAL_PATIENT_STATUSES:
        patient_case.red_flags = []
        patient_case.triage_proposal = None
        patient_case.queue_item = None
        if patient_case.status != CaseStatus.COLLECTING_INFORMATION:
            patient_case.patient_visible_response = None
    return patient_case


def _dump(value):
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else value


def _build_pipeline_trace(
    *,
    message: str,
    analysis: str,
    triage_case: TriageCase,
    response: str,
) -> list[PipelineTraceStage]:
    return [
        PipelineTraceStage(
            stage="input",
            title="Input",
            output={
                "message": message,
                "case_id": triage_case.case_id,
                "conversation_turns": len(triage_case.conversation),
            },
        ),
        PipelineTraceStage(
            stage="mapping",
            title="Semantic mapping",
            output={
                "structured_data": _dump(triage_case.structured_data),
                "analysis": analysis,
            },
        ),
        PipelineTraceStage(
            stage="validation",
            title="Checklist + red flags",
            output={
                "validation": _dump(triage_case.validation),
                "red_flags": [_dump(item) for item in triage_case.red_flags],
            },
        ),
        PipelineTraceStage(
            stage="triage",
            title="Triage proposal",
            output={
                "triage_proposal": _dump(triage_case.triage_proposal),
                "summary": _dump(triage_case.summary),
                "queue_item": _dump(triage_case.queue_item),
                "status": triage_case.status,
            },
        ),
        PipelineTraceStage(
            stage="response",
            title="Final response",
            output={
                "response": response,
                "requires_human_approval": True,
            },
        ),
    ]
