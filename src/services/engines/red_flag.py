from __future__ import annotations

from src.config import RED_FLAG_RULES
from src.models.schemas import RedFlagFinding, StructuredSymptomData
from src.services.engines.red_flag_text_rules import detect_text_red_flags


class RedFlagSafetyLayer:
    def detect(self, data: StructuredSymptomData, *texts: str) -> list[RedFlagFinding]:
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

        # Structured fields catch explicit questionnaire answers.  The text rules
        # cover a patient describing an emergency in free text before every field
        # has been mapped; the same rule list is also used by the standalone LLM
        # intake demo.
        existing_codes = {finding.code for finding in findings}
        for text_rule, phrase in detect_text_red_flags(*texts):
            if text_rule.code in existing_codes:
                continue
            findings.append(
                RedFlagFinding(
                    code=text_rule.code,
                    label=text_rule.label,
                    matched_fields=[f"message:{phrase}"],
                )
            )
            existing_codes.add(text_rule.code)

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
