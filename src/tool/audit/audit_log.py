from __future__ import annotations

from src.tool.base import MCPToolDescriptor, ToolCallPolicy, ToolRiskLevel


def build_descriptor() -> MCPToolDescriptor:
    return MCPToolDescriptor(
        name="triage_audit_log_write",
        category="audit",
        external_server="audit",
        local_module="src.tool.audit.audit_log",
        description="Write an immutable triage audit event to an external audit store.",
        when_to_use="Use after mapping, validation, red-flag detection, proposal, and nurse review decisions.",
        input_schema={
            "type": "object",
            "properties": {
                "case_id": {"type": "string"},
                "event_type": {"type": "string"},
                "actor_role": {"type": "string"},
                "payload": {"type": "object"},
            },
            "required": ["case_id", "event_type", "actor_role", "payload"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "stored": {"type": "boolean"},
            },
            "required": ["event_id", "stored"],
        },
        policy=ToolCallPolicy(
            risk_level=ToolRiskLevel.SIDE_EFFECT,
            requires_human_approval=False,
            patient_visible=False,
            allow_before_hitl=True,
        ),
    )
