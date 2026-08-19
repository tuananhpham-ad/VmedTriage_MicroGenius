import asyncio
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
    TriagePriority,
)
from src.services.engines.priority_labels import PRIORITY_RANK
from src.services.infra.account_mailer import account_mailer
from src.services.infra.auth import (
    EmailNotVerifiedError,
    InvalidCredentialsError,
    NurseRegistrationDeniedError,
    UserAlreadyExistsError,
    auth_service,
)
from src.services.sessions import red_flag_sla, summary_render, symptom_case_bridge, symptom_session
from src.services.sessions.hitl_review import human_review_service
from src.services.stores.case_store import case_store
from src.services.symptom_protocol import registry
from src.services.symptom_protocol.session import EmptyMessageError, SessionNotFoundError
from src.tool.base import MCPToolCallRequest, MCPToolCallResult, MCPToolDescriptor
from src.tool.registry import tool_registry

logger = logging.getLogger("vmedtriage.api")

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
    try:
        session = symptom_session.session_store.submit_message(session_id, payload.message)
    except EmptyMessageError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except SessionNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return await _finish_chat_turn(session, patient_id=patient_id, previous=previous)


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
        session_id = symptom_session.session_store.start_session().session_id
        previous = None
    # Nửa còn lại của khoá composite `user_id + conversation_id`. Gán ở đây vì store không biết gì về
    # xác thực, còn route thì không biết gì về vòng đời phiên - chỗ hai thứ gặp nhau là đây.
    session = symptom_session.session_store.get(session_id, user_id=patient_id)
    if session is not None:
        session.user_id = patient_id
    return session_id, previous


async def _finish_chat_turn(session, *, patient_id: int, previous: TriageCase | None) -> ChatResponse:
    triage_case = symptom_case_bridge.to_triage_case(session, patient_id=patient_id, previous=previous)
    await _attach_graph_decision(triage_case, previous)
    case_store.save(triage_case)
    return _patient_chat_response(triage_case)


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

    async def events():
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()

        def on_token(piece: str) -> None:
            # Chạy trong THREADPOOL, không phải event loop - `call_soon_threadsafe` là cách duy nhất
            # đúng để đẩy dữ liệu về đây.
            loop.call_soon_threadsafe(queue.put_nowait, ("token", piece))

        async def run_turn() -> None:
            try:
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
    """Hàng đợi điều dưỡng: TẤT CẢ case, sắp theo mức ưu tiên rồi tới thời gian chờ.

    Trả về tất cả chứ không lọc, vì màn hình điều dưỡng có tab "Tất cả ca" bên cạnh tab "Đang chờ
    duyệt" và tự lọc phía client (`features/nurse.js`). Endpoint `/queue` cũ (đã gỡ cùng
    `case_approval`) lọc sẵn ở server nên không phục vụ được tab đó.

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

    return sorted(case_store.list_cases(), key=rank)


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
