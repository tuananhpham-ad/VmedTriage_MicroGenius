from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "AI20K Agent"
    app_env: Literal["development", "production", "test"] = "development"
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_host: str = "0.0.0.0"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: str = "http://localhost:3000"

    # LLM
    openai_api_key: str = ""
    model_name: str = "gemma-3-4b"
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)

    # Database
    database_url: str = "sqlite:///./data/app.db"

    # Vector Store
    chroma_persist_dir: str = "./data/chroma"

    # VMedTriage workflow
    semantic_mapping_confidence_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    manual_review_confidence_threshold: float = Field(default=0.60, ge=0.0, le=1.0)
    default_symptom_group: str = "general"
    nurse_queue_high_priority: str = "high"
    nurse_queue_standard_priority: str = "standard"

    # MCP external tools
    mcp_call_timeout_seconds: float = Field(default=10.0, ge=0.1, le=60.0)
    mcp_require_human_approval_for_side_effects: bool = True
    mcp_clinical_guideline_server_url: str = ""
    mcp_terminology_server_url: str = ""
    mcp_fhir_server_url: str = ""
    mcp_cds_hooks_server_url: str = ""
    mcp_notification_server_url: str = ""
    mcp_audit_server_url: str = ""


REQUIRED_FIELDS_BY_SYMPTOM_GROUP: dict[str, tuple[str, ...]] = {
    "chest_pain": ("onset", "pain_severity", "pain_radiation"),
    "breathing": ("onset", "breathing_severity"),
    "neurologic": ("onset", "face_droop", "arm_weakness", "speech_difficulty"),
    "bleeding": ("onset", "bleeding_severity"),
    "general": ("onset",),
}


FOLLOW_UP_QUESTIONS: dict[str, str] = {
    "onset": "Triệu chứng bắt đầu từ khi nào?",
    "pain_severity": "Mức độ đau của bạn từ 1 đến 10 là bao nhiêu?",
    "pain_radiation": "Cơn đau có lan sang tay trái, hàm hoặc lưng không?",
    "breathing_severity": "Bạn khó thở nhẹ, vừa hay nặng?",
    "face_droop": "Bạn có bị méo miệng hoặc lệch mặt đột ngột không?",
    "arm_weakness": "Bạn có yếu hoặc tê một bên tay/chân đột ngột không?",
    "speech_difficulty": "Bạn có nói khó, nói ngọng hoặc lú lẫn đột ngột không?",
    "bleeding_severity": "Máu chảy ít, vừa hay nhiều và có cầm được không?",
}


RED_FLAG_RULES: tuple[dict[str, object], ...] = (
    {
        "code": "chest_pain_with_shortness_of_breath",
        "label": "Đau ngực kèm khó thở",
        "required_true_fields": ("chest_pain", "shortness_of_breath"),
    },
    {
        "code": "stroke_signs",
        "label": "Dấu hiệu nghi ngờ đột quỵ",
        "any_true_fields": ("face_droop", "arm_weakness", "speech_difficulty"),
    },
    {
        "code": "heavy_bleeding",
        "label": "Chảy máu nặng",
        "field_equals": {"bleeding_severity": "heavy"},
    },
    {
        "code": "seizure",
        "label": "Co giật",
        "required_true_fields": ("seizure",),
    },
    {
        "code": "loss_of_consciousness",
        "label": "Mất ý thức",
        "required_true_fields": ("loss_of_consciousness",),
    },
    {
        "code": "severe_shortness_of_breath",
        "label": "Khó thở nặng",
        "field_equals": {"breathing_severity": "severe"},
    },
)


TRIAGE_PROTOCOL_RULES: tuple[dict[str, object], ...] = (
    {
        "id": "VMED-CP-001",
        "priority": "Urgent",
        "symptom_group": "chest_pain",
        "conditions": {"chest_pain": True},
        "reason": "Đau ngực không có red flag vẫn cần điều dưỡng/bác sĩ xem sớm.",
    },
    {
        "id": "VMED-BR-001",
        "priority": "Urgent",
        "symptom_group": "breathing",
        "conditions": {"shortness_of_breath": True},
        "reason": "Khó thở cần đánh giá sớm nếu chưa đạt ngưỡng Emergency.",
    },
    {
        "id": "VMED-GEN-001",
        "priority": "Routine",
        "symptom_group": "general",
        "conditions": {},
        "reason": "Không ghi nhận red flag hoặc tiêu chí urgent trong protocol MVP.",
    },
)


MCP_TOOL_SERVER_CONFIGS: dict[str, dict[str, str]] = {
    "clinical_guideline": {
        "setting_name": "mcp_clinical_guideline_server_url",
        "transport": "streamable_http",
    },
    "terminology": {
        "setting_name": "mcp_terminology_server_url",
        "transport": "streamable_http",
    },
    "fhir": {
        "setting_name": "mcp_fhir_server_url",
        "transport": "streamable_http",
    },
    "cds_hooks": {
        "setting_name": "mcp_cds_hooks_server_url",
        "transport": "streamable_http",
    },
    "notification": {
        "setting_name": "mcp_notification_server_url",
        "transport": "streamable_http",
    },
    "audit": {
        "setting_name": "mcp_audit_server_url",
        "transport": "streamable_http",
    },
}


@lru_cache
def get_settings() -> Settings:
    return Settings()
