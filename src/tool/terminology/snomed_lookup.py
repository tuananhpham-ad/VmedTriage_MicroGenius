from __future__ import annotations

from src.tool.base import MCPToolDescriptor, ToolCallPolicy, ToolRiskLevel


def build_descriptor() -> MCPToolDescriptor:
    return MCPToolDescriptor(
        name="snomed_concept_lookup",
        category="terminology",
        external_server="terminology",
        local_module="src.tool.terminology.snomed_lookup",
        description="Normalize mapped symptoms to SNOMED CT concepts through a terminology server.",
        when_to_use="Use after Gemma semantic mapping to standardize clinical terms before protocol matching.",
        input_schema={
            "type": "object",
            "properties": {
                "term": {"type": "string"},
                "language": {"type": "string", "default": "vi"},
                "system": {"type": "string", "default": "http://snomed.info/sct"},
            },
            "required": ["term"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "concepts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "code": {"type": "string"},
                            "display": {"type": "string"},
                            "system": {"type": "string"},
                            "confidence": {"type": "number"},
                        },
                    },
                }
            },
            "required": ["concepts"],
        },
        policy=ToolCallPolicy(
            risk_level=ToolRiskLevel.READ_ONLY,
            requires_human_approval=False,
            patient_visible=False,
            allow_before_hitl=True,
        ),
    )
