from __future__ import annotations

from src.tool.base import MCPToolDescriptor, ToolCallPolicy, ToolRiskLevel


def build_descriptor() -> MCPToolDescriptor:
    return MCPToolDescriptor(
        name="cds_hooks_triage_advice",
        category="cds",
        external_server="cds_hooks",
        local_module="src.tool.cds.cds_hooks",
        description="Request CDS Hooks cards for clinician-facing triage decision support.",
        when_to_use="Use after local protocol proposal when an external CDS service is available for cross-checking.",
        input_schema={
            "type": "object",
            "properties": {
                "hook": {"type": "string", "default": "patient-view"},
                "context": {"type": "object"},
                "prefetch": {"type": "object"},
            },
            "required": ["hook", "context"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "cards": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "summary": {"type": "string"},
                            "indicator": {"type": "string"},
                            "detail": {"type": "string"},
                            "source": {"type": "object"},
                        },
                    },
                }
            },
            "required": ["cards"],
        },
        policy=ToolCallPolicy(
            risk_level=ToolRiskLevel.CLINICAL_DECISION_SUPPORT,
            requires_human_approval=True,
            patient_visible=False,
            allow_before_hitl=True,
        ),
    )
