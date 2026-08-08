from __future__ import annotations

from src.config import RED_FLAG_RULES
from src.models.schemas import RedFlagFinding, StructuredSymptomData


class RedFlagSafetyLayer:
    def detect(self, data: StructuredSymptomData) -> list[RedFlagFinding]:
        findings: list[RedFlagFinding] = []

        for rule in RED_FLAG_RULES:
            matched_fields = self._match_rule(data.fields, rule)
            if matched_fields:
                findings.append(
                    RedFlagFinding(
                        code=str(rule["code"]),
                        label=str(rule["label"]),
                        matched_fields=matched_fields,
                    )
                )

        return findings

    def _match_rule(self, fields: dict[str, object], rule: dict[str, object]) -> list[str]:
        required_true_fields = tuple(rule.get("required_true_fields", ()))
        if required_true_fields and all(fields.get(field) is True for field in required_true_fields):
            return list(required_true_fields)

        any_true_fields = tuple(rule.get("any_true_fields", ()))
        matched_any = [field for field in any_true_fields if fields.get(field) is True]
        if matched_any:
            return matched_any

        field_equals = dict(rule.get("field_equals", {}))
        matched_equals = [field for field, expected in field_equals.items() if fields.get(field) == expected]
        return matched_equals
