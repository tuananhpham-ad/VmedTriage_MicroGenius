# Tool Catalog

## Trạng thái triển khai

Toàn bộ 82 tool trong catalog đã có entry point `execute(arguments, context)` và chạy qua
`CatalogToolRegistry`. Implementation dùng local adapter để development/test có thể chạy độc lập.
Các thao tác với hệ thống ngoài (FHIR, SMS, email, paging) được ghi vào local state/outbox; giá trị
`sent=false` hoặc `delivered=false` thể hiện provider bên ngoài chưa xác nhận gửi thành công.

Các thành phần framework:

- `framework.py`: execution context và output model chuẩn.
- `registry.py`: tự discover 82 tool, kiểm tra policy, validate output và audit call.
- `implementations.py`: implementation local theo 12 nhóm A-L.
- `state.py`: state backend in-memory có thể thay bằng database/repository.
- `orchestrator.py`: lập kế hoạch và điều hướng user query tới chuỗi tool phù hợp.

Ví dụ gọi một tool read-only:

```python
from src.tool.catalog.registry import catalog_tool_registry

result = await catalog_tool_registry.call(
    "snomed_concept_lookup",
    {"term": "đau ngực", "language": "vi"},
)
```

Tool có side effect bắt buộc truyền approval trong execution context:

```python
from src.tool.catalog.framework import ToolExecutionContext

context = ToolExecutionContext(
    case_id="case-123",
    actor_id="nurse-01",
    actor_role="nurse",
    approved=True,
)
result = await catalog_tool_registry.call(
    "fhir_task_create",
    {"patient_id": "patient-01", "task_payload": {"status": "requested"}},
    context=context,
)
```

Pipeline intake hiện gọi `ToolOrchestrator.run_patient_query()` trước semantic validation. Plan mặc
định gồm normalize, language detection, symptom extraction, self-harm detection, violence detection
và risk-factor extraction. Tất cả call đều tạo audit event.

Mỗi file `src/tool/catalog/<folder_con>/tool_<id>_<name>.py` chứa metadata và một entry point
thực thi độc lập. Registry tự động đăng ký các module này khi ứng dụng khởi động.

## Output Format Chuẩn

Mỗi MCP/local tool trả về format thống nhất:

```json
{
  "tool_id": 1,
  "tool_name": "patient_message_normalizer",
  "ok": true,
  "data": {},
  "error": null,
  "metadata": {
    "source": "local|mcp",
    "confidence": 1.0,
    "requires_human_review": false,
    "patient_visible": false
  }
}
```

Quy ước:
- `tool_id`: id số theo catalog.
- `tool_name`: tên tool ổn định.
- `ok`: `true` nếu tool chạy thành công.
- `data`: output chính, schema tùy từng tool.
- `error`: chuỗi lỗi nếu `ok=false`, ngược lại là `null`.
- `metadata.source`: `local` nếu chạy trong codebase, `mcp` nếu gọi MCP server.
- `metadata.confidence`: confidence nếu tool có tính xác suất; nếu không có thì dùng `1.0`.
- `metadata.requires_human_review`: `true` nếu kết quả clinical/side-effect cần human review.
- `metadata.patient_visible`: `true` chỉ khi output được phép đi thẳng tới bệnh nhân. Với bài toán này mặc định nên là `false`.

## A. Intake & Conversation

| ID | Tool | Input | Output | Action |
|---:|------|-------|--------|--------|
| 1 | `patient_message_normalizer` | Raw user query. | `normalized_message` | Chuẩn hóa lỗi gõ, không dấu, slang, whitespace. |
| 2 | `language_detector` | Text. | `language`, `confidence` | Detect VI/EN/mixed để chọn prompt/tool phù hợp. |
| 3 | `medical_translation_tool` | Text, source language, target language. | `translated_text`, `preserved_terms` | Dịch clinical text nhưng giữ ổn định thuật ngữ. |
| 4 | `conversation_memory_read` | `case_id` | `conversation` | Đọc lịch sử hội thoại của case. |
| 5 | `conversation_memory_write` | `case_id`, `role`, `content` | `stored`, `message_id` | Ghi lượt hội thoại vào case memory. |
| 6 | `patient_profile_read` | `patient_id` | `profile` | Đọc context như tuổi, giới, thai kỳ, nguy cơ. |
| 7 | `consent_checker` | `case_id`, `patient_id`, `scope` | `has_consent`, `missing_scope` | Kiểm tra consent trước khi xử lý/gọi tool ngoài. |

## B. Semantic Mapping

| ID | Tool | Input | Output | Action |
|---:|------|-------|--------|--------|
| 8 | `symptom_extraction_tool` | Patient message, optional conversation. | `structured_symptoms` | Extract chief complaint, onset, severity, associated symptoms. |
| 9 | `snomed_concept_lookup` | Clinical term, language, system. | `concepts` | Chuẩn hóa triệu chứng sang SNOMED CT. |
| 10 | `icd10_lookup` | Clinical term, language. | `codes` | Map ICD-10 cho reporting sau review. |
| 11 | `loinc_lookup` | Observation/lab term. | `codes` | Chuẩn hóa observation/lab sang LOINC. |
| 12 | `rxnorm_lookup` | Medication name. | `concepts` | Chuẩn hóa tên thuốc sang RxNorm. |
| 13 | `allergy_extraction_tool` | Text/note. | `allergies` | Extract allergy và reaction. |
| 14 | `medication_extraction_tool` | Text/note. | `medications` | Extract thuốc, liều, thời điểm dùng. |
| 15 | `risk_factor_extraction_tool` | Text/profile/note. | `risk_factors` | Extract nguy cơ: tuổi cao, thai kỳ, bệnh nền. |

## C. Validation & Follow-up

| ID | Tool | Input | Output | Action |
|---:|------|-------|--------|--------|
| 16 | `required_checklist_validator` | `structured_symptoms` | `is_valid`, `missing_fields` | Check field bắt buộc theo symptom group. |
| 17 | `contradiction_detector` | Structured symptoms, prior context. | `contradictions` | Tìm mâu thuẫn hoặc giá trị không hợp lệ. |
| 18 | `confidence_calibrator` | Structured symptoms, evidence. | `confidence`, `low_confidence_fields` | Calibrate confidence để quyết định hỏi thêm/review. |
| 19 | `follow_up_question_generator` | Missing fields, symptom group. | `questions` | Sinh câu hỏi follow-up an toàn. |
| 20 | `question_prioritizer` | Candidate questions, case context. | `prioritized_questions` | Chọn câu hỏi quan trọng nhất trước. |
| 21 | `health_literacy_rewriter` | Draft text, language, reading level. | `rewritten_text` | Viết lại dễ hiểu cho bệnh nhân. |

## D. Safety / Red Flag

| ID | Tool | Input | Output | Action |
|---:|------|-------|--------|--------|
| 22 | `red_flag_detector` | Structured symptoms. | `red_flags` | Detect dấu hiệu nguy hiểm để route ưu tiên. |
| 23 | `emergency_escalation_classifier` | Symptoms, red flags, risk factors. | `priority`, `reason` | Classify Emergency/Urgent/Routine/Manual review. |
| 24 | `self_harm_risk_detector` | Patient message. | `risk_detected`, `risk_level`, `evidence` | Detect nguy cơ tự hại/crisis. |
| 25 | `abuse_or_violence_detector` | Patient message/context. | `risk_detected`, `risk_type`, `evidence` | Detect bạo lực/ngược đãi/coercion. |
| 26 | `pediatric_risk_detector` | Age, structured symptoms. | `pediatric_risks` | Áp rule/threshold riêng cho trẻ em. |
| 27 | `pregnancy_risk_detector` | Pregnancy status, symptoms. | `pregnancy_risks` | Áp risk rule riêng cho thai kỳ. |
| 28 | `elderly_risk_detector` | Age, symptoms, profile. | `elderly_risks` | Áp risk rule riêng cho người cao tuổi. |

## E. Clinical Knowledge / RAG

| ID | Tool | Input | Output | Action |
|---:|------|-------|--------|--------|
| 29 | `clinical_guideline_search` | Symptom group, query, red flags. | `matches` | Search guideline/protocol đã duyệt. |
| 30 | `local_protocol_retriever` | Symptom group, site id. | `protocols` | Retrieve protocol nội bộ bệnh viện/phòng khám. |
| 31 | `triage_pathway_search` | Symptom group, structured symptoms. | `pathways` | Tìm pathway triage theo symptom group. |
| 32 | `drug_interaction_checker` | Medication list. | `interactions` | Check tương tác thuốc cho clinician-facing review. |
| 33 | `contraindication_checker` | Candidate action, patient context. | `contraindications` | Check chống chỉ định trước khi nurse approve. |
| 34 | `clinical_calculator_tool` | Calculator name, values. | `score`, `interpretation` | Tính score y khoa khi đủ input. |
| 35 | `medical_knowledge_summarizer` | Documents, case context. | `summary`, `citations` | Tóm tắt guideline cho nurse. |

## F. Triage Decision Support

| ID | Tool | Input | Output | Action |
|---:|------|-------|--------|--------|
| 36 | `protocol_triage_engine` | Symptoms, validation, red flags. | `triage_proposal` | Match protocol để tạo proposal cần review. |
| 37 | `cds_hooks_triage_advice` | Hook, context, prefetch. | `cards` | Gọi CDS Hooks để cross-check proposal. |
| 38 | `priority_score_calculator` | Case context. | `priority_score`, `priority_bucket` | Rank case trong nurse queue. |
| 39 | `manual_review_decider` | Proposal, tool results, policy. | `requires_review`, `reason` | Enforce HITL trước clinical output. |
| 40 | `care_navigation_router` | Case context and proposal. | `route`, `reason` | Route ER/urgent/routine/ask-more theo policy. |

## G. EHR / FHIR

| ID | Tool | Input | Output | Action |
|---:|------|-------|--------|--------|
| 41 | `fhir_patient_context_read` | Patient id, resources. | `bundle`, `resource_count`, `redacted` | Đọc limited EHR context. |
| 42 | `fhir_observation_read` | Patient id, codes, date range. | `observations` | Đọc vital/lab gần nhất. |
| 43 | `fhir_condition_read` | Patient id, clinical status. | `conditions` | Đọc bệnh nền/condition. |
| 44 | `fhir_medication_read` | Patient id, status. | `medications` | Đọc thuốc hiện tại. |
| 45 | `fhir_allergy_read` | Patient id. | `allergies` | Đọc allergy/intolerance. |
| 46 | `fhir_encounter_create` | Patient id, case id, encounter payload. | `encounter_id`, `created` | Tạo encounter sau khi đủ quyền/policy. |
| 47 | `fhir_task_create` | Patient id, case id, task payload. | `task_id`, `created` | Tạo task cho nurse/clinician. |
| 48 | `fhir_document_reference_write` | Patient id, case id, document. | `document_reference_id`, `stored` | Ghi approved handoff vào EHR. |

## H. Nurse Workflow / HITL

| ID | Tool | Input | Output | Action |
|---:|------|-------|--------|--------|
| 49 | `nurse_queue_create_item` | Case id, summary, proposal. | `queue_item` | Tạo item cho nurse review. |
| 50 | `nurse_queue_read` | Queue filters. | `items` | Đọc danh sách case chờ review. |
| 51 | `nurse_case_assign` | Case id, nurse id. | `assigned`, `assignee` | Assign case cho nurse. |
| 52 | `nurse_priority_alert` | Case id, priority, red flags, message. | `alert_id`, `delivered`, `channel` | Alert staff khi red flag. |
| 53 | `human_review_submit` | Case id, action, response, notes. | `case_id`, `status`, `patient_visible_response` | Apply approve/edit/reject/escalate/ask_more. |
| 54 | `approved_response_sender` | Case id, approved response, channel. | `sent`, `message_id` | Gửi response đã được nurse duyệt. |
| 55 | `handoff_summary_generator` | Case context. | `summary` | Tạo summary nurse-facing. |
| 56 | `case_status_updater` | Case id, status, reason. | `case_id`, `status` | Update workflow state. |

## I. Audit / Compliance / Governance

| ID | Tool | Input | Output | Action |
|---:|------|-------|--------|--------|
| 57 | `triage_audit_log_write` | Case id, event type, actor role, payload. | `event_id`, `stored` | Ghi audit event bất biến. |
| 58 | `tool_call_audit_logger` | Tool name, args, result, policy. | `event_id`, `stored` | Audit mọi MCP tool call. |
| 59 | `phi_redactor` | Text, policy. | `redacted_text`, `redactions` | Redact PHI trước external call/log. |
| 60 | `policy_guardrail_checker` | Draft output, case context. | `allowed`, `violations` | Chặn output vi phạm medical safety policy. |
| 61 | `patient_visible_safety_filter` | Response, case context, approval state. | `safe_response`, `blocked`, `issues` | Filter text trước khi gửi bệnh nhân. |
| 62 | `data_retention_policy_checker` | Data type, purpose, policy context. | `allowed`, `retention_period`, `reason` | Check policy lưu trữ data. |
| 63 | `access_control_checker` | Actor, resource, action. | `allowed`, `reason` | Enforce role-based access. |
| 64 | `consent_audit_logger` | Case id, patient id, consent event. | `event_id`, `stored` | Audit consent grant/refusal/revocation. |

## J. Notification

| ID | Tool | Input | Output | Action |
|---:|------|-------|--------|--------|
| 65 | `sms_notification_tool` | Recipient, message, case id. | `sent`, `message_id` | Gửi SMS đã approved. |
| 66 | `email_notification_tool` | Recipient, subject, body, case id. | `sent`, `message_id` | Gửi email workflow. |
| 67 | `push_notification_tool` | Recipient, message, case id. | `sent`, `notification_id` | Push notification trong app/dashboard. |
| 68 | `on_call_paging_tool` | Case id, priority, message, team. | `page_id`, `delivered` | Page team trực khi escalation. |
| 69 | `appointment_scheduler` | Patient id, case id, slot, reason. | `appointment_id`, `scheduled` | Đặt lịch sau confirmation/policy approval. |

## K. Analytics / Evaluation

| ID | Tool | Input | Output | Action |
|---:|------|-------|--------|--------|
| 70 | `case_metrics_logger` | Case id, metrics. | `stored`, `metric_event_id` | Log metrics vận hành. |
| 71 | `triage_quality_evaluator` | Cases, expected labels. | `scores` | Đánh giá quality so với gold/nurse outcomes. |
| 72 | `rag_grounding_evaluator` | Output, evidence. | `grounded`, `issues` | Check grounding của guideline/RAG. |
| 73 | `safety_event_detector` | Case trace. | `safety_events` | Detect safety incident/near miss. |
| 74 | `feedback_collector` | Case id, actor role, feedback. | `feedback_id`, `stored` | Thu feedback từ nurse/patient. |
| 75 | `drift_monitor` | Time window, metrics. | `drift_detected`, `signals` | Theo dõi drift mapping/protocol/review. |

## L. Orchestrator Internal

| ID | Tool | Input | Output | Action |
|---:|------|-------|--------|--------|
| 76 | `tool_registry_list` | Filters. | `tools` | Liệt kê tool khả dụng. |
| 77 | `tool_capability_matcher` | Intent, case context, available tools. | `candidate_tools` | Chọn tool phù hợp cho next step. |
| 78 | `tool_policy_enforcer` | Tool descriptor, args, case context. | `allowed`, `reason` | Enforce policy trước tool call. |
| 79 | `tool_argument_builder` | Tool descriptor, agent state, case context. | `arguments`, `missing_inputs` | Build args đúng schema. |
| 80 | `tool_result_validator` | Tool descriptor, raw result. | `valid`, `normalized_result`, `errors` | Validate output tool trước khi dùng. |
| 81 | `fallback_strategy_selector` | Failed tool, error, case context. | `fallback`, `reason` | Chọn fallback khi MCP fail/unconfigured. |
| 82 | `orchestration_trace_writer` | Case id, trace event. | `trace_id`, `stored` | Ghi trace orchestrator để debug/demo. |

## Policy Mặc Định Khi Implement

- Tool read-only có thể chạy trước HITL nếu không lộ PHI quá mức.
- Tool clinical decision support phải `patient_visible=false`.
- Tool side-effect như write EHR, send notification, schedule appointment phải có policy/confirmation rõ.
- Patient-facing response phải qua `patient_visible_safety_filter` và HITL nếu có nội dung clinical.
- Mọi tool call quan trọng nên đi qua `tool_call_audit_logger`.
