# Architecture Document

## System Overview

VMedTriage là một hệ thống hỗ trợ phân luồng y tế có kiểm soát: bệnh nhân nhập triệu chứng qua demo web UI, FastAPI nhận request, LangGraph agent chạy pipeline triage, sau đó tạo phản hồi an toàn cho bệnh nhân và case/handoff summary cho điều dưỡng duyệt. Kiến trúc hiện tại ưu tiên an toàn: mọi kết quả triage đều yêu cầu human-in-the-loop, các side-effect tools bị chặn nếu chưa có phê duyệt rõ ràng.

Runtime hiện tại là một backend Python đơn khối có UI tĩnh được mount trực tiếp bởi FastAPI. Luồng triage đang chạy bằng rule-backed services và in-memory stores cho MVP/demo; data layer mục tiêu là Weaviate Cloud để lưu persistent triage cases, tool state và dữ liệu vector/semantic search.

## System Overview Diagram

```mermaid
graph TB
    Patient[Patient / User] -->|Open /| StaticMount
    Nurse[Nurse / Clinician] -->|Review in same UI| StaticUI

    StaticUI -->|POST /api/v1/chat| ChatAPI[Chat API]
    StaticUI -->|GET /api/v1/nurse/queue| QueueAPI[Nurse Queue API]
    StaticUI -->|GET /api/v1/cases/:case_id| CaseAPI[Case API]
    StaticUI -->|POST /api/v1/cases/:case_id/review| ReviewAPI[Human Review API]
    StaticUI -->|GET /api/v1/tools<br/>POST /api/v1/tools/:tool/call| ToolsAPI[MCP Tools API]

    subgraph FastAPIApp[FastAPI Application - src/main.py]
        StaticMount[StaticFiles Mount /]
        Health[Health Endpoint /health]
        StaticMount --> StaticUI[Demo Static UI<br/>HTML + CSS + JavaScript]

        subgraph APIRoutes[API Router - /api/v1]
            ChatAPI
            QueueAPI
            CaseAPI
            ReviewAPI
            ToolsAPI
            StatusAPI[Status API]
        end
    end

    ChatAPI -->|ainvoke| Agent[LangGraph Agent<br/>src/agents/graph.py]

    subgraph LangGraph[Controlled LangGraph Flow]
        TriageNode[triage_pipeline node]
        Decision{error?}
        RespondNode[patient_safe_response node]
        EndNode([END])

        TriageNode --> Decision
        Decision -->|no error| RespondNode
        Decision -->|error| EndNode
        RespondNode --> EndNode
    end

    Agent --> TriageNode
    TriageNode --> Pipeline[TriagePipeline<br/>src/services/triage_pipeline.py]

    Pipeline --> ClinicalServices[Clinical Triage Services<br/>ToolOrchestrator, SemanticMapper,<br/>ChecklistValidator, RedFlagSafetyLayer,<br/>ProtocolTriageEngine, SummaryGenerator,<br/>NurseQueueService]

    ClinicalServices --> CatalogRegistry[CatalogToolRegistry<br/>discovers and executes 82 local tools]
    CatalogRegistry --> LocalToolCatalog[Local Tool Catalog<br/>src/tool/catalog<br/>82 tools: intake, mapping, validation,<br/>safety, knowledge, FHIR, HITL,<br/>audit, notification, analytics, orchestration]

    ToolsAPI --> MCPRegistry[MCPToolRegistry<br/>src/tool/registry.py]
    MCPRegistry -->|configured server URL| ExternalMCP[External MCP Servers<br/>guideline, terminology, FHIR, CDS, notification, audit]
    MCPRegistry -->|fallback/direct local catalog call| CatalogRegistry

    QueueAPI --> CaseStore[(InMemoryCaseStore<br/>TriageCase objects)]
    CaseAPI --> CaseStore
    ReviewAPI --> HumanReview[HumanReviewService]
    HumanReview --> CaseStore
    Pipeline -->|save case| CaseStore

    CatalogRegistry --> CatalogState[(CatalogStateStore<br/>conversations, FHIR mock data,<br/>queue, audit, outbox, metrics, traces)]

    Settings[Settings / .env<br/>CORS, model, Weaviate credentials,<br/>MCP URLs] --> FastAPIApp
    Settings --> ClinicalServices
    Settings --> MCPRegistry

    LLMAdapter[LLM Adapter<br/>services/llm.py - ChatOpenAI] -. extension point .-> Pipeline
    FullPipeline[Full Pipeline Runner<br/>src/pipeline/full_pipeline.py<br/>sample upload + sample query] --> DBUpdatePhase
    FullPipeline --> AnswerPhase

    Pipeline -->|best-effort case update| DBUpdatePhase[Database Update Phase<br/>src/pipeline/database_update_phase.py]
    DBUpdatePhase -->|user uploads documents<br/>or new cases are created| WeaviateCloud[(Weaviate Cloud<br/>database + vector store)]
    AnswerPhase[User Answer Phase<br/>src/pipeline/user_answer_phase.py] -->|query cases / knowledge| WeaviateCloud
```

## Components

### 1. Frontend / Demo UI

- **Technology:** Static HTML, CSS, JavaScript served by FastAPI `StaticFiles`.
- **Location:** `src/ui/static/index.html`, `src/ui/static/app.js`, `src/ui/static/styles.css`.
- **Purpose:** Provide one demo workspace for both patient intake and nurse review.
- **Key features:**
  - Patient chat form sends messages to `/api/v1/chat`.
  - Case panel shows status, priority, structured mapping, validation, red flags and summary.
  - Nurse panel reads `/api/v1/nurse/queue` and sends review actions to `/api/v1/cases/{case_id}/review`.
- **State management:** Browser-local JavaScript object holding `caseId`, `currentCase` and active tab. Server state is fetched through REST calls.

### 2. Backend API

- **Technology:** FastAPI + Pydantic.
- **Location:** `src/main.py`, `src/api/routes.py`.
- **Purpose:** Serve the UI, validate incoming requests, expose triage, case, nurse review and tool endpoints.
- **API design:** REST-style JSON endpoints under `/api/v1`.
- **Main endpoints:**
  - `GET /health`: service health.
  - `POST /api/v1/chat`: run patient message through LangGraph + triage pipeline.
  - `GET /api/v1/status`: agent readiness.
  - `GET /api/v1/tools`: list MCP-facing tool descriptors.
  - `POST /api/v1/tools/{tool_name}/call`: call configured MCP tool or local catalog tool.
  - `GET /api/v1/nurse/queue`: list cases visible to nurse dashboard.
  - `GET /api/v1/cases/{case_id}`: fetch one triage case.
  - `POST /api/v1/cases/{case_id}/review`: approve, edit, reject, escalate or ask for more information.
- **Authentication:** None implemented in current MVP.

### 3. AI Agent

- **Technology:** LangGraph `StateGraph`.
- **Location:** `src/agents/graph.py`, `src/agents/state.py`, `src/agents/nodes/triage_nodes.py`.
- **Agent type:** Controlled two-node workflow, not ReAct. Tool selection for intake is deterministic inside `ToolOrchestrator`.
- **State schema:** `AgentState` contains `query`, `case_id`, `triage_case`, `analysis`, `response`, `error` and `metadata`.
- **Nodes:**
  - `triage_pipeline`: validates input and calls `TriagePipeline.handle_patient_message`.
  - `respond`: returns `triage_case.patient_visible_response`.
- **Flow:**

```mermaid
graph LR
    START([START]) --> PipelineNode[triage_pipeline]
    PipelineNode --> ErrorDecision{state.error?}
    ErrorDecision -->|yes| END([END])
    ErrorDecision -->|no| RespondNode[patient_safe_response]
    RespondNode --> END
```

### 4. Triage Pipeline

- **Location:** `src/services/triage_pipeline.py`.
- **Purpose:** Convert free-text patient messages into structured triage case data and a safe patient-visible response.
- **Processing sequence:**
  1. Load existing case or create a new `TriageCase`.
  2. Append the patient message to conversation history.
  3. Run deterministic intake tools through `ToolOrchestrator`.
  4. Normalize message and map it to `StructuredSymptomData`.
  5. Validate required fields and confidence.
  6. Detect red flags, including high self-harm language from the tool orchestration result.
  7. Propose triage priority with `ProtocolTriageEngine`.
  8. Build handoff summary and nurse queue item.
  9. Derive case status and patient-safe response.
  10. Save the case in `InMemoryCaseStore`.

### 5. Tooling Layer

- **Local catalog:** `CatalogToolRegistry` discovers 82 local tools from `src/tool/catalog/**/tool_*.py`.
- **Runtime implementations:** `src/tool/catalog/implementations.py` contains the local handler logic for all catalog tools.
- **MCP-facing registry:** `MCPToolRegistry` exposes descriptors and can call external MCP servers if the relevant server URL is configured.
- **Safety policy:**
  - Tools are classified as `read_only`, `clinical_decision_support` or `side_effect`.
  - Side-effect tools require explicit approval before execution.
  - Tool calls are audited into `CatalogStateStore.audit_events`.

### 6. Data Layer

- **Current active storage:**
  - `InMemoryCaseStore`: process-local store for `TriageCase` objects used by the API and review flow.
  - `CatalogStateStore`: process-local state for tool conversations, mock FHIR resources, queue data, assignments, audit events, outbox, appointments, metrics, feedback and traces.
- **Weaviate Cloud pipeline layer:** `src/pipeline/`.
  - `full_pipeline.py`: runs the full sample flow: upload sample documents, update Weaviate Cloud, then query a sample question.
  - `database_update_phase.py`: updates Weaviate Cloud when users upload documents, and can also store newly created triage cases.
  - `user_answer_phase.py`: queries case and knowledge collections, then builds a user-facing answer.
  - `weaviate_cloud.py`: central Weaviate Cloud adapter.
- **Target persistent storage:** Weaviate Cloud.
  - Store triage cases, nurse queue state, review decisions, audit events and tool traces as persistent objects.
  - Store clinical knowledge/protocol documents as vectorized objects for semantic search/RAG.
  - Required future configuration: Weaviate cluster URL, API key and collection/schema definitions.
  - Current code still keeps the in-memory store for fast API reads, and now attempts best-effort case ingestion into Weaviate after local save.
  - `database_url` and `chroma_persist_dir` remain legacy settings; no repository layer writes to SQLite/PostgreSQL/Chroma.

### 7. External Integrations

- **LLM:** `src/services/llm.py` provides a `ChatOpenAI` adapter using `OPENAI_API_KEY`, `MODEL_NAME` and `LLM_TEMPERATURE`, but the current triage pipeline does not call it directly.
- **MCP servers:** Optional external servers can be configured for clinical guideline search, terminology lookup, FHIR, CDS Hooks, notification and audit.
- **Deployment:** Docker and Render are configured to run the FastAPI app with Uvicorn.

## Data Flow

```mermaid
sequenceDiagram
    participant User as Patient/User
    participant UI as Static Demo UI
    participant API as FastAPI /api/v1
    participant Agent as LangGraph Agent
    participant Pipeline as TriagePipeline
    participant Tools as ToolOrchestrator + Catalog Tools
    participant Store as InMemoryCaseStore
    participant Nurse as Nurse/Clinician

    User->>UI: Enter symptom message
    UI->>API: POST /chat
    API->>Agent: ainvoke query + optional case_id
    Agent->>Pipeline: handle_patient_message()
    Pipeline->>Tools: normalize, language, symptom, self-harm, violence, risk factors
    Tools-->>Pipeline: tool results
    Pipeline->>Pipeline: map symptoms, validate, detect red flags, propose priority
    Pipeline->>Store: save TriageCase
    Pipeline-->>Agent: TriageCase
    Agent-->>API: patient-safe response + analysis
    API-->>UI: ChatResponse
    UI->>API: GET /nurse/queue
    API->>Store: list cases
    Store-->>API: cases
    API-->>UI: queue
    Nurse->>UI: approve / edit / escalate / ask more
    UI->>API: POST /cases/:case_id/review
    API->>Store: update case status and response
    API-->>UI: NurseReviewResponse
```

## Deployment Architecture

```mermaid
graph LR
    Browser[Browser] -->|HTTP| App[FastAPI + Static UI<br/>Uvicorn on port 8000]

    subgraph Docker[Docker image]
        App
        DataDir[Data volume<br/>/app/data]
    end

    App --> DataDir
    Render[Render Web Service<br/>render.yaml] -->|starts| App
    Healthcheck[Healthcheck<br/>GET /health] --> App
```

## Security and Safety

- API keys and MCP server URLs are read from `.env` through Pydantic settings and should never be committed.
- Input validation is handled by Pydantic request/response schemas.
- CORS is configured from `cors_origins`.
- Patient-visible responses are deliberately conservative and always marked as requiring human approval.
- Side-effect catalog tools require explicit approval before execution.
- Clinical decision support tools are marked for human review.
- Tool calls are audited in process-local catalog state.
- No authentication/RBAC middleware is implemented yet; this is a required hardening step before production clinical use.

## Design Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Runtime shape | Single FastAPI app serving API and static UI | Simple MVP deployment; one Uvicorn process serves demo frontend and backend. |
| Agent framework | LangGraph controlled workflow | Makes pipeline state explicit while keeping safety-critical flow deterministic. |
| Tool orchestration | Deterministic `ToolOrchestrator` + local catalog | Avoids unsafe autonomous tool use; still provides extensible tool coverage. |
| Triage logic | Rule-backed semantic mapper + protocol engine | Testable MVP behavior without depending on LLM availability. |
| Human approval | Mandatory HITL before patient-visible clinical action | Reduces risk for medical triage decisions. |
| Storage | In-memory now; Weaviate Cloud target | Fast for demo/testing today; production persistence should move cases, queue/audit state and vectorized knowledge into Weaviate Cloud. |
| External tools | Optional MCP server URLs with local catalog fallback | Allows integration with FHIR/CDS/notification/audit systems without blocking MVP. |
| LLM | Adapter exists but is not active in current pipeline | Keeps path open for LLM-based mapping/summarization while current behavior remains deterministic. |

## Framework Update (2026-08-07) — Feature-spec REST API, Quality Guard, HITL mở rộng, GNN Advisory #TODO

Mọi mô tả ở phía trên (LangGraph Agent, `/chat`, `/cases/{id}/review`) là **luồng demo Gen1** ban đầu.
Song song đó, repo đã phát triển một luồng REST API bám sát đặc tả Feature #1–#5 (**Gen2**, đang là
nguồn sự thật cho sản phẩm) nhưng chưa được tài liệu hoá ở đây. Cập nhật này bổ sung phần đó và ghi
nhận rõ khoảng trùng lặp giữa hai luồng.

### Gen1 vs Gen2 — khoảng trùng lặp cần dọn dẹp

| | Gen1 (demo gốc, `src/api/routes.py`) | Gen2 (đúng đặc tả, `src/api/routers/*.py`) |
|---|---|---|
| Tạo/tiếp tục case | `POST /chat` (không auth, không ownership check) | `POST /cases`, `POST /cases/{id}/responses` (`case_flow.py`, có auth + ownership) |
| Xem case | `GET /cases/{case_id}` trả nguyên `TriageCase` (lộ dữ liệu nội bộ cho bất kỳ ai) | `GET /cases/{id}/result` (`result.py`) — chỉ trả nội dung xử trí khi `approval_status = approved`, đúng ràng buộc HITL |
| Duyệt case | `POST /cases/{id}/review` (`hitl_review.py`, action approve/edit/reject/ask_more, sửa thẳng `TriageCase.status`) | `POST /cases/{id}/approve\|override\|escalate\|reject\|ask_more` (`case_approval.py`, ghi `approval_store`/`audit_log` — khớp đặc tả #2) |
| Hàng đợi | `GET /nurse/queue` trả toàn bộ case, không lọc theo priority/thời gian chờ | `GET /queue` (`case_approval.list_queue`) — sắp theo priority rồi thời gian chờ, đúng đặc tả #2 |

**Khuyến nghị:** Gen1 (`routes.py`, `hitl_review.py`) nên được đánh dấu deprecated và gỡ khỏi router
chính trong một PR riêng — nó vi phạm nguyên tắc "patient không thấy dữ liệu nội bộ" (DESIGN.md) vì
không kiểm tra ownership và trả thẳng `TriageCase` đầy đủ. Chưa xoá trong lần cập nhật này để tránh
phá vỡ các chỗ đang tham chiếu nó ngoài phạm vi thay đổi hiện tại; chỉ ghi nhận ở đây làm việc cần làm.

### Checklist đa bệnh — bổ sung nhóm `headache`

`REQUIRED_FIELDS_BY_SYMPTOM_GROUP` (`src/config.py`) trước đây có 6 nhóm (`chest_pain`, `breathing`,
`abdominal`, `fever`, `bleeding`, `neurologic`) nhưng **không có nhóm nào khớp** với
`data/triage_daudau.csv` (đau đầu). Đã bổ sung nhóm `headache` (`onset`, `headache_severity`,
`thunderclap_onset`) cùng follow-up question, red-flag rule `thunderclap_headache` (nghi xuất huyết
não) và protocol rule `VMED-HD-001`/`VMED-HD-002`, theo đúng pattern các nhóm sẵn có.

### Quality Guard — suppress hàng đợi khi hội thoại "vớ vẩn", KHÔNG BAO GIỜ chặn red-flag

- `src/services/quality_guard.py` (mới): heuristic rule-based (không LLM), gán
  `TriageCase.quality_flag` (`normal`/`low_quality`) mỗi turn dựa trên độ dài tin nhắn, lặp lại y hệt
  nhiều lần liên tiếp, hoặc số vòng hỏi lại vượt ngưỡng mà vẫn chưa đủ checklist.
- Được gọi trong `case_flow._finalize_turn` — chỉ gắn nhãn, **không** tự đổi `CaseStatus`.
- Quyết định suppress khỏi hàng đợi nằm **duy nhất** ở `case_approval.list_queue()`: bỏ qua case khi
  `quality_flag == low_quality` **và** `not triage_case.red_flags`. Vì `RedFlagSafetyLayer` đã chạy
  vô điều kiện mỗi turn từ trước (xác nhận trong `triage_pipeline.py`, không cần sửa), red-flag luôn
  thắng quality guard theo đúng thiết kế đã thống nhất.

### HITL mở rộng — reject/ask_more cộng thêm vào Gen2 (approve/override/escalate)

Đặc tả #2 gốc chỉ định nghĩa 3 hành động (approve/override/escalate — đã implement đủ trong
`case_approval.py`). Bổ sung 2 hành động mới cho đúng luồng nurse feedback đã thống nhất:

- `POST /cases/{id}/reject` — bắt buộc `reason_code` (`RejectReasonCode`:
  `already_handled_offline` / `ai_incorrect` / `other`). Case chuyển `CaseStatus.WITHDRAWN`. Tách
  riêng khỏi `REJECTED` (giá trị cũ, thuộc Gen1) để không lẫn ngữ nghĩa.
- `POST /cases/{id}/ask_more` — điều dưỡng chỉ định câu hỏi trực tiếp, case chuyển
  `CaseStatus.NEEDS_MORE_INFO`, tự động rời khỏi hàng đợi; khi bệnh nhân trả lời lượt tiếp theo,
  `case_flow._finalize_turn` đưa case quay lại hàng đợi bình thường.
- Cả hai đều ghi vào `approval_store.AuditLogEntry` (đã bổ sung field `reason`) — dùng cho bước
  calibration/feedback scoring sau này: **chỉ** audit entry có `action=reject` với `reason` bắt đầu
  bằng `ai_incorrect` mới được tính vào thống kê độ chính xác AI–điều dưỡng; `already_handled_offline`
  và `other` không phải tín hiệu AI đúng/sai nên bị loại khỏi phép đo ngay từ nguồn.

### GNN Advisory Signal — #TODO, tách riêng khỏi luồng quyết định chính

`src/services/graph_triage_advisor.py` (mới) là điểm neo interface cho phần dual-embedding + GNN đã
thảo luận (checklist graph + text summary → similarity search case tương tự). Module này:

- **Chưa có logic thật** (`NotImplementedError`), **không được gọi ở bất kỳ đâu** trong
  `TriagePipeline`/`case_flow`/`case_approval` hiện tại.
- Được thiết kế để CHỈ trả về evidence tham khảo (case tương tự + field đóng góp), không bao giờ được
  gán trực tiếp vào `TriageProposal.priority` — `ProtocolTriageEngine`/`RedFlagSafetyLayer` tiếp tục là
  nguồn quyết định priority duy nhất.
- Toàn bộ checklist việc cần làm (schema graph, dual embedding, ingest 609 dòng
  `data/triage_*.csv` đã dedupe, explainability trước khi bật hiển thị cho nurse, calibration offline
  loại trừ lý do reject không liên quan accuracy) nằm trong docstring của file — giao cho người phụ
  trách phần GNN, độc lập với luồng triage chính.
