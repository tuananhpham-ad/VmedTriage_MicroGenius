from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from math import isfinite
from typing import Any
from uuid import uuid4

from src.config import FOLLOW_UP_QUESTIONS, TRIAGE_PROTOCOL_RULES
from src.models.schemas import (
    RedFlagFinding,
    StructuredSymptomData,
    ValidationResult,
)
from src.services.checklist_validator import ChecklistValidator
from src.services.red_flag import RedFlagSafetyLayer
from src.services.semantic_mapper import RuleBackedSemanticMapper
from src.services.triage_engine import ProtocolTriageEngine
from src.tool.catalog.framework import ToolExecutionContext
from src.tool.catalog.state import CatalogStateStore, catalog_state

TERMINOLOGY: dict[str, dict[str, tuple[str, str]]] = {
    "snomed": {
        "chest pain": ("29857009", "Chest pain"),
        "đau ngực": ("29857009", "Chest pain"),
        "shortness of breath": ("267036007", "Dyspnea"),
        "khó thở": ("267036007", "Dyspnea"),
        "bleeding": ("131148009", "Bleeding"),
    },
    "icd10": {
        "chest pain": ("R07.9", "Chest pain, unspecified"),
        "đau ngực": ("R07.9", "Chest pain, unspecified"),
        "shortness of breath": ("R06.02", "Shortness of breath"),
        "khó thở": ("R06.02", "Shortness of breath"),
    },
    "loinc": {
        "heart rate": ("8867-4", "Heart rate"),
        "blood pressure": ("85354-9", "Blood pressure panel"),
        "oxygen saturation": ("2708-6", "Oxygen saturation"),
    },
    "rxnorm": {
        "aspirin": ("1191", "Aspirin"),
        "paracetamol": ("161", "Acetaminophen"),
        "acetaminophen": ("161", "Acetaminophen"),
        "ibuprofen": ("5640", "Ibuprofen"),
    },
}

DRUG_INTERACTIONS = {
    frozenset(("warfarin", "aspirin")): ("high", "Increased bleeding risk"),
    frozenset(("warfarin", "ibuprofen")): ("high", "Increased bleeding risk"),
    frozenset(("sildenafil", "nitroglycerin")): ("critical", "Severe hypotension risk"),
}

RISK_WORDS = {
    "pregnancy": ("mang thai", "có thai", "pregnant"),
    "diabetes": ("tiểu đường", "đái tháo đường", "diabetes"),
    "hypertension": ("tăng huyết áp", "hypertension"),
    "heart_disease": ("bệnh tim", "heart disease"),
}

VIETNAMESE_LANGUAGE_TOKENS = {
    "ban",
    "bi",
    "bung",
    "cam",
    "chay",
    "chao",
    "co",
    "dau",
    "ho",
    "khong",
    "kho",
    "mau",
    "met",
    "muon",
    "nguc",
    "non",
    "sang",
    "sot",
    "thay",
    "tho",
    "toi",
    "tu",
    "va",
    "xin",
}
ENGLISH_LANGUAGE_TOKENS = {
    "am",
    "and",
    "bleeding",
    "breath",
    "chest",
    "cough",
    "feel",
    "fever",
    "have",
    "headache",
    "help",
    "is",
    "my",
    "nausea",
    "pain",
    "shortness",
    "since",
    "the",
    "with",
}
VIETNAMESE_MARKS = frozenset(
    "ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
)


def _state(context: ToolExecutionContext) -> CatalogStateStore:
    return context.state if isinstance(context.state, CatalogStateStore) else catalog_state


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid4()}"


def _text(arguments: dict[str, Any]) -> str:
    return str(
        arguments.get("patient_message")
        or arguments.get("text")
        or arguments.get("message")
        or arguments.get("note")
        or ""
    ).strip()


def _ascii_fold(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value.replace("đ", "d").replace("Đ", "D"))
    return "".join(char for char in folded if not unicodedata.combining(char))


def _structured(arguments: dict[str, Any]) -> StructuredSymptomData:
    raw = arguments.get("structured_symptoms") or arguments.get("structured_data") or arguments
    if isinstance(raw, StructuredSymptomData):
        return raw
    if not isinstance(raw, dict):
        raw = {}
    fields = raw.get("fields", raw.get("symptoms", {}))
    return StructuredSymptomData(
        symptom_group=str(raw.get("symptom_group", "general")),
        fields=fields if isinstance(fields, dict) else {},
        missing_fields=list(raw.get("missing_fields", [])),
        confidence=float(raw.get("confidence", 0.5)),
        source=str(raw.get("source", "catalog")),
    )


def _validation(arguments: dict[str, Any], data: StructuredSymptomData) -> ValidationResult:
    raw = arguments.get("validation")
    if isinstance(raw, ValidationResult):
        return raw
    if isinstance(raw, dict):
        return ValidationResult.model_validate(raw)
    return ChecklistValidator().validate(data)


def _red_flags(arguments: dict[str, Any], data: StructuredSymptomData) -> list[RedFlagFinding]:
    raw = arguments.get("red_flags")
    if isinstance(raw, list):
        return [item if isinstance(item, RedFlagFinding) else RedFlagFinding.model_validate(item) for item in raw]
    return RedFlagSafetyLayer().detect(data)


def _lookup(system: str, term: str) -> list[dict[str, Any]]:
    normalized = term.casefold().strip()
    entries = TERMINOLOGY[system]
    matches = []
    for key, (code, display) in entries.items():
        if normalized in key or key in normalized:
            matches.append(
                {
                    "code": code,
                    "display": display,
                    "system": system,
                    "confidence": 1.0 if normalized == key else 0.85,
                }
            )
    return matches


def _contains_any(text: str, values: tuple[str, ...]) -> bool:
    folded = _ascii_fold(text.casefold())
    return any(_ascii_fold(value.casefold()) in folded for value in values)


def _extract_entities(text: str, vocabulary: tuple[str, ...]) -> list[str]:
    return sorted({item for item in vocabulary if _contains_any(text, (item,))})


def _detect_language(text: str) -> tuple[str, float]:
    normalized = text.casefold()
    tokens = re.findall(r"[a-zA-ZÀ-ỹ]+", normalized)
    folded_tokens = [_ascii_fold(token) for token in tokens]
    vi_score = sum(token in VIETNAMESE_LANGUAGE_TOKENS for token in folded_tokens)
    en_score = sum(token in ENGLISH_LANGUAGE_TOKENS for token in folded_tokens)
    mark_count = sum(char in VIETNAMESE_MARKS for char in normalized)
    vi_score += min(mark_count, 2)

    if vi_score == 0 and en_score == 0:
        return "unknown", 0.0

    stronger = max(vi_score, en_score)
    weaker = min(vi_score, en_score)
    if weaker and weaker / stronger >= 0.5:
        evidence = min(vi_score + en_score, 6)
        return "mixed", round(min(0.95, 0.6 + evidence * 0.05), 3)

    language = "vi" if vi_score > en_score else "en"
    margin = abs(vi_score - en_score) / stronger
    evidence = min(stronger, 5)
    return language, round(min(0.99, 0.55 + margin * 0.25 + evidence * 0.04), 3)


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


async def run_tool(name: str, arguments: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    """Local implementations for all 82 catalog tools."""

    store = _state(context)
    text = _text(arguments)

    # A. Intake and conversation
    if name == "patient_message_normalizer":
        normalized = re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()
        return {"normalized_message": normalized}
    if name == "language_detector":
        language, confidence = _detect_language(text)
        return {"language": language, "confidence": confidence}
    if name == "medical_translation_tool":
        target = str(arguments.get("target_language", "en"))
        translations = {"đau ngực": "chest pain", "khó thở": "shortness of breath", "chảy máu": "bleeding"}
        translated = text
        if target == "en":
            for source, destination in translations.items():
                translated = re.sub(source, destination, translated, flags=re.IGNORECASE)
        preserved = _extract_entities(text, tuple(TERMINOLOGY["rxnorm"]))
        return {"translated_text": translated, "preserved_terms": preserved}
    if name == "conversation_memory_read":
        case_id = str(arguments.get("case_id") or context.case_id or "")
        return {"conversation": list(store.conversations.get(case_id, []))}
    if name == "conversation_memory_write":
        case_id = str(arguments.get("case_id") or context.case_id or "")
        item = {"message_id": _id("msg"), "role": arguments.get("role", "patient"), "content": arguments.get("content", text), "created_at": _now()}
        store.conversations[case_id].append(item)
        return {"stored": True, "message_id": item["message_id"]}
    if name == "patient_profile_read":
        return {"profile": dict(store.patient_profiles.get(str(arguments.get("patient_id", "")), {}))}
    if name == "consent_checker":
        patient_id = str(arguments.get("patient_id", ""))
        scope = str(arguments.get("scope", "triage"))
        scopes = store.consents.get(patient_id, set())
        return {"has_consent": scope in scopes or "*" in scopes, "missing_scope": None if scope in scopes or "*" in scopes else scope}

    # B. Semantic mapping and terminology
    if name == "symptom_extraction_tool":
        mapped = await RuleBackedSemanticMapper().map_message(text)
        return {"structured_symptoms": mapped.model_dump()}
    if name in {"snomed_concept_lookup", "icd10_lookup", "loinc_lookup", "rxnorm_lookup"}:
        system = name.split("_", 1)[0]
        term = str(arguments.get("term") or arguments.get("clinical_term") or arguments.get("medication_name") or text)
        key = "codes" if system in {"icd10", "loinc"} else "concepts"
        return {key: _lookup(system, term)}
    if name == "allergy_extraction_tool":
        pattern = re.compile(r"(?:dị ứng|di ung|allergic to)\s+([\wÀ-ỹ-]+)", re.IGNORECASE)
        return {"allergies": [{"substance": item, "reaction": None} for item in pattern.findall(text)]}
    if name == "medication_extraction_tool":
        medicines = _extract_entities(text, tuple(TERMINOLOGY["rxnorm"]))
        return {"medications": [{"name": item, "dose": None, "timing": None} for item in medicines]}
    if name == "risk_factor_extraction_tool":
        risks = [key for key, words in RISK_WORDS.items() if _contains_any(text, words)]
        age = arguments.get("age") or (arguments.get("profile") or {}).get("age")
        if isinstance(age, (int, float)) and age >= 65:
            risks.append("age_65_or_older")
        return {"risk_factors": sorted(set(risks))}

    # C. Validation and follow-up
    if name == "required_checklist_validator":
        result = ChecklistValidator().validate(_structured(arguments))
        return {"is_valid": result.is_valid, "missing_fields": result.missing_fields}
    if name == "contradiction_detector":
        result = ChecklistValidator().validate(_structured(arguments))
        return {"contradictions": [item.model_dump() for item in result.contradictions]}
    if name == "confidence_calibrator":
        data = _structured(arguments)
        evidence = arguments.get("evidence", [])
        evidence_count = len(evidence) if isinstance(evidence, list) else 0
        confidence = min(1.0, max(0.0, data.confidence + min(evidence_count, 3) * 0.05))
        low_fields = list(data.missing_fields) if confidence < 0.7 else []
        return {"confidence": confidence, "low_confidence_fields": low_fields}
    if name == "follow_up_question_generator":
        missing = arguments.get("missing_fields", [])
        return {"questions": [FOLLOW_UP_QUESTIONS.get(str(field), f"Vui lòng cung cấp thêm thông tin: {field}.") for field in missing]}
    if name == "question_prioritizer":
        questions = list(arguments.get("candidate_questions") or arguments.get("questions") or [])
        priority_terms = ("khó thở", "ý thức", "chảy máu", "đột ngột", "severity", "onset")
        ranked = sorted(questions, key=lambda question: not _contains_any(str(question), priority_terms))
        return {"prioritized_questions": ranked}
    if name == "health_literacy_rewriter":
        replacements = {"triệu chứng": "dấu hiệu bạn đang cảm thấy", "khởi phát": "bắt đầu", "nghiêm trọng": "nặng"}
        rewritten = text
        for source, destination in replacements.items():
            rewritten = re.sub(source, destination, rewritten, flags=re.IGNORECASE)
        return {"rewritten_text": rewritten}

    # D. Safety and red flags
    if name == "red_flag_detector":
        findings = RedFlagSafetyLayer().detect(_structured(arguments))
        return {"red_flags": [item.model_dump() for item in findings]}
    if name == "emergency_escalation_classifier":
        data = _structured(arguments)
        findings = _red_flags(arguments, data)
        priority = "Emergency" if findings else ("Urgent" if data.symptom_group in {"chest_pain", "breathing"} else "Routine")
        return {"priority": priority, "reason": "Red flag detected" if findings else "Rule-based symptom-group classification"}
    if name == "self_harm_risk_detector":
        high = _contains_any(text, ("tự tử", "tu tu", "kill myself", "suicide", "không muốn sống"))
        moderate = _contains_any(text, ("tự hại", "self harm", "muốn biến mất"))
        return {"risk_detected": high or moderate, "risk_level": "high" if high else ("moderate" if moderate else "none"), "evidence": ["matched crisis language"] if high or moderate else []}
    if name == "abuse_or_violence_detector":
        types = []
        if _contains_any(text, ("đánh tôi", "bạo lực", "hit me", "abuse")):
            types.append("physical_violence")
        if _contains_any(text, ("ép buộc", "đe dọa", "coercion", "threaten")):
            types.append("coercion")
        return {"risk_detected": bool(types), "risk_type": types, "evidence": ["matched violence language"] if types else []}
    if name in {"pediatric_risk_detector", "pregnancy_risk_detector", "elderly_risk_detector"}:
        data = _structured(arguments)
        age = arguments.get("age") or (arguments.get("profile") or {}).get("age")
        risks = []
        if name == "pediatric_risk_detector" and isinstance(age, (int, float)) and age < 16 and (data.fields.get("seizure") or data.fields.get("breathing_severity") == "severe"):
            risks.append("high_risk_pediatric_symptom")
        if name == "pregnancy_risk_detector" and arguments.get("pregnancy_status") in {True, "pregnant"} and (data.fields.get("bleeding") or data.fields.get("pain_severity")):
            risks.append("pregnancy_with_pain_or_bleeding")
        if name == "elderly_risk_detector" and isinstance(age, (int, float)) and age >= 65 and data.symptom_group in {"chest_pain", "breathing", "neurologic"}:
            risks.append("older_adult_high_risk_symptom")
        output_key = {"pediatric_risk_detector": "pediatric_risks", "pregnancy_risk_detector": "pregnancy_risks", "elderly_risk_detector": "elderly_risks"}[name]
        return {output_key: risks}

    # E. Clinical knowledge and RAG
    if name in {"clinical_guideline_search", "local_protocol_retriever", "triage_pathway_search"}:
        group = str(arguments.get("symptom_group", "general"))
        matches = [
            {"protocol_id": rule["id"], "title": f"VMedTriage {rule['symptom_group']} protocol", "excerpt": rule["reason"], "priority_hint": rule["priority"], "source": "local_config"}
            for rule in TRIAGE_PROTOCOL_RULES
            if group == "general" or rule["symptom_group"] == group
        ]
        key = {"clinical_guideline_search": "matches", "local_protocol_retriever": "protocols", "triage_pathway_search": "pathways"}[name]
        return {key: matches}
    if name == "drug_interaction_checker":
        medications = [str(item.get("name", "") if isinstance(item, dict) else item).casefold() for item in arguments.get("medications", [])]
        interactions = []
        for pair, (severity, reason) in DRUG_INTERACTIONS.items():
            if pair.issubset(medications):
                interactions.append({"medications": sorted(pair), "severity": severity, "reason": reason})
        return {"interactions": interactions}
    if name == "contraindication_checker":
        action = str(arguments.get("candidate_action", "")).casefold()
        profile = arguments.get("patient_context", {})
        contraindications = []
        if "aspirin" in action and (profile.get("active_bleeding") or profile.get("aspirin_allergy")):
            contraindications.append("aspirin_with_bleeding_or_allergy")
        return {"contraindications": contraindications}
    if name == "clinical_calculator_tool":
        calculator = str(arguments.get("calculator_name", "bmi")).casefold()
        values = arguments.get("values", {})
        if calculator == "bmi":
            height_m = _finite_number(values.get("height_m"))
            weight_kg = _finite_number(values.get("weight_kg"))
            if height_m is None or weight_kg is None:
                score, interpretation = None, "insufficient_input"
            elif not 0.5 <= height_m <= 2.5 or not 1 <= weight_kg <= 500:
                score, interpretation = None, "invalid_input"
            else:
                score = round(weight_kg / height_m**2, 2)
                interpretation = (
                    "underweight"
                    if score < 18.5
                    else "normal"
                    if score < 25
                    else "overweight_or_obesity"
                )
        elif calculator == "qsofa":
            required = {"respiratory_rate", "systolic_bp", "altered_mentation"}
            if not required.issubset(values):
                score, interpretation = None, "insufficient_input"
            else:
                respiratory_rate = _finite_number(values.get("respiratory_rate"))
                systolic_bp = _finite_number(values.get("systolic_bp"))
                altered_mentation = values.get("altered_mentation")
                if (
                    respiratory_rate is None
                    or systolic_bp is None
                    or not 0 <= respiratory_rate <= 100
                    or not 20 <= systolic_bp <= 300
                    or not isinstance(altered_mentation, bool)
                ):
                    score, interpretation = None, "invalid_input"
                else:
                    score = sum((respiratory_rate >= 22, systolic_bp <= 100, altered_mentation))
                    interpretation = "high_risk" if score >= 2 else "lower_risk"
        else:
            score, interpretation = None, "unsupported_calculator"
        return {"score": score, "interpretation": interpretation}
    if name == "medical_knowledge_summarizer":
        documents = arguments.get("documents", [])
        summaries = [str(item.get("excerpt") or item.get("text") or "") if isinstance(item, dict) else str(item) for item in documents]
        citations = [item.get("source") for item in documents if isinstance(item, dict) and item.get("source")]
        return {"summary": " ".join(summaries)[:2000], "citations": citations}

    # F. Triage decision support
    if name == "protocol_triage_engine":
        data = _structured(arguments)
        proposal = ProtocolTriageEngine().propose(data, _validation(arguments, data), _red_flags(arguments, data))
        return {"triage_proposal": proposal.model_dump()}
    if name == "cds_hooks_triage_advice":
        proposal = arguments.get("triage_proposal") or arguments.get("context", {}).get("triage_proposal", {})
        return {"cards": [{"summary": "Review triage proposal", "detail": str(proposal.get("reason", "Clinical review required")), "indicator": "warning", "source": {"label": "VMedTriage local CDS"}}]}
    if name == "priority_score_calculator":
        priority = str(arguments.get("priority") or (arguments.get("triage_proposal") or {}).get("priority", "Manual review"))
        score = {"Emergency": 100, "Urgent": 75, "Manual review": 50, "Routine": 25, "Self-care": 10}.get(priority, 50)
        score += min(len(arguments.get("red_flags", [])) * 5, 20)
        return {"priority_score": min(score, 100), "priority_bucket": "high" if score >= 75 else ("standard" if score >= 25 else "low")}
    if name == "manual_review_decider":
        proposal = arguments.get("proposal") or arguments.get("triage_proposal") or {}
        required = bool(proposal.get("requires_manual_review", True)) or bool(arguments.get("tool_errors"))
        return {"requires_review": required, "reason": "Clinical proposal or tool uncertainty requires HITL" if required else "Policy permits automated continuation"}
    if name == "care_navigation_router":
        priority = str((arguments.get("proposal") or arguments.get("triage_proposal") or {}).get("priority", "Manual review"))
        route = {"Emergency": "emergency_department", "Urgent": "urgent_clinical_review", "Routine": "routine_appointment", "Self-care": "approved_self_care"}.get(priority, "manual_review")
        return {"route": route, "reason": f"Mapped from triage priority {priority}"}

    # G. EHR/FHIR local adapter. Real external calls are delegated by the registry when configured.
    if name.startswith("fhir_"):
        patient_id = str(arguments.get("patient_id", ""))
        resource_by_tool = {"fhir_observation_read": "Observation", "fhir_condition_read": "Condition", "fhir_medication_read": "MedicationStatement", "fhir_allergy_read": "AllergyIntolerance"}
        if name == "fhir_patient_context_read":
            resources = [item for values in store.fhir_resources[patient_id].values() for item in values]
            return {"bundle": {"resourceType": "Bundle", "type": "collection", "entry": [{"resource": item} for item in resources]}, "resource_count": len(resources), "redacted": True}
        if name in resource_by_tool:
            key = {"Observation": "observations", "Condition": "conditions", "MedicationStatement": "medications", "AllergyIntolerance": "allergies"}[resource_by_tool[name]]
            return {key: list(store.fhir_resources[patient_id][resource_by_tool[name]])}
        resource_type = {"fhir_encounter_create": "Encounter", "fhir_task_create": "Task", "fhir_document_reference_write": "DocumentReference"}[name]
        payload = dict(arguments.get("encounter_payload") or arguments.get("task_payload") or arguments.get("document") or {})
        resource_id = _id(resource_type.lower())
        resource = {"resourceType": resource_type, "id": resource_id, "subject": {"reference": f"Patient/{patient_id}"}, **payload}
        store.fhir_resources[patient_id][resource_type].append(resource)
        if resource_type == "Encounter":
            return {"encounter_id": resource_id, "created": True}
        if resource_type == "Task":
            return {"task_id": resource_id, "created": True}
        return {"document_reference_id": resource_id, "stored": True}

    # H. Nurse workflow and HITL
    if name == "nurse_queue_create_item":
        case_id = str(arguments.get("case_id") or context.case_id or _id("case"))
        item = {"case_id": case_id, "summary": arguments.get("summary", {}), "proposal": arguments.get("proposal") or arguments.get("triage_proposal", {}), "status": "awaiting_review", "created_at": _now()}
        store.queue[case_id] = item
        return {"queue_item": item}
    if name == "nurse_queue_read":
        status = arguments.get("status")
        items = [item for item in store.queue.values() if not status or item.get("status") == status]
        return {"items": items}
    if name == "nurse_case_assign":
        case_id, nurse_id = str(arguments.get("case_id", "")), str(arguments.get("nurse_id", ""))
        store.assignments[case_id] = nurse_id
        if case_id in store.queue:
            store.queue[case_id]["assignee"] = nurse_id
        return {"assigned": True, "assignee": nurse_id}
    if name == "nurse_priority_alert":
        event = {"alert_id": _id("alert"), "case_id": arguments.get("case_id") or context.case_id, "channel": arguments.get("channel", "dashboard"), "message": arguments.get("message", "Priority case requires review"), "created_at": _now()}
        store.outbox.append(event)
        return {"alert_id": event["alert_id"], "delivered": False, "channel": event["channel"]}
    if name == "human_review_submit":
        case_id = str(arguments.get("case_id") or context.case_id or "")
        action = str(arguments.get("action", "approve"))
        status = {"approve": "approved", "edit": "approved", "reject": "rejected", "escalate": "escalated", "ask_more": "collecting_information"}.get(action, "needs_nurse_review")
        store.case_statuses[case_id] = status
        return {"case_id": case_id, "status": status, "patient_visible_response": arguments.get("response") or arguments.get("approved_response")}
    if name == "approved_response_sender":
        event = {"message_id": _id("approved-msg"), "case_id": arguments.get("case_id") or context.case_id, "channel": arguments.get("channel", "app"), "message": arguments.get("approved_response", ""), "status": "queued", "created_at": _now()}
        store.outbox.append(event)
        return {"sent": False, "message_id": event["message_id"]}
    if name == "handoff_summary_generator":
        data = _structured(arguments)
        validation = _validation(arguments, data)
        findings = _red_flags(arguments, data)
        proposal = arguments.get("proposal") or arguments.get("triage_proposal", {})
        return {"summary": {"chief_complaint": data.symptom_group, "onset": data.fields.get("onset"), "severity": data.fields.get("pain_severity") or data.fields.get("breathing_severity"), "missing_information": validation.missing_fields, "red_flags": [item.model_dump() for item in findings], "proposed_priority": proposal.get("priority")}}
    if name == "case_status_updater":
        case_id, status = str(arguments.get("case_id") or context.case_id or ""), str(arguments.get("status", "needs_nurse_review"))
        store.case_statuses[case_id] = status
        if case_id in store.queue:
            store.queue[case_id]["status"] = status
        return {"case_id": case_id, "status": status}

    # I. Audit, compliance, and governance
    if name in {"triage_audit_log_write", "tool_call_audit_logger", "consent_audit_logger"}:
        event = {"event_id": _id("audit"), "event_type": arguments.get("event_type", name), "case_id": arguments.get("case_id") or context.case_id, "actor_role": arguments.get("actor_role", context.actor_role), "payload": arguments.get("payload", arguments), "created_at": _now()}
        store.audit_events.append(event)
        return {"event_id": event["event_id"], "stored": True}
    if name == "phi_redactor":
        redacted, count = re.subn(r"\b[\w.+-]+@[\w.-]+\.\w+\b", "[EMAIL]", text)
        redacted, phone_count = re.subn(r"(?<!\d)(?:\+?84|0)\d{9,10}(?!\d)", "[PHONE]", redacted)
        redacted, id_count = re.subn(r"\b\d{9,12}\b", "[IDENTIFIER]", redacted)
        return {"redacted_text": redacted, "redactions": count + phone_count + id_count}
    if name == "policy_guardrail_checker":
        draft = str(arguments.get("draft_output") or text)
        violations = [code for code, words in {"diagnosis_claim": ("chắc chắn bạn bị", "you definitely have"), "prescription": ("hãy dùng thuốc", "take this medication")}.items() if _contains_any(draft, words)]
        return {"allowed": not violations, "violations": violations}
    if name == "patient_visible_safety_filter":
        response = str(arguments.get("response") or text)
        approval = bool(arguments.get("approval_state") in {True, "approved"} or context.approved)
        issues = [] if approval else ["human_approval_required"]
        if _contains_any(response, ("chắc chắn bạn bị", "you definitely have")):
            issues.append("unsupported_diagnosis")
        return {"safe_response": response if not issues else "Phản hồi đang chờ nhân viên y tế xem xét.", "blocked": bool(issues), "issues": issues}
    if name == "data_retention_policy_checker":
        periods = {"audit": "7_years", "clinical_case": "10_years", "analytics_deidentified": "indefinite"}
        data_type = str(arguments.get("data_type", "clinical_case"))
        return {"allowed": data_type in periods, "retention_period": periods.get(data_type), "reason": "Configured retention policy" if data_type in periods else "Unknown data type"}
    if name == "access_control_checker":
        role, action = str((arguments.get("actor") or {}).get("role", context.actor_role)), str(arguments.get("action", "read"))
        allowed = role in {"system", "admin"} or (role in {"nurse", "clinician"} and action in {"read", "review", "write"}) or (role == "patient" and action == "read_own")
        return {"allowed": allowed, "reason": "RBAC rule matched" if allowed else "Role is not allowed for this action"}

    # J. Notification adapters queue messages; provider delivery is intentionally separate.
    if name in {"sms_notification_tool", "email_notification_tool", "push_notification_tool", "on_call_paging_tool"}:
        channel = name.split("_", 1)[0] if name != "on_call_paging_tool" else "page"
        event_id = _id(channel)
        event = {"id": event_id, "channel": channel, "recipient": arguments.get("recipient") or arguments.get("team"), "message": arguments.get("message") or arguments.get("body"), "status": "queued", "created_at": _now()}
        store.outbox.append(event)
        if channel == "push":
            return {"sent": False, "notification_id": event_id}
        if channel == "page":
            return {"page_id": event_id, "delivered": False}
        return {"sent": False, "message_id": event_id}
    if name == "appointment_scheduler":
        appointment = {"appointment_id": _id("appointment"), "patient_id": arguments.get("patient_id"), "case_id": arguments.get("case_id") or context.case_id, "slot": arguments.get("slot"), "reason": arguments.get("reason"), "status": "booked"}
        store.appointments.append(appointment)
        return {"appointment_id": appointment["appointment_id"], "scheduled": True}

    # K. Analytics and evaluation
    if name == "case_metrics_logger":
        event = {"metric_event_id": _id("metric"), "case_id": arguments.get("case_id") or context.case_id, "metrics": arguments.get("metrics", {}), "created_at": _now()}
        store.metrics.append(event)
        return {"stored": True, "metric_event_id": event["metric_event_id"]}
    if name == "triage_quality_evaluator":
        cases, expected = arguments.get("cases", []), arguments.get("expected_labels", [])
        predicted = [item.get("priority") or (item.get("triage_proposal") or {}).get("priority") for item in cases]
        total = min(len(predicted), len(expected))
        accuracy = sum(predicted[index] == expected[index] for index in range(total)) / total if total else 0.0
        return {"scores": {"accuracy": accuracy, "evaluated_cases": total}}
    if name == "rag_grounding_evaluator":
        output = str(arguments.get("output", "")).casefold()
        evidence = arguments.get("evidence", [])
        evidence_text = " ".join(str(item) for item in evidence).casefold()
        tokens = {token for token in re.findall(r"\w{5,}", output)}
        unsupported = sorted(token for token in tokens if token not in evidence_text)[:20]
        return {"grounded": bool(evidence) and len(unsupported) <= max(2, len(tokens) // 2), "issues": unsupported}
    if name == "safety_event_detector":
        trace = arguments.get("case_trace", [])
        events = []
        if any(item.get("red_flags") and not item.get("requires_human_review", True) for item in trace if isinstance(item, dict)):
            events.append({"code": "red_flag_without_review", "severity": "high"})
        return {"safety_events": events}
    if name == "feedback_collector":
        event = {"feedback_id": _id("feedback"), "case_id": arguments.get("case_id") or context.case_id, "actor_role": arguments.get("actor_role", context.actor_role), "feedback": arguments.get("feedback"), "created_at": _now()}
        store.feedback.append(event)
        return {"feedback_id": event["feedback_id"], "stored": True}
    if name == "drift_monitor":
        metrics = arguments.get("metrics") or [item.get("metrics", {}) for item in store.metrics]
        signals = []
        for key in {metric_key for item in metrics if isinstance(item, dict) for metric_key in item}:
            values = [float(item[key]) for item in metrics if isinstance(item, dict) and isinstance(item.get(key), (int, float))]
            if len(values) >= 4:
                midpoint = len(values) // 2
                baseline, recent = sum(values[:midpoint]) / midpoint, sum(values[midpoint:]) / (len(values) - midpoint)
                if abs(recent - baseline) > max(abs(baseline) * 0.2, 0.1):
                    signals.append({"metric": key, "baseline": baseline, "recent": recent})
        return {"drift_detected": bool(signals), "signals": signals}

    # L is handled here because it needs access to the active registry.
    if name == "tool_registry_list":
        filters = arguments.get("filters", {})
        tools = context.registry.list_tools() if context.registry else []
        if filters.get("category"):
            tools = [item for item in tools if item.category == filters["category"]]
        return {"tools": [item.model_dump() for item in tools]}
    if name == "tool_capability_matcher":
        intent = str(arguments.get("intent", "")).casefold()
        tools = context.registry.list_tools() if context.registry else []
        scored = []
        intent_tokens = set(re.findall(r"\w+", intent))
        for item in tools:
            haystack = f"{item.name} {item.description} {item.action}".casefold()
            score = sum(token in haystack for token in intent_tokens)
            if score:
                scored.append({"tool_name": item.name, "score": score})
        return {"candidate_tools": sorted(scored, key=lambda item: item["score"], reverse=True)[:10]}
    if name == "tool_policy_enforcer":
        descriptor = arguments.get("tool_descriptor", {})
        risk = descriptor.get("risk_level") or descriptor.get("policy", {}).get("risk_level", "read_only")
        allowed = risk != "side_effect" or context.approved
        return {"allowed": allowed, "reason": "Approved by execution policy" if allowed else "Side-effect tool requires explicit approval"}
    if name == "tool_argument_builder":
        descriptor = arguments.get("tool_descriptor", {})
        state = arguments.get("agent_state", {})
        case = arguments.get("case_context", {})
        required = descriptor.get("required_inputs", [])
        built = {key: state.get(key, case.get(key)) for key in required if state.get(key, case.get(key)) is not None}
        return {"arguments": built, "missing_inputs": [key for key in required if key not in built]}
    if name == "tool_result_validator":
        descriptor, raw = arguments.get("tool_descriptor", {}), arguments.get("raw_result", {})
        expected = list((descriptor.get("output") or {}).keys())
        missing = [key for key in expected if key not in raw]
        return {"valid": not missing, "normalized_result": raw if not missing else {}, "errors": [f"Missing output: {key}" for key in missing]}
    if name == "fallback_strategy_selector":
        error = str(arguments.get("error", "")).casefold()
        fallback = "local_implementation" if "server" in error or "timeout" in error else "manual_review"
        return {"fallback": fallback, "reason": "Recoverable infrastructure failure" if fallback == "local_implementation" else "No safe automated fallback"}
    if name == "orchestration_trace_writer":
        trace = {"trace_id": _id("trace"), "case_id": arguments.get("case_id") or context.case_id, "event": arguments.get("trace_event", {}), "created_at": _now()}
        store.traces.append(trace)
        return {"trace_id": trace["trace_id"], "stored": True}

    raise KeyError(f"No local implementation is registered for {name}.")
