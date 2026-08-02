from __future__ import annotations

from src.models.schemas import HandoffSummary, RedFlagFinding, StructuredSymptomData, TriageProposal, ValidationResult


class SummaryGenerator:
    def build(
        self,
        data: StructuredSymptomData,
        validation: ValidationResult,
        red_flags: list[RedFlagFinding],
        proposal: TriageProposal,
    ) -> HandoffSummary:
        return HandoffSummary(
            chief_complaint=data.symptom_group,
            onset=_optional_string(data.fields.get("onset")),
            severity=data.fields.get("pain_severity") or data.fields.get("breathing_severity"),
            associated_symptoms=self._associated_symptoms(data.fields),
            missing_information=validation.missing_fields,
            red_flags=red_flags,
            proposed_priority=proposal.priority,
            protocol_reason=proposal.reason,
        )

    def _associated_symptoms(self, fields: dict[str, object]) -> list[str]:
        labels = {
            "shortness_of_breath": "shortness_of_breath",
            "pain_radiation": "pain_radiation",
            "face_droop": "face_droop",
            "arm_weakness": "arm_weakness",
            "speech_difficulty": "speech_difficulty",
            "bleeding": "bleeding",
            "seizure": "seizure",
            "loss_of_consciousness": "loss_of_consciousness",
        }
        return [label for field, label in labels.items() if fields.get(field)]


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
