"""DeepSeek JSON extraction with validation, retry, and no label leakage."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

from openai import APIStatusError, OpenAI

from src.config import get_settings
from src.graph_triage.graph_schema import ClinicalGraph, validate_provenance

FATAL_STATUS_CODES = {401: "the API key was rejected", 402: "the DeepSeek account has insufficient balance", 403: "the API key is not allowed to use this model"}


class FatalExtractionError(RuntimeError):
    """An account-level failure that every remaining row would hit too."""


SYSTEM_PROMPT = r"""You are a clinical-information-extraction component, not a clinician.
Return one JSON object only; the output must contain the word "json" and follow the patient_graph_v1 contract below.

Hard safety rules:
1. Extract only facts explicitly stated in the Vietnamese report. Never infer diagnosis, cause, urgency, triage label, future outcome, or a missing negative fact.
2. UNKNOWN is represented by omitting a node/field. Create status="absent" only for an explicit negation.
3. Every observation and every edge needs provenance.source_span copied verbatim from the report. surface_form must be a verbatim substring of that provenance span.
3a. A source_span is one uninterrupted stretch of the report: everything between its first and last character is copied too. Never delete words from the middle of it, and never write "..." — an ellipsis makes the string a non-match and fails the whole extraction.
3b. Vietnamese reports pack several facts into one coordinated clause, most often as "không A hay B", "không A, không B" or "A và B <mô tả>". Handle every such clause mechanically: give each fact its own node, put the ENTIRE clause in source_span for all of them, and set each surface_form to the contiguous fragment naming that one fact. The moment you catch yourself writing a negation that reads well but was assembled from separate parts of the sentence, you have broken the contract. Worked examples:
- "không khó thở hay buồn nôn nhiều" -> two absent nodes, both source_span "không khó thở hay buồn nôn nhiều", surface_form "khó thở" and "buồn nôn nhiều". NOT "không buồn nôn nhiều".
- "không mủ hay đau tinh hoàn" -> surface_form "mủ" and "đau tinh hoàn". NOT "không đau tinh hoàn".
- "cũng không đau lan xuống tay trái hay lên hàm" -> surface_form "tay trái" and "hàm". NOT "không đau lan lên hàm".
- "phù mặt và chân rõ" -> surface_form "mặt" and "chân". "ăn uống và đi vệ sinh bình thường" -> surface_form "ăn uống" and "đi vệ sinh".
The status field, not the surface_form, is what records the negation, so a surface_form without the word "không" is correct and expected.
4. A Condition is only a patient-reported established history (for example "tôi bị hen"); never turn symptoms or a suspected illness into a Condition.
5. Nodes are event instances: create separate nodes for separate episodes/times/statuses of the same concept. Do not merge them blindly.
6. The triage target is the implicit node named "patient". Facts about a reporter/other person must set experiencer="reporter" or "other" and must not receive a patient HAS edge.

JSON contract (omit every unknown optional field; never use null):
{
  "schema_version":"patient_graph_v1",
  "patient":{"age":72,"report_source":"family_member","provenance":{"source_span":"Bố tôi 72 tuổi","source_turn":1,"source_role":"family_member"}},
  "nodes":[
    {"id":"chest_pain_1","type":"symptom","concept":"chest_pain","canonical_name":"Chest pain","experiencer":"target_patient","observations":[{"surface_form":"đau tức giữa ngực","status":"present","certainty":"certain","onset_text":"từ sáng","details":{"character":"pressure"},"provenance":{"source_span":"đau tức giữa ngực từ sáng","source_turn":1,"source_role":"family_member"}}]},
    {"id":"chest_1","type":"body_location","concept":"chest","canonical_name":"Chest","experiencer":"target_patient","observations":[{"surface_form":"giữa ngực","status":"present","provenance":{"source_span":"đau tức giữa ngực từ sáng","source_turn":1,"source_role":"family_member"}}]}
  ],
  "edges":[
    {"source":"patient","relation":"has_symptom","target":"chest_pain_1","provenance":{"source_span":"đau tức giữa ngực từ sáng","source_turn":1,"source_role":"family_member"}},
    {"source":"chest_pain_1","relation":"located_at","target":"chest_1","provenance":{"source_span":"đau tức giữa ngực từ sáng","source_turn":1,"source_role":"family_member"}}
  ]
}

The schema is closed: any key not listed below is rejected and the whole extraction fails. Never invent a key, and never use a value outside an enumerated set. When a stated fact has no place in the schema, express it as its own node (for example a stated weight or obesity becomes a risk_factor node) or drop it.

Allowed node types: symptom, finding, body_location, condition, risk_factor, context.
Allowed relations, usable only in "edges": has_symptom, has_finding, has_condition, has_risk_factor, has_context, located_at, radiates_to, triggered_by, worsened_by, relieved_by, associated_with. triggered_by, worsened_by and relieved_by are never observation fields, and their trigger must exist as its own node.
For each target_patient symptom/finding/condition/risk_factor/context add exactly one compatible patient HAS edge; use source exactly "patient". A body_location must have located_at or radiates_to from a symptom. associated_with is only stated co-occurrence, not mere adjacency in the report.
A context node that triggers, worsens or relieves a fact about the triage target still has experiencer="target_patient" and still needs its own has_context edge from patient, in addition to the triggered_by/worsened_by/relieved_by edge. Both edges are required together; removing either one is invalid.
Structural relations accept these source and target types only, and each side must be a declared node id:
- located_at, radiates_to: symptom|finding|condition -> body_location
- triggered_by, worsened_by, relieved_by: symptom|finding -> context|symptom|finding. The trigger is usually a context node, but one stated fact may trigger another: "đang sốt cao thì lên cơn co giật" gives seizure triggered_by the fever symptom node.
- associated_with: symptom|finding -> symptom|finding
A body_location, risk_factor or context node is never the source of any of these. A trigger such as scratching or water contact is a context node, so a rash worsened by scratching needs that scratching context node to exist and to carry its own has_context edge from patient.

A node object accepts exactly: id, type, concept, canonical_name, experiencer, observations. id and concept must match ^[a-z][a-z0-9_]*$.
A provenance object accepts exactly: source_span, source_turn (integer >= 1), source_role. source_role and patient.report_source must be exactly one of patient, family_member, unknown — "self", "patient_self", "reporter" and similar are invalid.
The patient object accepts exactly: age, report_source, provenance.

An observation object accepts exactly these keys and no others: surface_form, status (present|absent|uncertain), certainty (certain|probable|possible|uncertain), onset_type (sudden|gradual|unknown), onset_text, onset_hours_ago, duration_value, duration_unit (minutes|hours|days|weeks|months|years), duration_precision (exact|approximate), progression (worsening|stable|improving|fluctuating|unknown), frequency, pattern, time_pattern, functional_impacts, subjective_severity (0-10), details, provenance. surface_form, status and provenance are required. duration_value and duration_unit must appear together. functional_impacts is a list from walking_limitation, speech_limitation, sleep_disruption, unable_to_eat, unable_to_drink, unable_to_perform_daily_activity. subjective_severity must be a bare JSON number from 0 to 10 - write 7, never "7/10", "7 trên 10", or any string.

The details object accepts exactly these keys and no others: character (text), work_of_breathing (text), oral_intake (text), vomiting_frequency (text), stool_change (text), estimated_amount (text), movement_related, exertional, pleuritic, positional, at_rest, speech_limitation, blood_present, ongoing, clots, associated_syncope, focal_deficit, speech_change, consciousness_change, seizure_activity (all booleans). Include a key only when the report states it explicitly. Omit the whole details object if it is empty.

Keep the output compact: no markdown fence, no comments, no repetition of a fact that is already one observation.

Example of explicit negative evidence: "Tôi đau ngực nhưng không sốt" contains chest_pain present AND fever absent, each with its own source span and a patient HAS edge. It does not contain any node for symptoms never mentioned. Return {"schema_version":"patient_graph_v1","patient":{},"nodes":[],"edges":[]} when no clinical evidence is stated."""


MAX_OUTPUT_TOKENS = 8000

REPAIR_PROMPT = """Your JSON was rejected by the patient_graph_v1 validator. Every problem reported so far in this report:

{errors}

Return the corrected full JSON object only. Fix what the errors name without reintroducing an earlier one: drop keys and values the schema does not allow, keep each provenance span verbatim from the report, and never add a fact the report does not state. If you cannot locate one uninterrupted span of the report that supports a fact, drop that node or edge entirely; an incomplete graph is acceptable, an approximated span is not."""


@dataclass
class DeepSeekExtractor:
    model: str = "deepseek-v4-flash"
    max_tokens: int = 4000
    retries: int = 4

    def __post_init__(self) -> None:
        # Credential đọc qua `get_settings()` chứ không phải `os.environ` trực tiếp: P-141 nạp `.env`
        # bằng pydantic-settings, module này chạy cả trong app lẫn CLI nên phải dùng chung một nguồn.
        settings = get_settings()
        if not settings.deepseek_api_key:
            raise RuntimeError("Set DEEPSEEK_API_KEY before running graph extraction.")
        self.client = OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url)

    def extract(self, patient_text: str) -> ClinicalGraph:
        errors: list[str] = []
        messages: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Patient report:\n{patient_text}"},
        ]
        max_tokens = self.max_tokens
        for attempt in range(self.retries):
            content = None
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0,
                    max_tokens=max_tokens,
                    extra_body={"thinking": {"type": "disabled"}},
                )
                content = response.choices[0].message.content
                if response.choices[0].finish_reason == "length":
                    content = None  # Truncated JSON is useless as a repair starting point.
                    truncated_budget, max_tokens = max_tokens, min(max_tokens * 2, MAX_OUTPUT_TOKENS)
                    raise ValueError(f"DeepSeek output hit max_tokens={truncated_budget}; the JSON is truncated.")
                if not content:
                    raise ValueError("DeepSeek returned empty JSON content.")
                graph = ClinicalGraph.model_validate(json.loads(content))
                validate_provenance(graph, patient_text)
                return graph
            except APIStatusError as error:
                # Hết tiền hoặc sai key thì mọi ca còn lại cũng trượt y hệt - dừng hẳn, đừng đốt retry.
                if reason := FATAL_STATUS_CODES.get(error.status_code):
                    raise FatalExtractionError(f"DeepSeek returned HTTP {error.status_code}: {reason}. Retrying cannot help.") from error
                errors.append(f"attempt {attempt + 1}: {error}")
                if attempt + 1 >= self.retries:
                    break
                time.sleep(2 ** attempt)
            except Exception as error:  # API và schema error đều retry.
                errors.append(f"attempt {attempt + 1}: {error}")
                if attempt + 1 >= self.retries:
                    break
                # Gửi lại y nguyên ở temperature=0 sẽ nhận lại y nguyên câu trả lời hỏng - các lần thử
                # đều trượt cùng một lỗi, tốn tiền nhiều lần. Đưa chính lỗi validate ngược lại để model
                # sửa. Chỉ thêm mô tả lỗi, KHÔNG gợi ý nội dung lâm sàng nào.
                if content:
                    messages = messages[:2] + [
                        {"role": "assistant", "content": content},
                        {"role": "user", "content": REPAIR_PROMPT.format(errors="\n".join(f"- {message}" for message in errors))},
                    ]
                time.sleep(2 ** attempt)
        raise RuntimeError("Extraction failed after retries: " + " | ".join(errors))
