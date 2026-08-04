from __future__ import annotations

from src.config import FOLLOW_UP_QUESTIONS, REQUIRED_FIELDS_BY_SYMPTOM_GROUP, get_settings
from src.models.schemas import StructuredSymptomData, ValidationIssue, ValidationResult


class ChecklistValidator:
    def validate(self, data: StructuredSymptomData) -> ValidationResult:
        required_fields = REQUIRED_FIELDS_BY_SYMPTOM_GROUP.get(
            data.symptom_group,
            REQUIRED_FIELDS_BY_SYMPTOM_GROUP[get_settings().default_symptom_group],
        )
        missing_fields = [field for field in required_fields if field not in data.fields]
        contradictions = self._find_contradictions(data)
        low_confidence = data.confidence < get_settings().semantic_mapping_confidence_threshold
        follow_up_questions = [
            FOLLOW_UP_QUESTIONS[field]
            for field in missing_fields
            if field in FOLLOW_UP_QUESTIONS
        ]

        if low_confidence:
            follow_up_questions.append("Bạn có thể mô tả lại triệu chứng chính rõ hơn không?")

        return ValidationResult(
            is_valid=not missing_fields and not contradictions and not low_confidence,
            missing_fields=missing_fields,
            contradictions=contradictions,
            low_confidence=low_confidence,
            follow_up_questions=follow_up_questions,
        )

    def _find_contradictions(self, data: StructuredSymptomData) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        severity = data.fields.get("pain_severity")

        if isinstance(severity, int) and not 1 <= severity <= 10:
            issues.append(
                ValidationIssue(
                    code="invalid_pain_severity",
                    field="pain_severity",
                    message="Pain severity must be between 1 and 10.",
                )
            )

        if data.fields.get("chest_pain") is False and data.symptom_group == "chest_pain":
            issues.append(
                ValidationIssue(
                    code="conflicting_chest_pain_group",
                    field="chest_pain",
                    message="Symptom group says chest pain but chest_pain is false.",
                )
            )

        return issues
