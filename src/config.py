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
    app_name: str = os.getenv("APP_NAME", "AI20K Agent")
    app_env: Literal["development", "production", "test"] = "development"
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: str = os.getenv("CORS_ORIGINS", "http://localhost:3000")

    # LLM
    llm_provider: Literal["auto", "openai", "deepseek", "gemini", "anthropic", "openrouter"] = "auto"
    llm_provider_order: str = os.getenv("LLM_PROVIDER_ORDER", "gemini,deepseek,openai,anthropic,openrouter")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model_name: str = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_model_name: str = os.getenv("DEEPSEEK_MODEL_NAME", "deepseek-chat")
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    gemini_api_key: str = Field(default="", validation_alias=AliasChoices("GEMINI_API_KEY", "GOOGLE_API_KEY"))
    # Đã kiểm 2026-08-15: `gemini-1.5-flash` (default cũ) và `gemini-2.5-flash` đều trả HTTP 404 -
    # Google đã gỡ khỏi API cho key mới. Provider gemini vì thế luôn hỏng rồi mới rơi về deepseek,
    # tốn 2 lời gọi vứt đi mỗi lượt chat. Dùng bản có số hiệu cố định chứ KHÔNG dùng
    # `gemini-flash-latest`: alias đó đổi model dưới chân mình, một hệ y tế cần tái lập được.
    gemini_model_name: str = os.getenv("GEMINI_MODEL_NAME", "gemini-3.5-flash")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model_name: str = os.getenv("ANTHROPIC_MODEL_NAME", "claude-haiku-4-5-20251001")
    # Rỗng = gọi thẳng api.anthropic.com. Có giá trị = key ở trên là token của một endpoint tương
    # thích Anthropic API bên thứ 3 (proxy) - SDK dùng `auth_token`/Bearer thay vì `api_key`/x-api-key.
    anthropic_base_url: str = os.getenv("ANTHROPIC_BASE_URL", "")
    openrouter_api_key: str = Field(
        default="", validation_alias=AliasChoices("OPENROUTER_API_KEY", "OPEN_ROUTER_API_KEY")
    )
    # Rỗng = xoay vòng trên `OPENROUTER_FREE_MODELS`. Đặt tên model ở đây thì model đó được thử
    # TRƯỚC, danh sách free vẫn là phương án dự phòng phía sau.
    openrouter_model_name: str = os.getenv("OPENROUTER_MODEL_NAME", "")
    openrouter_base_url: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    openrouter_free_models: str = os.getenv("OPENROUTER_FREE_MODELS", ",".join(OPENROUTER_FREE_MODELS))
    # Trần số model OpenRouter được thử trong MỘT lần gọi. Có trần vì mỗi model lỗi tốn một vòng
    # HTTP: duyệt hết danh sách khi OpenRouter đang sập sẽ treo request hàng chục giây.
    openrouter_max_model_attempts: int = Field(default=4, ge=1, le=20)
    # Trần TỔNG cho MỘT lần gọi `provider_router.complete()`, cộng dồn mọi provider × mọi model.
    # Cần trần riêng vì hai trần kia nhân với nhau: 3 provider × 4 model = 12 vòng HTTP nối tiếp,
    # đủ để một request của điều dưỡng treo hàng phút khi nhà cung cấp đang sập. Trần thời gian là
    # cái quan trọng hơn - một model timeout 30s thì đếm số lượt không cứu được gì.
    llm_max_total_attempts: int = Field(default=6, ge=1, le=50)
    llm_total_budget_seconds: float = Field(default=45.0, ge=5.0, le=600.0)
    model_name: str = os.getenv("MODEL_NAME", "")
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    supported_model_name: str = os.getenv("SUPPORTED_MODEL_NAME", "Qwen/Qwen3-8B")

    # Định tuyến model theo VAI TRÒ (`provider_router.RoleProfile`). Rỗng = dùng `llm_provider_order`
    # chung, tức mặc định KHÔNG đổi hành vi gì. Có giá trị ngay cả khi không bao giờ có SLM: nó tách
    # được cấu hình model của bước trích xuất khỏi bước diễn đạt câu hỏi - hai việc có yêu cầu chất
    # lượng rất khác nhau (sai ở trích xuất là sai hồ sơ lâm sàng; sai ở diễn đạt là câu văn khô).
    role_order_fact_extractor: str = os.getenv("ROLE_ORDER_FACT_EXTRACTOR", "")
    role_order_synthesis: str = os.getenv("ROLE_ORDER_SYNTHESIS", "")
    role_order_symptom_group_router: str = os.getenv("ROLE_ORDER_SYMPTOM_GROUP_ROUTER", "")
    # `source_support` (part 3) - mỗi bước định tuyến RIÊNG: bước nào trượt cổng lọc chất lượng thì
    # chỉ bước đó quay về OpenAI, các bước còn lại vẫn chạy provider rẻ. Bỏ trống = kế thừa thứ tự
    # toàn cục, tức cài đặt này không tự nó đổi hành vi gì.
    role_order_claim_splitter: str = os.getenv("ROLE_ORDER_CLAIM_SPLITTER", "")
    role_order_source_verdict: str = os.getenv("ROLE_ORDER_SOURCE_VERDICT", "")
    role_order_source_explain: str = os.getenv("ROLE_ORDER_SOURCE_EXPLAIN", "")

    # Công tắc ngắt cho các cơ chế hội thoại thêm vào ở P2-P3 (§9 P4 mục 5). Mặc định BẬT - đây là
    # đường quay lui, không phải nút bật tính năng.
    #
    # Vì sao có: mỗi cơ chế dưới đây đổi hành vi trên đường người bệnh đang đi, và cách sửa duy nhất
    # trước đây là deploy lại. Bốn công tắc riêng chứ không phải một cờ "flow cũ": một cờ tổng thì
    # không ai dám bật (nó tắt cả những thứ đang chạy đúng), nên trên thực tế nó không phải đường
    # quay lui nào cả. Xem `symptom_protocol/flags.py` để biết mỗi công tắc rơi về đâu.
    #
    # KHÔNG có công tắc nào cho tầng an toàn: `text_safety_signals`, `common_safety/rules`,
    # `rule_engine`, `escalation_lock`, `output_guard` và bước quét sót không được phép tắt (§8.1
    # loại 1). Một công tắc tắt được lớp bảo vệ là một công tắc sẽ bị bật nhầm.
    agent_ranking_enabled: bool = True
    """Tắt ⇒ `next_cluster` quay về first-fit thuần thứ tự khai báo (§8.3). Độ phủ KHÔNG đổi: tier
    field M0/M1 quyết độ phủ, xếp hạng chỉ quyết thứ tự."""
    agent_synthesis_enabled: bool = True
    """Tắt ⇒ câu hỏi phát ra nguyên văn `script_hint`, không gọi model diễn đạt. Đây cũng đúng là
    đường mà `output_guard` rơi về khi model viết sai, nên nhánh này luôn được test sẵn."""
    agent_retraction_confirmation_enabled: bool = True
    """Tắt ⇒ đính chính rủi ro được áp NGAY, không hỏi xác nhận (§5 quy tắc 5). Tắt nếu cổng này hỏi
    lại quá nhiều trong thực tế - đổi lại chấp nhận rủi ro xoá nhầm hồ sơ."""
    agent_unset_operation_enabled: bool = True
    """Tắt ⇒ bỏ qua `operation: "unset"` của model (§4.1), hồ sơ chỉ bị xoá qua đường phủ định field
    cha như trước P2.4. Đây là công tắc cho cơ chế MỚI NHẤT và ít giờ chạy thật nhất."""
    agent_llm_controller_shadow_enabled: bool = False
    """Controller bằng model, **bước 1 shadow mode** (§4.11 mục 13b). Mặc định TẮT.

    Shadow mode nghĩa là model được hỏi và câu trả lời được ĐỐI CHIẾU, nhưng không dòng nào của nó
    tác động tới hành vi - bật hay tắt, hệ thống chạy y hệt. Đây là công tắc `AGENT_LLM_CONTROLLER_
    ENABLED` mà §4.11 ràng buộc 5 yêu cầu, và nó hợp lệ vì controller không phải tầng an toàn theo
    định nghĩa mới: nó chỉ chọn trong tập hành động code đã tính trước.

    Toàn bộ test tất định phải xanh khi tắt cờ (§4.11 ràng buộc 6) - test không bao giờ được phụ
    thuộc vào một endpoint GPU."""
    agent_model_red_flag_branch_enabled: bool = False
    """Nhánh red-flag bằng model (§4.1). **Mặc định TẮT** - nó thêm một lời gọi model mỗi lượt, và
    giá trị của nó là ĐO chứ không phải bảo vệ.

    Đây KHÔNG phải công tắc cho tầng an toàn: bật hay tắt, hai nhánh tất định (L0 + rule engine) vẫn
    chạy nguyên vẹn và vẫn là thứ quyết định escalate. Nhánh model chỉ **thêm** phát hiện và sinh
    `red_flag_agreement`; nó không có đường nào TRỪ đi một mã mà rule đã bật (xem
    `red_flag_branches.merge_findings`). Vì vậy công tắc này không vi phạm quy tắc "không có công
    tắc cho tầng an toàn" ở trên."""

    # Database
    database_url: str = os.getenv("DATABASE_URL", "")

    # Authentication
    jwt_secret_key: str = Field(
        default=os.getenv("JWT_SECRET_KEY", "development-only-change-before-production"), min_length=32
    )
    jwt_algorithm: Literal["HS256"] = "HS256"
    access_token_expire_minutes: int = Field(default=60, ge=5, le=10080)
    nurse_registration_code: str = os.getenv("NURSE_REGISTRATION_CODE", "")
    password_reset_token_expire_minutes: int = Field(default=30, ge=5, le=1440)
    password_reset_base_url: str = os.getenv("PASSWORD_RESET_BASE_URL", "http://localhost:8000")
    email_verification_code_expire_minutes: int = Field(default=10, ge=5, le=60)

    # Leave SMTP_HOST empty during development to write email contents to the server log.
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = os.getenv("SMTP_USERNAME", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_from_email: str = os.getenv("SMTP_FROM_EMAIL", "")
    smtp_use_tls: bool = True

    # Weaviate Cloud (optional best-effort case persistence; pipeline degrades gracefully if unset)
    weaviate_url: str = os.getenv("WEAVIATE_URL", "")
    weaviate_api_key: str = os.getenv("WEAVIATE_API_KEY", "")
    weaviate_cases_collection: str = os.getenv("WEAVIATE_CASES_COLLECTION", "TriageCases")
    weaviate_knowledge_collection: str = os.getenv("WEAVIATE_KNOWLEDGE_COLLECTION", "TriageKnowledge")
    weaviate_query_limit: int = Field(default=5, ge=1, le=50)

    # Console trace: in từng bước hỏi-đáp ra terminal để quan sát khi dev.
    # "auto" = bật khi app_env != production. CẢNH BÁO: trace in nguyên văn hội thoại (PHI),
    # không bật ở môi trường có dữ liệu thật.
    console_trace: Literal["auto", "on", "off"] = "auto"

    # VMedTriage workflow
    semantic_mapping_confidence_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    manual_review_confidence_threshold: float = Field(default=0.60, ge=0.0, le=1.0)
    default_symptom_group: str = os.getenv("DEFAULT_SYMPTOM_GROUP", "general")
    nurse_queue_high_priority: str = os.getenv("NURSE_QUEUE_HIGH_PRIORITY", "high")
    nurse_queue_standard_priority: str = os.getenv("NURSE_QUEUE_STANDARD_PRIORITY", "standard")

    # Agent quyết định chạy trên artifact đã train (src/graph_triage/). Mặc định TẮT: nó cần
    # requirements-graph.txt (torch ~2.5 GB) và gọi thêm DeepSeek + OpenAI mỗi khi phiếu chốt.
    # Kết quả CHỈ là ý kiến tham khảo thứ hai cho điều dưỡng, không bao giờ ghi vào
    # TriageProposal.priority - ProtocolTriageEngine/RedFlagSafetyLayer vẫn quyết định duy nhất.
    enable_graph_triage_agent: bool = False
    graph_triage_artifact_root: str = os.getenv("GRAPH_TRIAGE_ARTIFACT_ROOT", "")
    """Thư mục chứa `logreg_full/` và `bert_full/`. Bỏ trống thì dùng `<repo>/runs`."""
    graph_triage_max_length: int = Field(default=256, ge=1, le=512)

    # Trích nguồn y văn cho nhãn đã chốt (src/source_support/, "part 3"). Mặc định TẮT: nó chạy sau
    # agent quyết định nên chỉ có nghĩa khi ENABLE_GRAPH_TRIAGE_AGENT đã bật, và nó gửi source_span
    # (trích nguyên văn báo cáo bệnh nhân) sang provider LLM - xem cổng chặn PHI trong README của gói.
    # Tầng này KHÔNG BAO GIỜ đổi triage_label; đường duy nhất nó tác động tới ca là bật thêm cờ
    # requires_human_review.
    source_support_enabled: bool = False
    source_support_threshold: float = Field(default=0.55, ge=0.0, le=1.0)
    """Ngưỡng cosine để coi index đã phủ được một claim. ĐÃ HIỆU CHỈNH BẰNG ĐO THẬT (2026-08-19, 11
    claim trên corpus 39 tài liệu / 841 chunk):

        claim TRONG phạm vi corpus, thấp nhất : 0.591
        claim NGOÀI phạm vi, cao nhất         : 0.497
        khoảng tách                           : 0.094

    Giá trị cũ 0.45 nằm DƯỚI nhóm ngoài phạm vi, nên nó nhận nhầm: claim "ngộ độc paracetamol cần
    nhập viện" khớp trang *Fever in under 5s* ở 0.491 và được coi là ĐÃ PHỦ - hệ thống không đi
    search, và đưa cho bước chấm một tài liệu chẳng liên quan. 0.55 nằm giữa khoảng tách.

    Đây cũng là núm vặn CHI PHÍ: nâng ngưỡng thì nhiều lần search hơn (chỗ tốn tiền duy nhất), đổi
    lại claim ngoài phạm vi được đi tìm nguồn thật thay vì gán bừa. Đo lại khi corpus đổi."""
    source_support_max_claims: int = Field(default=3, ge=1, le=5)
    """Mỗi claim tốn một lời gọi ở bước chấm verdict, nên đây vừa là trần chi phí vừa là trần quota."""
    source_support_index_only: bool = False
    """Bỏ hẳn bước search + nạp trang. Cần cho các lượt đo hit-rate lặp lại và cho môi trường không có
    TAVILY_API_KEY."""
    source_support_allowlist: str = os.getenv(
        "SOURCE_SUPPORT_ALLOWLIST",
        "who.int,moh.gov.vn,kcb.vn,nhs.uk,nice.org.uk,cdc.gov,ncbi.nlm.nih.gov,"
        "cochranelibrary.com,msdmanuals.com,aafp.org,acep.org",
    )
    """Danh sách domain y khoa được phép trích. Guard 1 kiểm theo NHÃN TÊN MIỀN, không phải theo chuỗi
    con, nên `nhs.uk.evil.com` không lọt."""
    source_support_search_provider: Literal["gemini", "tavily", "none"] = "gemini"
    """Backend cho bước 3 (tìm URL khi index không phủ được claim).

    `gemini` = Grounding with Google Search, dùng key Gemini sẵn có, KHÔNG tốn tiền riêng nhưng mỗi
    lần search là +1 call Gemini (trần một ca đi từ 10 lên 13).

    ĐÃ ĐO 2026-08-19 - GROUNDING KHÔNG DÙNG ĐƯỢC VỚI KEY FREE TIER HIỆN TẠI: cùng một key, cùng một
    model, call thường trả OK còn call kèm `google_search` trả 429 RESOURCE_EXHAUSTED. Tức grounding
    có hạn mức RIÊNG, tách khỏi hạn mức sinh văn bản thường. Ba bước chính của part 3 (tách claim,
    chấm verdict, diễn giải) vẫn chạy bình thường vì chúng là call thường.

    Hệ quả: đặt `gemini` lúc này thì mỗi lần index miss sẽ đốt một lời gọi hỏng rồi trả về rỗng -
    hành vi an toàn (bước 6 chấm `unsupported`, đoạn văn nói không có tài liệu) nhưng vô ích. Muốn
    nhánh search chạy thật thì cần key Tavily, hoặc nâng Gemini lên tier trả phí.
    `tavily` = HTTP search API, ~$0,008/lần nhưng KHÔNG đụng quota LLM - hợp lý hơn khi chạy hàng loạt,
    vì với free tier thì RPD mới là giới hạn ràng buộc chứ không phải tiền.
    `none`   = tắt hẳn, tương đương `source_support_index_only`."""
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")

    # Braintrust (eval/ tracing, xem eval/config.py). HOÀN TOÀN TUỲ CHỌN: thiếu key thì tracing
    # phải im lặng trở thành no-op, KHÔNG được làm app hay script trong eval/ crash.
    braintrust_api_key: str = os.getenv("BRAINTRUST_API_KEY", "")
    braintrust_project: str = os.getenv("BRAINTRUST_PROJECT", "vmedtriage-eval")

    # MCP external tools
    mcp_call_timeout_seconds: float = Field(default=10.0, ge=0.1, le=60.0)
    mcp_require_human_approval_for_side_effects: bool = True
    mcp_clinical_guideline_server_url: str = os.getenv("MCP_CLINICAL_GUIDELINE_SERVER_URL", "")
    mcp_terminology_server_url: str = os.getenv("MCP_TERMINOLOGY_SERVER_URL", "")
    mcp_fhir_server_url: str = os.getenv("MCP_FHIR_SERVER_URL", "")
    mcp_cds_hooks_server_url: str = os.getenv("MCP_CDS_HOOKS_SERVER_URL", "")
    mcp_notification_server_url: str = os.getenv("MCP_NOTIFICATION_SERVER_URL", "")
    mcp_audit_server_url: str = os.getenv("MCP_AUDIT_SERVER_URL", "")


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
