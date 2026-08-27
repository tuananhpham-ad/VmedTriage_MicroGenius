import asyncio
import contextlib
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from src.config import get_settings
from src.database import get_db_session

# Module này chỉ import stdlib + pydantic ở top-level; mọi thứ cần torch nằm trong hàm của nó, nên
# import ở đây không kéo requirements-graph.txt thành bắt buộc để app khởi động.
from src.graph_triage import service as graph_triage_service
from src.models.auth import (
    ChangePasswordRequest,
    DemoLoginRequest,
    EmailVerificationConfirmRequest,
    HealthProfileResponse,
    HealthProfileUpdateRequest,
    LoginRequest,
    MessageResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RegisterRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserResponse,
)
from src.models.health_profile import HealthProfileRecord
from src.models.schemas import (
    ActorRole,
    CaseStatus,
    ChatRequest,
    ChatResponse,
    ConversationMessage,
    NurseCaseView,
    NurseReviewRequest,
    NurseReviewResponse,
    PipelineTraceStage,
    TriageCase,
    TriagePriority,
)
from src.models.user import UserRecord, UserRole
from src.observability.braintrust_tracing import traced_root_span
from src.services.engines.priority_labels import C6_TRIAGE_LABEL_TO_PRIORITY, PRIORITY_RANK
from src.services.infra.account_mailer import account_mailer
from src.services.infra.auth import (
    DemoLoginDisabledError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    NurseRegistrationDeniedError,
    UserAlreadyExistsError,
    auth_service,
)
from src.services.sessions import (
    history_recall,
    red_flag_sla,
    summary_render,
    symptom_case_bridge,
    symptom_session,
)
from src.services.sessions.hitl_review import human_review_service
from src.services.stores.approval_store import AuditLogEntry, approval_store
from src.services.stores.case_store import case_store
from src.services.stores.conversation_store import conversation_store
from src.services.symptom_protocol import registry
from src.services.symptom_protocol.session import (
    EmptyMessageError,
    SessionNotFoundError,
    SessionState,
)
from src.tool.base import MCPToolCallRequest, MCPToolCallResult, MCPToolDescriptor
from src.tool.registry import tool_registry

logger = logging.getLogger("vmedtriage.api")

router = APIRouter()
_safety_gate_tasks: set[asyncio.Task[None]] = set()

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
    delivery = account_mailer.send_email_verification_code(recipient=user.email, code=verification_code)
    if not delivery.delivered:
        # KHÔNG rollback tài khoản: người dùng đã điền xong form, và họ còn đường gửi lại mã. Nhưng
        # phải hét lên trong log - đây là lỗi hạ tầng sẽ biểu hiện thành "đăng ký xong không đăng
        # nhập được", và nếu không tìm được nó ở đây thì sẽ đi tìm nhầm chỗ ở tầng auth.
        logger.error(
            "REGISTER OK nhưng KHÔNG gửi được mã xác thực cho %s (%s). "
            "Người dùng này sẽ không đăng nhập được cho tới khi xác thực được email.",
            user.email, delivery.reason,
        )
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


@router.post("/auth/demo-login", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def demo_login(request: DemoLoginRequest, db: Session = Depends(get_db_session)) -> TokenResponse:
    """Cấp một tài khoản dùng thử MỚI cho vai trò được chọn và đăng nhập luôn.

    Dùng cho demo/nghiệm thu: mỗi lần bấm là một tài khoản `test-<role>-<yyyymmdd-hhmmss>` riêng
    trong DB, nên phiên của hai người demo không lẫn vào nhau. Tắt bằng DEMO_LOGIN_ENABLED=false."""
    try:
        user = auth_service.create_demo_user(db, request.role)
    except DemoLoginDisabledError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except UserAlreadyExistsError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    logger.info("DEMO LOGIN: tạo tài khoản dùng thử %s (role=%s)", user.username, user.role.value)
    access_token, expires_in = auth_service.create_access_token(user)
    return TokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        user=UserResponse.model_validate(user),
    )


@router.post("/auth/email-verification/confirm", response_model=MessageResponse)
def confirm_email_verification(
    payload: EmailVerificationConfirmRequest, db: Session = Depends(get_db_session)
) -> MessageResponse:
    if not auth_service.verify_email(db, email=str(payload.email), code=payload.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mã xác thực không hợp lệ hoặc đã hết hạn.")
    return MessageResponse(message="Email đã được xác thực. Bạn có thể đăng nhập.")


@router.post("/auth/email-verification/resend", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
def resend_email_verification(payload: PasswordResetRequest, db: Session = Depends(get_db_session)) -> MessageResponse:
    """Gửi lại mã xác thực. Trả **503 khi hệ thống thư đang hỏng** thay vì 202 dối.

    Thông điệp thành công vẫn cố ý mơ hồ ("nếu tài khoản tồn tại") để không ai dò được email nào đã
    đăng ký. 503 KHÔNG phá tính chất đó: nó chỉ nói về máy chủ thư, và được trả về **kể cả khi email
    không tồn tại** - lúc đó `probe()` hỏi thẳng SMTP thay vì gửi gì. Nhờ vậy 503 ⇔ "SMTP hỏng",
    không suy ra được gì về tài khoản.

    Đây là chỗ người dùng đang kẹt sẽ tới khi không nhận được thư, nên nó là chỗ tệ nhất để nói dối:
    nghe 202 ba lần rồi vẫn không có thư thì họ nghĩ email mình gõ sai, chứ không nghĩ hệ thống hỏng."""
    result = auth_service.resend_email_verification_code(db, str(payload.email))
    if result is not None:
        user, code = result
        delivery = account_mailer.send_email_verification_code(recipient=user.email, code=code)
    else:
        delivery = account_mailer.probe()
    if not delivery.delivered and delivery.reason != "development_console":
        logger.error("Không gửi lại được mã xác thực: %s", delivery.reason)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Hệ thống gửi email đang gặp sự cố. Vui lòng thử lại sau hoặc liên hệ hỗ trợ.",
        )
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


def _patient_for_health_profile(request: Request, db: Session):
    user = auth_service.get_user_by_id(db, int(request.state.auth.sub))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tài khoản không còn hoạt động")
    if user.role is not UserRole.PATIENT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Chỉ bệnh nhân có thể quản lý hồ sơ sức khỏe")
    return user


@router.get("/me/health-profile", response_model=HealthProfileResponse)
def current_health_profile(request: Request, db: Session = Depends(get_db_session)) -> HealthProfileResponse:
    """Đọc duy nhất hồ sơ do chính bệnh nhân sở hữu; không cấp cho hàng đợi điều dưỡng."""
    user = _patient_for_health_profile(request, db)
    profile = db.query(HealthProfileRecord).filter(HealthProfileRecord.user_id == user.id).one_or_none()
    if profile is None:
        return HealthProfileResponse()
    return HealthProfileResponse.model_validate(profile)


@router.put("/me/health-profile", response_model=HealthProfileResponse)
def update_health_profile(
    request: Request, payload: HealthProfileUpdateRequest, db: Session = Depends(get_db_session)
) -> HealthProfileResponse:
    """Lưu hồ sơ tự khai, không biến nó thành dữ liệu đầu vào tự động của sàng lọc."""
    user = _patient_for_health_profile(request, db)
    profile = db.query(HealthProfileRecord).filter(HealthProfileRecord.user_id == user.id).one_or_none()
    data = payload.model_dump()
    if profile is None:
        profile = HealthProfileRecord(user_id=user.id, **data)
        db.add(profile)
    else:
        for field, value in data.items():
            setattr(profile, field, value)
    now = datetime.now(timezone.utc)
    profile.confirmed_at = now
    profile.updated_at = now
    db.commit()
    db.refresh(profile)
    return HealthProfileResponse.model_validate(profile)


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    """Nhận tin nhắn tự do của bệnh nhân và chạy AGENT triệu chứng (`symptom_protocol/`).

    Trước đây endpoint này chạy pipeline rule-based `src/agents/graph.py` (đã xoá 2026-08-16 cùng
    `POST /cases`, xem `docs/API_DOCUMENTATION.md` §4.5). Đã chuyển sang agent vì
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
    session_id, previous = _prepare_chat_turn(payload, patient_id)
    if previous is not None and previous.status is CaseStatus.NEEDS_MORE_INFO:
        return _direct_patient_message(previous, payload.message)
    with _chat_turn_span(session_id, patient_id=patient_id, streaming=False):
        try:
            session = symptom_session.session_store.submit_message(session_id, payload.message)
        except EmptyMessageError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except SessionNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return await _finish_chat_turn(session, patient_id=patient_id, previous=previous)


@contextlib.contextmanager
def _chat_turn_span(session_id: str, *, patient_id: int, streaming: bool):
    """Root span Braintrust cho TRỌN một lượt `/chat`, mở ở đây vì đây là biên duy nhất biết một
    lượt bắt đầu và kết thúc ở đâu.

    Mọi span bên dưới tự tìm cha qua contextvar của braintrust: các step/tool/llm của
    `symptom_protocol/` (phản chiếu trong `fever_stage_log`) và cả nhánh graph_triage Part 2
    (`decide_for_case` - `traced_root_span` tự lồng làm con khi thấy đã có span đang mở). Thiếu root
    này thì braintrust trả `NOOP_SPAN` cho tất cả và toàn bộ phần hội thoại im lặng biến mất - đúng
    tình trạng trước 2026-08-25, khi Braintrust chỉ nhìn thấy quãng SAU lúc phiếu đã chốt.

    KHÔNG log nội dung tin nhắn ở span này: nguyên văn hội thoại (PHI) đã nằm ở các span con và chịu
    `FEVER_LOG_REDACT`; nhân đôi ở đây là thêm một chỗ nữa phải nhớ che.
    """
    with traced_root_span(
        "chat_turn",
        session_id=session_id,
        metadata={"track": "1_conversation", "streaming": streaming, "patient_id": patient_id},
    ) as (span, trace_link):
        if trace_link:
            logger.info("braintrust.trace_link session_id=%s url=%s", session_id, trace_link)
        yield span


def _direct_patient_message(triage_case: TriageCase, message: str) -> ChatResponse:
    """Bệnh nhân nhắn trong lúc điều dưỡng đang chat trực tiếp (status NEEDS_MORE_INFO).

    KHÔNG được gọi agent: `to_triage_case()` dựng lại `conversation` từ đầu từ session, sẽ xoá mất
    các tin nhắn điều dưỡng vừa ghi trực tiếp vào case_store. Chỉ nối thêm tin nhắn bệnh nhân."""
    triage_case.conversation.append(ConversationMessage(role=ActorRole.PATIENT, content=message))
    case_store.save(triage_case)
    return ChatResponse(
        case_id=triage_case.case_id,
        response="Tin nhắn của bạn đã được gửi tới nhân viên y tế đang hỗ trợ bạn trực tiếp.",
        status=CaseStatus.NEEDS_MORE_INFO,
        requires_human_approval=True,
    )


def _prepare_chat_turn(payload: ChatRequest, patient_id: int) -> tuple[str, TriageCase | None]:
    """Kiểm quyền + tìm/mở phiên. Tách ra để `/chat` và `/chat/stream` không lệch nhau về quyền sở
    hữu case - hai bản sao của một kiểm tra 403 là hai chỗ để quên một chỗ."""
    previous = case_store.get(payload.case_id) if payload.case_id else None
    if previous and previous.patient_id not in (None, patient_id):
        raise HTTPException(status_code=403, detail="Bạn không có quyền tiếp tục case này")

    session_id = payload.case_id
    if session_id is None or symptom_session.session_store.get(session_id, user_id=patient_id) is None:
        # Chưa có phiên, hoặc phiên không khôi phục được. Từ M1 (§4.9) `store.get` đã tra cả kho bền,
        # nên nhánh này giờ chỉ còn là case MỚI thật sự - phiên đang dở sống được qua restart.
        # `user_id` truyền NGAY từ lượt mở: khoá persist là `(conversation_id, user_id)` (M1) và câu
        # hỏi thăm phiên trước (M3) chỉ có đúng một chỗ để xuất hiện, là câu mở.
        # Root span RIÊNG cho lượt mở, không gộp vào `chat_turn`: `/chat/stream` bắt buộc gọi
        # `_prepare_chat_turn` NGOÀI generator để giữ được HTTP status thật (403/400/404), nên ở đó
        # không có `chat_turn` nào để lồng vào. Thà một trace riêng tên rõ ràng, còn hơn để nguyên
        # lượt mở - nơi protocol được chọn và câu hỏi đầu tiên được sinh - rơi vào NOOP_SPAN.
        with traced_root_span("session_open", metadata={"track": "1_conversation", "patient_id": patient_id}):
            session_id = symptom_session.session_store.start_session(user_id=patient_id).session_id
        previous = None
    # Nửa còn lại của khoá composite `user_id + conversation_id`. Gán ở đây vì store không biết gì về
    # xác thực, còn route thì không biết gì về vòng đời phiên - chỗ hai thứ gặp nhau là đây.
    session = symptom_session.session_store.get(session_id, user_id=patient_id)
    if session is not None:
        session.user_id = patient_id
    return session_id, previous


async def _finish_chat_turn(session, *, patient_id: int, previous: TriageCase | None) -> ChatResponse:
    triage_case = symptom_case_bridge.to_triage_case(session, patient_id=patient_id, previous=previous)
    _remember_nurse_summary(session, triage_case, patient_id=patient_id)
    if _should_background_safety_gate(triage_case, previous):
        # Rule-engine priority is saved before scheduling network-dependent C6 work. The patient
        # gets the fixed red-flag response and the nurse queue sees the case immediately.
        case_store.save(triage_case)
        _schedule_safety_gate(triage_case.case_id)
    else:
        await _attach_graph_decision(triage_case, previous)
        changed = (
            _raise_priority_from_c6(triage_case, triage_case.graph_decision)
            if (
                get_settings().graph_triage_mode == "c6"
                and triage_case.graph_decision is not None
                and "safety_gate" in triage_case.graph_decision
            )
            else None
        )
        case_store.save(triage_case)
        if changed is not None:
            _log_priority_raise(triage_case.case_id, triage_case.graph_decision, changed)
        _retry_graph_decision_if_stranded(triage_case)
    return _patient_chat_response(triage_case)


def _remember_nurse_summary(session, triage_case: TriageCase, *, patient_id: int) -> None:
    """Ghi `nurse_summary_json` cho hội thoại - Memory M3 (§4.9).

    CHỈ khi phiên đã đóng, vì hai lý do: phiếu của một phiên mới hỏi được 3 field không dùng vào việc
    gì, và `summary.narrative` (thứ đáng lưu nhất) chỉ được sinh khi phiên đóng (ADR-006). Ghi mỗi
    lượt là một lần UPDATE thừa cho mọi lượt của mọi phiên.

    Ghi ở route chứ không trong `symptom_case_bridge`: `to_triage_case` là hàm THUẦN, và nó phải giữ
    nguyên như vậy - đây là chỗ duy nhất biết cả `patient_id` lẫn phiếu vừa dựng."""
    if session.state is SessionState.COLLECTING:
        return
    first_write = conversation_store.save_nurse_summary(
        session.session_id, user_id=patient_id, summary=triage_case.summary.model_dump(mode="json"),
    )
    if not first_write:
        return
    # Phiếu vừa lưu là phiếu MỚI NHẤT trong ba phiếu sẽ được chắt lọc, nên chắt lọc lại ngay tại đây
    # chứ không đợi lượt mở lần sau. Đây là chỗ RẢNH duy nhất biết chắc cả hai điều kiện: phiên đã
    # đóng, và phiếu của nó đã nằm trong DB (chắt lọc TRƯỚC `save_nurse_summary` sẽ đọc trúng bộ ba
    # cũ, thiếu đúng phiên vừa xong - phiên đáng hỏi thăm nhất).
    history_recall.refresh_for_user(patient_id)


_case_locks: dict[str, asyncio.Lock] = {}
"""Khoá theo `case_id` cho chuỗi đọc-tính-ghi `graph_decision`. `/chat` và `/chat/stream` có thể tới
gần như đồng thời cho CÙNG một case (`streamChatTurn` phía client rơi về `POST /chat` thường khi
stream lỗi giữa chừng - hai request cho một lượt), mỗi request tự đọc `previous` RỒI mới chạy agent
~vài giây; nếu không khoá, request nào lưu SAU cùng thắng và có thể ghi đè kết quả tốt bằng `None`
của request kia dù trace Braintrust của request đó chạy thành công - đúng triệu chứng "trace có,
UI không" mà bug này gây ra."""


async def _save_with_graph_decision(triage_case: TriageCase) -> None:
    lock = _case_locks.setdefault(triage_case.case_id, asyncio.Lock())
    async with lock:
        # Đọc lại NGAY TRƯỚC khi tính, không dùng `previous` bên ngoài lock (đã có thể lỗi thời nếu
        # một request song song vừa lưu xong trong lúc request này còn đang chờ agent trả lời).
        latest = case_store.get(triage_case.case_id)
        await _attach_graph_decision(triage_case, latest)
        case_store.save(triage_case)


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat/stream")
async def chat_stream(payload: ChatRequest, request: Request) -> StreamingResponse:
    """Như `POST /chat` nhưng đẩy câu trả lời ra dần (SSE) thay vì đợi trọn lượt.

    Vì sao là endpoint RIÊNG chứ không thêm cờ vào `/chat`: `/chat` trả một JSON `ChatResponse` và
    có ~8 test khẳng định đúng hình dạng đó. Một endpoint trả hai kiểu thân khác nhau tuỳ tham số là
    thứ không mô tả nổi trong OpenAPI, và client cũ sẽ vỡ khi cờ bị bật nhầm.

    SSE qua `StreamingResponse` chứ không WebSocket - `CLAUDE.md` xếp realtime WebSocket ngoài phạm
    vi MVP. Client PHẢI dùng `fetch()` + `ReadableStream`, không dùng `EventSource`:
    `RoleAuthorizationMiddleware` đòi Bearer token ở header mà `EventSource` không đặt được header.

    Ba loại sự kiện, theo đúng thứ tự một lượt diễn ra:

    - `status`  - đang trích xuất lời khai (LLM #1, không hiển thị được vì nó trả JSON);
    - `token`   - từng mẩu câu hỏi (LLM #2, thứ duy nhất người bệnh đọc);
    - `done`    - NGUYÊN VĂN body của `ChatResponse`, để client dùng lại đúng đường xử lý cũ;
    - `error`   - lỗi sau khi header đã gửi đi, lúc đó không còn đặt được HTTP status nữa.

    Lỗi TRƯỚC khi stream bắt đầu (403/400/404) vẫn là HTTP status thật - `_prepare_chat_turn` chạy
    ngoài generator để giữ được điều đó.
    """
    patient_id = int(request.state.auth.sub)
    session_id, previous = _prepare_chat_turn(payload, patient_id)

    if previous is not None and previous.status is CaseStatus.NEEDS_MORE_INFO:
        # Điều dưỡng đang chat trực tiếp: không có gì để stream (agent không chạy), trả thẳng `done`.
        body = _direct_patient_message(previous, payload.message)

        async def events_paused():
            yield _sse("done", body.model_dump(mode="json"))

        return StreamingResponse(
            events_paused(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def events():
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()

        def on_token(piece: str) -> None:
            # Chạy trong THREADPOOL, không phải event loop - `call_soon_threadsafe` là cách duy nhất
            # đúng để đẩy dữ liệu về đây.
            loop.call_soon_threadsafe(queue.put_nowait, ("token", piece))

        async def run_turn() -> None:
            # Root span mở BÊN TRONG `run_turn`, không phải trong `events()`: span sống theo
            # contextvar, mà `events()` là async generator - context của nó bị tháo/lắp lại mỗi lần
            # generator nhả rồi được gọi tiếp, nên span mở ở đó không chắc còn là span hiện hành khi
            # lượt thật sự chạy. `run_turn` là một task riêng, chạy liền một mạch từ đầu đến cuối.
            try:
                with _chat_turn_span(session_id, patient_id=patient_id, streaming=True):
                    session = await run_in_threadpool(
                        symptom_session.session_store.submit_message,
                        session_id, payload.message, on_token=on_token,
                    )
                    body = await _finish_chat_turn(session, patient_id=patient_id, previous=previous)
                await queue.put(("done", body.model_dump(mode="json")))
            except EmptyMessageError as error:
                await queue.put(("error", {"detail": str(error), "status": 400}))
            except SessionNotFoundError as error:
                await queue.put(("error", {"detail": str(error), "status": 404}))
            except Exception:
                logger.exception("chat_stream.failed session_id=%s", session_id)
                await queue.put(("error", {"detail": "Không xử lý được tin nhắn.", "status": 500}))

        task = asyncio.create_task(run_turn())
        yield _sse("status", {"phase": "reading", "text": "Đang đọc câu trả lời của bạn"})
        try:
            while True:
                kind, data = await queue.get()
                yield _sse(kind, data)
                if kind in ("done", "error"):
                    return
        finally:
            # Người dùng đóng tab giữa chừng: huỷ lượt để threadpool không giữ chỗ vô ích.
            task.cancel()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        # Proxy đệm lại thì SSE mất hết ý nghĩa - nó về đúng bằng một response chậm.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/cases/{case_id}/force-complete", response_model=ChatResponse)
async def force_complete_case(case_id: str, request: Request) -> ChatResponse:
    """Bệnh nhân tự chốt "không còn gì để khai báo thêm" dù checklist chưa đủ.

    KHÔNG dùng `/api/v1/fever/sessions/{id}/confirm`: router đó là demo độc lập, không đụng tới
    `case_store` (xem docstring `fever_intake.py`) - phiên bị chốt bên trong nó nhưng nurse queue
    không bao giờ thấy, và `_attach_graph_decision` (nguồn của "Mức ưu tiên AI đề xuất" + trace
    Braintrust) không bao giờ chạy vì nó chỉ được gọi từ `_finish_chat_turn`. Endpoint này đi đúng
    đường `/chat` đi: chốt phiên rồi dựng lại `TriageCase` + gắn graph decision + lưu case_store,
    y hệt một lượt `/chat` bình thường kết thúc checklist.
    """
    patient_id = int(request.state.auth.sub)
    previous = case_store.get(case_id)
    if previous is not None and previous.patient_id not in (None, patient_id):
        raise HTTPException(status_code=403, detail="Bạn không có quyền tiếp tục case này")
    # Cần root span y như `/chat`: endpoint này chốt phiếu rồi chạy `decide_for_case` - đúng phần
    # đắt nhất của luồng. Thiếu root ở đây thì mọi ca người bệnh tự bấm "không khai thêm" biến mất
    # khỏi Braintrust, và đó lại chính là nhóm ca checklist còn dở - nhóm đáng soi nhất.
    with traced_root_span(
        "force_complete",
        session_id=case_id,
        metadata={"track": "1_conversation", "patient_id": patient_id},
    ):
        try:
            session = symptom_session.session_store.confirm_summary(case_id, True, force=True)
        except SessionNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        triage_case = symptom_case_bridge.to_triage_case(session, patient_id=patient_id, previous=previous)
        _remember_nurse_summary(session, triage_case, patient_id=patient_id)
        await _save_with_graph_decision(triage_case)
        _retry_graph_decision_if_stranded(triage_case)
        return _patient_chat_response(triage_case)


async def _attach_graph_decision(triage_case: TriageCase, previous: TriageCase | None) -> None:
    """Gắn C6/ý kiến graph từ `src/graph_triage/` khi phiếu vừa chốt.

    `to_triage_case` là hàm THUẦN, dựng lại `TriageCase` từ đầu mỗi lượt và không biết gì về trường
    này - nên phải mang kết quả cũ sang bằng tay, nếu không nó biến mất ngay lượt chat kế tiếp.

    Chạy đúng một lần cho mỗi case KHI THÀNH CÔNG: mỗi lượt chạy tốn một lời gọi DeepSeek cộng một
    lời gọi LLM quyết định. Thất bại (`None`) thì lượt sau thử lại - lỗi mạng thoáng qua đáng được
    thử lại, còn lỗi cố định (thiếu thư viện/artifact/API key) đã bị `service._get_agent` nhớ lại nên
    không dựng model lần hai.

    Khi safety gate tắt, case `ESCALATED` giữ nguyên hành vi cũ là không gọi graph. Khi gate bật,
    `_finish_chat_turn` chạy C6 nền cho case này để rule-engine priority không chờ API ngoài.
    """
    if previous is not None and previous.graph_decision is not None:
        has_c6_result = "safety_gate" in previous.graph_decision
        if (get_settings().graph_triage_mode == "c6") == has_c6_result:
            triage_case.graph_decision = previous.graph_decision
            return
    if (
        triage_case.status is CaseStatus.ESCALATED
        and get_settings().graph_triage_mode != "c6"
    ):
        return
    if not triage_case.summary_ready:
        return
    # `decide_for_case` không bao giờ raise (best-effort), nhưng nó đồng bộ và nặng - đẩy sang
    # threadpool để không chặn event loop của các request khác.
    triage_case.graph_decision = await run_in_threadpool(graph_triage_service.decide_for_case, triage_case)


def _retry_graph_decision_if_stranded(triage_case: TriageCase) -> None:
    """Thử lại Part 2/3 dưới nền cho ca đã chốt phiếu mà lượt vừa rồi không lấy được kết quả.

    Trước khi hàng đợi lọc theo `_is_ready_for_nurse_queue`, một lần C6 hỏng chỉ làm mất thẻ mức ưu
    tiên. Bây giờ nó làm ca BIẾN MẤT khỏi hàng đợi - và `_attach_graph_decision` vốn dựa vào "lượt
    chat sau thử lại", trong khi ca vừa chốt phiếu thì không còn lượt chat nào nữa. Đây là chỗ bù lại
    đúng một lần thử: `_complete_safety_gate` chạy một lượt rồi thôi, không có vòng lặp nào.
    """
    if get_settings().graph_triage_mode == "off":
        return
    if triage_case.graph_decision is not None or not triage_case.summary_ready:
        return
    logger.info("graph_triage.retry_scheduled case_id=%s", triage_case.case_id)
    _schedule_safety_gate(triage_case.case_id)


def _should_background_safety_gate(triage_case: TriageCase, previous: TriageCase | None) -> bool:
    """Return whether an escalated case needs new C6 work after its response is sent."""
    return bool(
        get_settings().graph_triage_mode == "c6"
        and triage_case.status is CaseStatus.ESCALATED
        and triage_case.summary_ready
        and (
            previous is None
            or previous.graph_decision is None
            or "safety_gate" not in previous.graph_decision
        )
    )


def _schedule_safety_gate(case_id: str) -> None:
    """Keep the background task strongly referenced and log an unexpected task-level failure."""
    task = asyncio.create_task(_complete_safety_gate(case_id))
    _safety_gate_tasks.add(task)
    task.add_done_callback(_finish_safety_gate_task)


def _finish_safety_gate_task(task: asyncio.Task[None]) -> None:
    """Consume task exceptions; otherwise asyncio only reports them after the request is gone."""
    _safety_gate_tasks.discard(task)
    if task.cancelled():
        return
    try:
        task.result()
    except Exception:
        logger.exception("graph_triage.safety_gate_task_failed")


async def _complete_safety_gate(case_id: str) -> None:
    """Run C6 off the request path, then merge its result into the newest saved case."""
    triage_case = await run_in_threadpool(case_store.get, case_id)
    if triage_case is None:
        logger.warning("graph_triage.safety_gate_case_missing case_id=%s", case_id)
        return
    decision = await run_in_threadpool(graph_triage_service.decide_for_case, triage_case)
    if decision is not None:
        await run_in_threadpool(_persist_safety_gate_result, case_id, decision)


def _persist_safety_gate_result(case_id: str, decision: dict) -> None:
    """Persist C6 result and raise queue priority only while a nurse has not approved it."""
    changed: tuple[TriagePriority, TriagePriority] | None = None

    def apply(triage_case: TriageCase) -> None:
        nonlocal changed
        triage_case.graph_decision = decision
        changed = _raise_priority_from_c6(triage_case, decision)

    updated_case = case_store.update_if_unapproved(case_id, apply)
    if updated_case is None:
        latest = case_store.get(case_id)
        if latest is None:
            logger.warning("graph_triage.safety_gate_case_missing case_id=%s", case_id)
            return
        logger.warning("graph_triage.safety_gate_after_approval case_id=%s", case_id)
        approval_store.log(
            AuditLogEntry(
                case_id=case_id,
                actor="graph_triage_safety_gate",
                action="completed_after_approval",
                reason="C6 result intentionally did not alter an approved case.",
            )
        )
        return
    if changed is not None:
        _log_priority_raise(case_id, decision, changed)


def _log_priority_raise(
    case_id: str,
    decision: dict,
    changed: tuple[TriagePriority, TriagePriority],
) -> None:
    """Write the same structured audit entry for foreground and background C6 promotions."""
    previous, raised = changed
    sources = ",".join(decision.get("escalated_by", [])) or "c6_final_label"
    logger.info(
        "graph_triage.safety_gate_priority_raised case_id=%s from=%s to=%s sources=%s",
        case_id,
        previous.value,
        raised.value,
        sources,
    )
    approval_store.log(
        AuditLogEntry(
            case_id=case_id,
            actor="graph_triage_safety_gate",
            action="raise_priority_from_c6",
            old_value=previous.value,
            new_value=raised.value,
            reason=f"C6 sources: {sources}",
        )
    )


def _raise_priority_from_c6(
    triage_case: TriageCase, decision: dict,
) -> tuple[TriagePriority, TriagePriority] | None:
    """Raise a proposal from the C6 label; equal and lower labels leave it untouched."""
    proposal = triage_case.triage_proposal
    target = C6_TRIAGE_LABEL_TO_PRIORITY.get(decision.get("triage_label"))
    if proposal is None or target is None or PRIORITY_RANK[target] >= PRIORITY_RANK[proposal.priority]:
        return None
    previous = proposal.priority
    proposal.priority = target
    return previous, target


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


_NURSE_HISTORY_STATUSES = frozenset(
    {CaseStatus.APPROVED, CaseStatus.REJECTED, CaseStatus.WITHDRAWN}
)


def _is_ready_for_nurse_queue(triage_case: TriageCase) -> bool:
    """Case đã đủ điều kiện xuất hiện trước mặt điều dưỡng chưa.

    Mặc định là CHƯA: một ca vừa mở, bệnh nhân mới nhắn câu đầu, không nên chiếm chỗ trong hàng đợi
    khi chưa có gì để duyệt. Ca chỉ nổi lên khi Part 2 + Part 3 đã suy luận xong - `graph_decision`
    tồn tại nghĩa là cả hai đã chạy (`decide_for_case` gọi `_source_support_for` TRƯỚC khi dựng
    payload), nên một điều kiện là đủ cho cả hai.

    HAI NGOẠI LỆ, cả hai đều không được bỏ:

    1. `ESCALATED` - red-flag hiện NGAY, không chờ ai. Đây đúng là ngoại lệ có chủ đích của HITL
       (nguyên tắc 4, CLAUDE.md): C6 là lời gọi mạng, có thể chậm vài giây hoặc hỏng hẳn, và
       `red_flag_sla` bắt đầu đếm từ lúc ca escalate - giấu ca đi trong lúc đồng hồ SLA chạy là kiểu
       hỏng tệ nhất có thể có ở màn này.
    2. Ca đã chốt (duyệt/từ chối/đóng) - đó là LỊCH SỬ. Một ca được duyệt trong lúc Part 2 lỗi vẫn
       phải nằm trong tab "Ca đã duyệt", nếu không điều dưỡng mất dấu việc chính họ vừa làm.

    Khi `graph_triage_mode="off"` thì không có Part 2 nào để chờ - lúc đó mốc "xong" lùi về đúng
    nghĩa còn lại của nó: bệnh nhân đã chốt phiếu (`summary_ready`).
    """
    if triage_case.status in _NURSE_HISTORY_STATUSES or triage_case.status is CaseStatus.ESCALATED:
        return True
    if get_settings().graph_triage_mode == "off":
        return triage_case.summary_ready
    return triage_case.graph_decision is not None


@router.get("/nurse/queue", response_model=list[NurseCaseView])
async def nurse_queue(db: Session = Depends(get_db_session)) -> list[NurseCaseView]:
    """Hàng đợi điều dưỡng: case đã sẵn sàng để duyệt, sắp theo mức ưu tiên rồi tới thời gian chờ.

    KHÔNG lọc theo trạng thái duyệt: màn hình điều dưỡng có hai tab ("Hàng đợi" và "Ca đã duyệt")
    cùng ăn endpoint này rồi tự tách phía client (`listScopes` trong `features/nurse.js`). Lọc sẵn
    theo trạng thái ở server sẽ làm rỗng một trong hai tab.

    Cái server LỌC là mức độ sẵn sàng - xem `_is_ready_for_nurse_queue`. Lọc ở đây chứ không ở client
    vì đó là chính sách "điều dưỡng được thấy gì", không phải lựa chọn hiển thị.

    Thứ tự thì GIỮ từ `/queue` cũ và là phần đáng giữ nhất của nó: ca cấp cứu lên đầu, cùng mức thì
    ai chờ lâu hơn đứng trước. Sắp ở server chứ không ở client vì đây là thứ tự AN TOÀN - một bug
    sắp xếp phía client sẽ đẩy ca cấp cứu xuống cuối danh sách mà không ai nhận ra.
    """
    now = datetime.now(timezone.utc)

    def rank(triage_case: TriageCase) -> tuple[int, float]:
        priority = (
            triage_case.triage_proposal.priority
            if triage_case.triage_proposal
            else TriagePriority.MANUAL_REVIEW
        )
        waiting_minutes = max(0.0, (now - triage_case.created_at).total_seconds() / 60)
        return (PRIORITY_RANK.get(priority, 9), -waiting_minutes)

    ready = [item for item in case_store.list_cases() if _is_ready_for_nurse_queue(item)]
    patients = {
        patient_id: user.full_name
        for patient_id in {item.patient_id for item in ready if item.patient_id is not None}
        if (user := db.get(UserRecord, patient_id)) is not None
    }
    views: list[NurseCaseView] = []
    for item in sorted(ready, key=rank):
        payload = item.model_dump()
        payload["patient_display_name"] = patients.get(item.patient_id)
        views.append(NurseCaseView.model_validate(payload))
    return views


@router.get("/patient/history", response_model=list[TriageCase])
async def patient_history(request: Request) -> list[TriageCase]:
    patient_id = int(request.state.auth.sub)
    return sorted(
        (
            _patient_case_view(case)
            for case in case_store.list_cases()
            if case.patient_id == patient_id and case.patient_hidden_at is None
        ),
        key=lambda case: case.updated_at,
        reverse=True,
    )


@router.delete("/cases/{case_id}", response_model=MessageResponse)
async def hide_patient_case(case_id: str, request: Request) -> MessageResponse:
    """Ẩn một ca khỏi lịch sử của đúng người bệnh sở hữu nó.

    Không xóa bản ghi lâm sàng, hàng đợi hay audit: một thao tác giao diện của bệnh nhân tuyệt đối
    không được làm biến mất ca mà điều dưỡng cần đối chiếu hoặc ca đã có red-flag.
    """
    triage_case = case_store.get(case_id)
    if triage_case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    if triage_case.patient_id != int(request.state.auth.sub):
        raise HTTPException(status_code=403, detail="Bạn không có quyền xóa case này")

    if triage_case.patient_hidden_at is None:
        triage_case.patient_hidden_at = datetime.now(timezone.utc)
        case_store.save(triage_case)
        approval_store.log(
            AuditLogEntry(
                case_id=case_id,
                actor=f"patient:{triage_case.patient_id}",
                action="hidden_from_patient_history",
                reason="Người bệnh xóa ca khỏi lịch sử hiển thị.",
            )
        )
    return MessageResponse(message="Đã xóa ca khỏi lịch sử của bạn.")


@router.get("/cases/{case_id}", response_model=TriageCase)
async def get_case(case_id: str, request: Request) -> TriageCase:
    triage_case = case_store.get(case_id)
    if not triage_case:
        raise HTTPException(status_code=404, detail="Case not found")
    if request.state.auth.role.value == "patient" and triage_case.patient_id != int(request.state.auth.sub):
        raise HTTPException(status_code=403, detail="Bạn không có quyền xem case này")
    if request.state.auth.role.value == "patient" and triage_case.patient_hidden_at is not None:
        raise HTTPException(status_code=404, detail="Case không còn trong lịch sử của bạn")
    if request.state.auth.role.value == "patient":
        return _patient_case_view(triage_case)
    return _mark_opened_by_nurse(triage_case)


def _mark_opened_by_nurse(triage_case: TriageCase) -> TriageCase:
    """Điều dưỡng MỞ ca ⇒ dừng đồng hồ SLA (ADR-007, §4.12).

    Đặt ở đây chứ không ở bước duyệt: SLA an toàn hỏi "đã có người thật nhìn thấy ca này chưa", và
    câu trả lời đó có ngay lúc mở, không phải lúc bấm duyệt. Ca mở rồi mà chưa duyệt là vấn đề thông
    lượng - trộn hai thứ vào một chỉ số làm `sla_breach_rate` mất khả năng phát hiện cái thứ hai.

    Chỉ ghi LẦN ĐẦU. Điều dưỡng mở lại ca lần thứ năm không làm đồng hồ chạy lại."""
    if triage_case.first_opened_at is None and triage_case.queued_at is not None:
        triage_case.first_opened_at = datetime.now(timezone.utc)
        case_store.save(triage_case)
    return triage_case


@router.get("/cases/{case_id}/summary")
async def get_case_summary(case_id: str, request: Request) -> dict:
    """Hai output summary của ADR-006 trong MỘT lời gọi.

    - `isbar` — `HandoffSummary` phẳng map sang 5 khối I/S/B/A/R, cho bảng của điều dưỡng;
    - `narrative` — `summary_text`, văn xuôi, cho DB/memory;
    - `field_summary` — bản render TẤT ĐỊNH theo field, là **bản đối chứng** của `narrative`;
    - `raw_conversation` — toàn văn câu trả lời của người bệnh (§4.3).

    Chỉ nhân viên y tế: đây là hồ sơ nội bộ đầy đủ, gồm cả field an toàn còn `unknown` - thứ mà
    `_patient_case_view` cố ý che khỏi bệnh nhân cho tới khi có người duyệt."""
    if request.state.auth.role.value == "patient":
        raise HTTPException(status_code=403, detail="Chỉ nhân viên y tế xem được phiếu bàn giao đầy đủ.")
    triage_case = case_store.get(case_id)
    if not triage_case:
        raise HTTPException(status_code=404, detail="Case not found")
    if triage_case.summary is None:
        raise HTTPException(status_code=409, detail="Ca chưa có phiếu tóm tắt.")

    protocol = registry.protocol_for(triage_case.structured_data.symptom_group if triage_case.structured_data else "")
    answers = dict(triage_case.structured_data.fields) if triage_case.structured_data else {}
    fields = summary_render.field_summary(protocol, answers)
    return {
        "case_id": case_id,
        "isbar": summary_render.to_isbar(triage_case.summary),
        "narrative": triage_case.summary.narrative,
        "field_summary": {
            "reported": fields.reported,
            "denied": fields.denied,
            "unknown_safety": fields.unknown_safety,
            "text": fields.as_text(),
        },
        "raw_conversation": triage_case.summary.raw_conversation,
        "nurse_field_edits": [_dump(edit) for edit in triage_case.nurse_field_edits],
    }


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
        CaseStatus.NEEDS_MORE_INFO,
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
    """Redact internal rule/model output from every patient-facing case view."""
    patient_case = triage_case.model_copy(deep=True)
    # `graph_decision` now includes C6 branch/audit information when the safety gate is enabled.
    # It belongs to the nurse queue, not to a patient response — including the ESCALATED state.
    patient_case.graph_decision = None
    if patient_case.status not in _FINAL_PATIENT_STATUSES:
        patient_case.red_flags = []
        patient_case.triage_proposal = None
        patient_case.queue_item = None
        if patient_case.status not in (CaseStatus.COLLECTING_INFORMATION, CaseStatus.NEEDS_MORE_INFO):
            patient_case.patient_visible_response = None
    _apply_sla_breach(patient_case, triage_case)
    return patient_case


def _apply_sla_breach(patient_case: TriageCase, triage_case: TriageCase) -> None:
    """Quá SLA mà chưa điều dưỡng nào mở ca ⇒ bệnh nhân đọc `SLA_BREACH_MESSAGE` (ADR-007).

    HITL là đường chính; đây là lưới đỡ khi đường chính kẹt. Không có nó thì "chờ điều dưỡng" có thể
    âm thầm trở thành "chờ vô hạn" khi ca trực quá tải hoặc hệ thống thông báo lỗi.

    Câu này GHI ĐÈ nội dung đang hiển thị, kể cả khi phần redact ở trên vừa xoá nó: đúng lúc ca bị bỏ
    quên là lúc bệnh nhân cần đọc một thứ gì đó nhất. Nó KHÔNG đổi `status`, `triage_proposal` hay
    bất cứ quyết định nào - thuần tầng hiển thị."""
    status = red_flag_sla.evaluate(
        queued_at=triage_case.queued_at,
        first_opened_at=triage_case.first_opened_at,
        is_red_flag=triage_case.status is CaseStatus.ESCALATED,
    )
    if status.notify_patient:
        patient_case.patient_visible_response = red_flag_sla.SLA_BREACH_MESSAGE_TEXT


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
