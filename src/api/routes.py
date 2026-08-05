from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from src.agents.graph import agent
from src.database import get_db_session
from src.models.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from src.models.schemas import ChatRequest, ChatResponse, NurseReviewRequest, NurseReviewResponse, TriageCase
from src.services.auth import (
    InvalidCredentialsError,
    NurseRegistrationDeniedError,
    UserAlreadyExistsError,
    auth_service,
)
from src.services.case_store import case_store
from src.services.hitl_review import human_review_service
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
    access_token, expires_in = auth_service.create_access_token(user)
    return TokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
def current_user(request: Request, db: Session = Depends(get_db_session)) -> UserResponse:
    """Return the user represented by the validated Bearer token."""
    user = auth_service.get_user_by_id(db, int(request.state.auth.sub))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tài khoản không còn hoạt động")
    return UserResponse.model_validate(user)


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Receive a patient message and run the controlled triage pipeline."""
    try:
        payload = {"query": request.message}
        if request.case_id:
            payload["case_id"] = request.case_id

        result = await agent.ainvoke(payload)
        triage_case = result["triage_case"]
        return ChatResponse(
            case_id=triage_case.case_id,
            response=result.get("response", ""),
            status=triage_case.status,
            analysis=result.get("analysis", ""),
            structured_data=triage_case.structured_data,
            validation=triage_case.validation,
            red_flags=triage_case.red_flags,
            triage_proposal=triage_case.triage_proposal,
            summary=triage_case.summary,
            pipeline_trace=_build_pipeline_trace(
                message=request.message,
                analysis=result.get("analysis", ""),
                triage_case=triage_case,
                response=result.get("response", ""),
            ),
            requires_human_approval=True,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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


@router.get("/cases/{case_id}", response_model=TriageCase)
async def get_case(case_id: str) -> TriageCase:
    triage_case = case_store.get(case_id)
    if not triage_case:
        raise HTTPException(status_code=404, detail="Case not found")
    return triage_case


@router.post("/cases/{case_id}/review", response_model=NurseReviewResponse)
async def review_case(case_id: str, request: NurseReviewRequest) -> NurseReviewResponse:
    try:
        return human_review_service.review(case_id, request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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
