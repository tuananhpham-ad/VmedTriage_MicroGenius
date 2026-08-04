from __future__ import annotations

from src.tool.base import MCPToolDescriptor, ToolCallPolicy, ToolRiskLevel


def build_descriptor() -> MCPToolDescriptor:
    return MCPToolDescriptor(
        name="clinical_guideline_search",
        category="search",
        external_server="clinical_guideline",
        local_module="src.tool.search.clinical_guideline_search",
        description="Search approved clinical triage protocols or local guideline documents.",
        when_to_use="Use after structured mapping and validation when the protocol engine needs grounded evidence.",
        input_schema={
            "type": "object",
            "properties": {
                "symptom_group": {"type": "string"},
                "query": {"type": "string"},
                "patient_age": {"type": "integer", "minimum": 0},
                "red_flags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["symptom_group", "query"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "matches": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "protocol_id": {"type": "string"},
                            "title": {"type": "string"},
                            "excerpt": {"type": "string"},
                            "priority_hint": {"type": "string"},
                            "source_url": {"type": "string"},
                        },
                    },
                }
            },
            "required": ["matches"],
        },
        policy=ToolCallPolicy(
            risk_level=ToolRiskLevel.CLINICAL_DECISION_SUPPORT,
            requires_human_approval=True,
            patient_visible=False,
            allow_before_hitl=True,
        ),
    )
