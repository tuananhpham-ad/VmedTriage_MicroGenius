# Sơ đồ kiến trúc

> Bản rút gọn để tra nhanh. **Nguồn chi tiết là [`ARCHITECTURE.md`](../ARCHITECTURE.md)** ở root repo —
> mọi mô tả thành phần, bảng endpoint, phân quyền và nợ kỹ thuật nằm ở đó. File này chỉ giữ hai sơ đồ.

## Tổng quan hệ thống

```mermaid
graph TB
    User([Bệnh nhân / Điều dưỡng]) --> SPA["SPA tĩnh<br/>HTML + JS thuần, không build step<br/>src/ui/new/"]
    SPA -->|REST /api/v1| API["FastAPI<br/>src/main.py"]
    API --> MW["RoleAuthorizationMiddleware<br/>JWT + phân quyền patient/nurse"]

    MW --> Chat["POST /chat - LUỒNG CHÍNH"]
    MW --> Auth["Đăng ký / đăng nhập / xác thực email"]
    MW --> Review["Hàng đợi + duyệt HITL"]

    Chat --> Session["session_store<br/>ProtocolSessionStore singleton"]
    Session --> Engine["symptom_protocol<br/>stage_machine · screening · intake_agent<br/>retraction · rule_engine"]
    Engine --> Protocol["SymptomProtocol<br/>fever · generic"]
    Engine --> LLM["provider_router<br/>OpenAI · DeepSeek · Gemini<br/>Anthropic · OpenRouter"]
    LLM --> Free["OpenRouter: xoay vòng model free<br/>OPENROUTER_FREE_MODELS<br/>429/402/404 → model kế tiếp"]
    LLM -.->|provider + model + latency| Log[("log LLM<br/>console trace · llm-io.jsonl")]

    Session --> Bridge["symptom_case_bridge<br/>case_id = session_id"]
    Bridge --> CaseStore[("case_store<br/>IN-MEMORY")]
    Review --> CaseStore

    Auth --> DB[("SQLite<br/>CHỈ 3 bảng tài khoản")]
    CaseStore -.->|best-effort, tuỳ chọn| Weaviate[("Weaviate Cloud")]
```

Hai điều dễ hiểu sai:

- **LLM chỉ trích xuất field**, không xếp mức khẩn cấp. Mức ưu tiên do `rule_engine` thuần quyết định.
- **Dữ liệu lâm sàng in-memory**, mất khi restart. SQLite chỉ lưu tài khoản.

## Luồng một lượt hội thoại

```mermaid
graph LR
    START((Tin nhắn)) --> Open{Đã chọn<br/>protocol?}
    Open -->|chưa| Select["run_open_turn<br/>chọn protocol từ lời kể"]
    Select -->|không trích được gì| START
    Open -->|rồi| Extract
    Select --> Extract["extract_turn<br/>LLM trích field theo schema MỘT cụm<br/>+ chuẩn hoá enum + screening gộp"]
    Extract --> Merge["_merge_answers"]
    Merge --> Retract["retraction<br/>đính chính + phát hiện mâu thuẫn"]
    Retract --> Rules["rule_engine.evaluate<br/>NGUỒN QUYẾT ĐỊNH DUY NHẤT"]
    Rules -->|EMERGENCY| Red["Chốt đỏ - thông điệp cố định,<br/>hiện NGAY, không chờ duyệt"]
    Rules -->|chưa chốt| Next["stage_machine.advance<br/>chọn cụm kế tiếp"]
    Next -->|còn cụm| Ask["Hỏi tiếp"] --> END((Chờ trả lời))
    Next -->|hết cụm / cạn ngân sách| Summary["Phiếu bàn giao<br/>chờ điều dưỡng duyệt"]
    Red --> END
    Summary --> END
```

## Thành phần chính

| Thành phần | Công nghệ | Vai trò |
|---|---|---|
| Frontend | HTML/CSS/JS ES module thuần | SPA 9 view, không build step |
| Backend | FastAPI + Pydantic | 6 router dưới `/api/v1` |
| Agent | Engine rule + LLM tách bạch (`src/services/symptom_protocol/`) | Hỏi theo cụm, trích field, chốt mức ưu tiên |
| LLM | 5 provider + fallback 2 cấp (`provider_router`) | **Chỉ** trích xuất field; OpenRouter xoay vòng model free |
| Quyết định lâm sàng | `rule_engine` thuần | Nguồn duy nhất của `triage_level` |
| Tài khoản | SQLAlchemy + SQLite | `users`, `password_reset_tokens`, `email_verification_codes` |
| Dữ liệu lâm sàng | In-memory store | `case_store`, `approval_store`, `session_store` |
| Vector store | Weaviate Cloud (tuỳ chọn) | Best-effort, degrade êm khi chưa cấu hình |
