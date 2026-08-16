import os
from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Danh sách model MIỄN PHÍ trên OpenRouter, thử lần lượt từ trên xuống khi model trước bị
# 429 (hết quota/rate limit), 402 (hết số dư) hoặc 404 (model bị gỡ). Đây là danh sách duy nhất
# cần sửa khi OpenRouter đổi/khai tử model free - `provider_router` đọc thẳng từ đây.
#
# Ghi đè không cần sửa code: đặt `OPENROUTER_FREE_MODELS` trong `.env` (các tên cách nhau bằng dấu phẩy).
OPENROUTER_FREE_MODELS: tuple[str, ...] = (
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "poolside/laguna-s-2.1:free",
    "nvidia/nemotron-3.5-lightning:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "cohere/north-mini-code:free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "google/gemma-4-26b-a4b-it:free",
)


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
    llm_provider: Literal["auto", "openai", "deepseek", "gemini", "anthropic", "openrouter"] = "auto"
    llm_provider_order: str = "gemini,deepseek,openai,anthropic,openrouter"
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model_name: str = "gpt-4o-mini"
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_model_name: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"
    gemini_api_key: str = Field(default="", validation_alias=AliasChoices("GEMINI_API_KEY", "GOOGLE_API_KEY"))
    # Đã kiểm 2026-08-15: `gemini-1.5-flash` (default cũ) và `gemini-2.5-flash` đều trả HTTP 404 -
    # Google đã gỡ khỏi API cho key mới. Provider gemini vì thế luôn hỏng rồi mới rơi về deepseek,
    # tốn 2 lời gọi vứt đi mỗi lượt chat. Dùng bản có số hiệu cố định chứ KHÔNG dùng
    # `gemini-flash-latest`: alias đó đổi model dưới chân mình, một hệ y tế cần tái lập được.
    gemini_model_name: str = "gemini-3.5-flash"
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model_name: str = "claude-haiku-4-5-20251001"
    openrouter_api_key: str = Field(
        default="", validation_alias=AliasChoices("OPENROUTER_API_KEY", "OPEN_ROUTER_API_KEY")
    )
    # Rỗng = xoay vòng trên `OPENROUTER_FREE_MODELS`. Đặt tên model ở đây thì model đó được thử
    # TRƯỚC, danh sách free vẫn là phương án dự phòng phía sau.
    openrouter_model_name: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_free_models: str = ",".join(OPENROUTER_FREE_MODELS)
    # Trần số model OpenRouter được thử trong MỘT lần gọi. Có trần vì mỗi model lỗi tốn một vòng
    # HTTP: duyệt hết danh sách khi OpenRouter đang sập sẽ treo request hàng chục giây.
    openrouter_max_model_attempts: int = Field(default=4, ge=1, le=20)
    # Trần TỔNG cho MỘT lần gọi `provider_router.complete()`, cộng dồn mọi provider × mọi model.
    # Cần trần riêng vì hai trần kia nhân với nhau: 3 provider × 4 model = 12 vòng HTTP nối tiếp,
    # đủ để một request của điều dưỡng treo hàng phút khi nhà cung cấp đang sập. Trần thời gian là
    # cái quan trọng hơn - một model timeout 30s thì đếm số lượt không cứu được gì.
    llm_max_total_attempts: int = Field(default=6, ge=1, le=50)
    llm_total_budget_seconds: float = Field(default=45.0, ge=5.0, le=600.0)
    model_name: str = ""
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    supported_model_name: str = "Qwen/Qwen3-8B"

    # Database
    database_url: str = "sqlite:///./data/app.db"

    # Authentication
    jwt_secret_key: str = Field(default="development-only-change-before-production", min_length=32)
    jwt_algorithm: Literal["HS256"] = "HS256"
    access_token_expire_minutes: int = Field(default=60, ge=5, le=10080)
    nurse_registration_code: str = ""
    password_reset_token_expire_minutes: int = Field(default=30, ge=5, le=1440)
    password_reset_base_url: str = "http://localhost:8000"
    email_verification_code_expire_minutes: int = Field(default=10, ge=5, le=60)

    # Leave SMTP_HOST empty during development to write email contents to the server log.
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_use_tls: bool = True

    # Vector Store
    chroma_persist_dir: str = "./data/chroma"

    # Weaviate Cloud (optional best-effort case persistence; pipeline degrades gracefully if unset)
    weaviate_url: str = ""
    weaviate_api_key: str = ""
    weaviate_cases_collection: str = "TriageCases"
    weaviate_knowledge_collection: str = "TriageKnowledge"
    weaviate_query_limit: int = Field(default=5, ge=1, le=50)

    # Console trace: in từng bước hỏi-đáp ra terminal để quan sát khi dev.
    # "auto" = bật khi app_env != production. CẢNH BÁO: trace in nguyên văn hội thoại (PHI),
    # không bật ở môi trường có dữ liệu thật.
    console_trace: Literal["auto", "on", "off"] = "auto"

    # VMedTriage workflow
    semantic_mapping_confidence_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    manual_review_confidence_threshold: float = Field(default=0.60, ge=0.0, le=1.0)
    default_symptom_group: str = "general"
    nurse_queue_high_priority: str = "high"
    nurse_queue_standard_priority: str = "standard"

    # Agent quyết định chạy trên artifact đã train (src/graph_triage/). Mặc định TẮT: nó cần
    # requirements-graph.txt (torch ~2.5 GB) và gọi thêm DeepSeek + OpenAI mỗi khi phiếu chốt.
    # Kết quả CHỈ là ý kiến tham khảo thứ hai cho điều dưỡng, không bao giờ ghi vào
    # TriageProposal.priority - ProtocolTriageEngine/RedFlagSafetyLayer vẫn quyết định duy nhất.
    enable_graph_triage_agent: bool = False
    graph_triage_artifact_root: str = ""
    """Thư mục chứa `logreg_full/` và `bert_full/`. Bỏ trống thì dùng `<repo>/runs`."""
    graph_triage_max_length: int = Field(default=256, ge=1, le=512)

    # MCP external tools
    mcp_call_timeout_seconds: float = Field(default=10.0, ge=0.1, le=60.0)
    mcp_require_human_approval_for_side_effects: bool = True
    mcp_clinical_guideline_server_url: str = ""
    mcp_terminology_server_url: str = ""
    mcp_fhir_server_url: str = ""
    mcp_cds_hooks_server_url: str = ""
    mcp_notification_server_url: str = ""
    mcp_audit_server_url: str = ""


# 5 nhóm triệu chứng phổ biến dùng cho tính năng khai báo triệu chứng (dữ liệu mẫu do đội dự án
# biên soạn cho MVP, CHƯA phải nguồn Bộ Y tế VN/WHO chính thức).
REQUIRED_FIELDS_BY_SYMPTOM_GROUP: dict[str, tuple[str, ...]] = {
    # Nhóm 1: Đau ngực / Tim mạch
    "chest_pain": ("onset", "pain_severity", "pain_radiation"),
    # Nhóm 2: Khó thở / Hô hấp
    "breathing": ("onset", "breathing_severity"),
    # Nhóm 3: Đau bụng / Tiêu hoá
    "abdominal": ("onset", "abdominal_pain_severity", "vomiting_blood"),
    # Nhóm 4: Sốt / Nhiễm trùng
    "fever": ("onset", "fever_severity", "neck_stiffness"),
    # Nhóm 5: Chấn thương / Chảy máu
    "bleeding": ("onset", "bleeding_severity"),
    # Nhóm 6: Đau đầu - bổ sung vì bộ dữ liệu triage_daudau.csv không khớp nhóm nào có sẵn ở trên.
    "headache": ("onset", "headache_severity", "thunderclap_onset"),
    # Nhóm bổ sung (thần kinh) - giữ lại vì logic red-flag đột quỵ đã dùng sẵn trong code cũ
    "neurologic": ("onset", "face_droop", "arm_weakness", "speech_difficulty"),
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
    "abdominal_pain_severity": "Mức độ đau bụng của bạn từ 1 đến 10 là bao nhiêu?",
    "vomiting_blood": "Bạn có nôn ra máu hoặc đi ngoài phân đen không?",
    "rigid_abdomen": "Bụng của bạn có gồng cứng như gỗ khi sờ vào không?",
    "fever_severity": "Bạn sốt nhẹ, vừa hay sốt cao (trên 39°C)?",
    "neck_stiffness": "Bạn có cứng cổ, đau đầu dữ dội hoặc lú lẫn kèm sốt không?",
    "headache_severity": "Mức độ đau đầu của bạn từ 1 đến 10 là bao nhiêu?",
    "thunderclap_onset": "Cơn đau đầu này có đến đột ngột, dữ dội nhất từ trước tới nay chỉ trong vài giây/phút không?",
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
    {
        "code": "gi_bleeding",
        "label": "Nôn ra máu hoặc đi ngoài phân đen (nghi xuất huyết tiêu hoá)",
        "required_true_fields": ("vomiting_blood",),
    },
    {
        "code": "rigid_abdomen",
        "label": "Bụng gồng cứng kèm đau bụng (nghi bụng ngoại khoa cấp)",
        "required_true_fields": ("rigid_abdomen",),
    },
    {
        "code": "fever_with_neck_stiffness",
        "label": "Sốt kèm cứng cổ/lú lẫn (nghi viêm màng não)",
        "required_true_fields": ("neck_stiffness",),
    },
    {
        "code": "thunderclap_headache",
        "label": "Đau đầu dữ dội đột ngột (nghi xuất huyết não)",
        "required_true_fields": ("thunderclap_onset",),
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
        "id": "VMED-AB-001",
        "priority": "Urgent",
        "symptom_group": "abdominal",
        "conditions": {"rigid_abdomen": True},
        "reason": "Đau bụng kèm co cứng thành bụng cần khám sớm để loại trừ bụng ngoại khoa cấp.",
    },
    {
        "id": "VMED-AB-002",
        "priority": "Routine",
        "symptom_group": "abdominal",
        "conditions": {},
        "reason": "Đau bụng không có dấu hiệu nguy hiểm, cần khám để xác định nguyên nhân.",
    },
    {
        "id": "VMED-FV-001",
        "priority": "Urgent",
        "symptom_group": "fever",
        "conditions": {"fever_severity": "high"},
        "reason": "Sốt cao cần được đánh giá sớm.",
    },
    {
        "id": "VMED-FV-002",
        "priority": "Self-care",
        "symptom_group": "fever",
        "conditions": {},
        "reason": "Sốt nhẹ/vừa không có dấu hiệu nguy hiểm, có thể theo dõi tại nhà.",
    },
    {
        "id": "VMED-HD-001",
        "priority": "Urgent",
        "symptom_group": "headache",
        "conditions": {"headache_severity": "high"},
        "reason": "Đau đầu dữ dội cần được đánh giá sớm dù chưa đạt ngưỡng Emergency.",
    },
    {
        "id": "VMED-HD-002",
        "priority": "Self-care",
        "symptom_group": "headache",
        "conditions": {},
        "reason": "Đau đầu nhẹ/vừa không có dấu hiệu nguy hiểm, có thể theo dõi tại nhà.",
    },
    {
        "id": "VMED-GEN-001",
        "priority": "Routine",
        "symptom_group": "general",
        "conditions": {},
        "reason": "Không ghi nhận red flag hoặc tiêu chí urgent trong protocol MVP.",
    },
)


# Nguồn dữ liệu mô phỏng dùng để tách vai trò "phát hiện triệu chứng" (detect) khỏi
# "căn cứ kết luận mức độ ưu tiên" (grounding). Đây là dữ liệu tĩnh nội bộ của dự án,
# KHÔNG gọi API bên ngoài, và KHÔNG dùng để chẩn đoán bệnh cụ thể.
DETECT_SOURCE_LABEL = "Mayo Clinic symptom reference (mô phỏng nội bộ)"
GROUNDING_SOURCE_LABEL = "Bộ Y tế VN/WHO (mô phỏng nội bộ — ngưỡng do đội dự án biên soạn)"


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
