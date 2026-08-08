from __future__ import annotations

from pydantic import BaseModel, Field


class IntakeMessageRequest(BaseModel):
    """Không dùng min_length để trả 400 kèm message rõ ràng thay vì 422 mặc định của FastAPI,
    giống cách PatientMessageRequest (src/models/case_api.py) đang làm."""

    message: str = Field(default="", max_length=5000)


class IntakeCredentialRequest(BaseModel):
    """API key + model do người test tự cung cấp cho phiên này.

    Bỏ trống -> dùng key server đã cấu hình trong `.env` (hoặc fallback deterministic nếu không có).
    Key CHỈ được giữ in-memory theo phiên, không ghi ra đĩa và không trả lại trong response.
    """

    provider: str | None = Field(default=None, max_length=32)
    api_key: str | None = Field(default=None, max_length=512)
    model: str | None = Field(default=None, max_length=128)


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
    llm_source: str = Field(
        default="server",
        description="'user' = đang dùng API key người test nhập; 'server' = key trong .env của server.",
    )
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_key_masked: str | None = Field(
        default=None,
        description="Key đã che (vd sk-••••1f13). Không bao giờ trả về key nguyên văn.",
    )
    disclaimer: str
