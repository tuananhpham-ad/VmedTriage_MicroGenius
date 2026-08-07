from __future__ import annotations

from pydantic import BaseModel, Field


class IntakeMessageRequest(BaseModel):
    """Không dùng min_length để trả 400 kèm message rõ ràng thay vì 422 mặc định của FastAPI,
    giống cách PatientMessageRequest (src/models/case_api.py) đang làm."""

    message: str = Field(default="", max_length=5000)


class IntakeConfirmRequest(BaseModel):
    is_correct: bool
    correction: str | None = Field(default=None, max_length=2000)


class SummaryRow(BaseModel):
    key: str
    label: str
    value: str | None = None
    is_missing: bool
    required: bool


class IntakeProgress(BaseModel):
    ratio: float
    percent: int
    filled_required: int
    total_required: int
    missing_required_labels: list[str] = Field(default_factory=list)


class IntakeSessionResponse(BaseModel):
    session_id: str
    state: str
    next_question: str | None = None
    progress: IntakeProgress
    summary_rows: list[SummaryRow] = Field(default_factory=list)
    summary_ready: bool = False
    red_flag: bool = False
    red_flag_labels: list[str] = Field(default_factory=list)
    conversation: list[dict[str, str]] = Field(default_factory=list)
    llm_used: bool = Field(
        default=False,
        description="False nghĩa là lượt vừa rồi chạy bằng fallback deterministic (LLM chưa cấu hình hoặc lỗi).",
    )
    disclaimer: str
