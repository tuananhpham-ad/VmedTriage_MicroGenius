from __future__ import annotations

from src.tool.base import MCPToolDescriptor, ToolCallPolicy, ToolRiskLevel


def build_descriptor() -> MCPToolDescriptor:
    return MCPToolDescriptor(
        name="fhir_patient_context_read",
        category="fhir",
        external_server="fhir",
        local_module="src.tool.fhir.ehr_context",
        description="Read limited patient context from an EHR/FHIR server for nurse review.",
        when_to_use="Use only for authenticated nurse-facing workflows when prior conditions or observations are needed.",
        input_schema={
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
                "resources": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["Patient", "Condition", "Observation", "MedicationStatement", "AllergyIntolerance"]},
                },
            },
            "required": ["patient_id", "resources"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "bundle": {"type": "object"},
                "resource_count": {"type": "integer"},
                "redacted": {"type": "boolean"},
            },
            "required": ["bundle", "resource_count", "redacted"],
        },
        policy=ToolCallPolicy(
            risk_level=ToolRiskLevel.READ_ONLY,
            requires_human_approval=True,
            patient_visible=False,
            allow_before_hitl=False,
        ),
    )
