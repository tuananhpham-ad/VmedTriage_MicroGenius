from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FeverMessageRequest(BaseModel):
    message: str = Field(default="", max_length=5000)


class FeverCredentialRequest(BaseModel):
    """API key riêng của người test, chỉ giữ in-memory theo phiên, không ghi log/không trả lại nguyên văn."""

    provider: str | None = Field(default=None, max_length=32)
    api_key: str | None = Field(default=None, max_length=512)
    model: str | None = Field(default=None, max_length=128)


class FeverConfirmRequest(BaseModel):
    is_correct: bool


class FeverSessionResponse(BaseModel):
    session_id: str
    state: str
    stage: str
    next_question: str | None = None
    turn_count: int
    answers: dict[str, Any] = Field(default_factory=dict)
    conversation: list[dict[str, str]] = Field(default_factory=list)
    triage_level: str | None = None
    reason_codes: list[str] = Field(default_factory=list)
    triggered_rules: list[str] = Field(default_factory=list)
    stop_reason: str | None = None
    llm_used: bool = Field(
        default=False,
        description="False nghĩa là lượt vừa rồi chạy fallback (LLM lỗi/chưa cấu hình).",
    )
