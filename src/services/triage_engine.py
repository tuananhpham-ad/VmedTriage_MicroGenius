from __future__ import annotations

from src.config import TRIAGE_PROTOCOL_RULES, get_settings
from src.models.schemas import RedFlagFinding, StructuredSymptomData, TriagePriority, TriageProposal, ValidationResult


class ProtocolTriageEngine:
    def propose(
        self,
        data: StructuredSymptomData,
        validation: ValidationResult,
        red_flags: list[RedFlagFinding],
    ) -> TriageProposal:
        if red_flags:
            return TriageProposal(
                priority=TriagePriority.EMERGENCY,
                protocol_id="VMED-RF-001",
                reason="Red-flag safety layer matched: "
                + ", ".join(finding.label for finding in red_flags),
                confidence=1.0,
                requires_manual_review=True,
            )

        if not validation.is_valid:
            return TriageProposal(
                priority=TriagePriority.MANUAL_REVIEW,
                reason="Checklist is incomplete, contradictory, or below mapping confidence threshold.",
                confidence=data.confidence,
                requires_manual_review=True,
            )

        for rule in TRIAGE_PROTOCOL_RULES:
            if self._matches_rule(data, rule):
                return TriageProposal(
                    priority=TriagePriority(str(rule["priority"])),
                    protocol_id=str(rule["id"]),
                    reason=str(rule["reason"]),
                    confidence=max(data.confidence, get_settings().manual_review_confidence_threshold),
                    requires_manual_review=True,
                )

        return TriageProposal(
            priority=TriagePriority.MANUAL_REVIEW,
            reason="No configured protocol rule matched the structured data.",
            confidence=data.confidence,
            requires_manual_review=True,
        )

    def _matches_rule(self, data: StructuredSymptomData, rule: dict[str, object]) -> bool:
        rule_group = rule.get("symptom_group")
        if rule_group and rule_group != data.symptom_group:
            return False

        conditions = dict(rule.get("conditions", {}))
        return all(data.fields.get(field) == expected for field, expected in conditions.items())
