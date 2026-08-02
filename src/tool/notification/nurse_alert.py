from __future__ import annotations

from src.tool.base import MCPToolDescriptor, ToolCallPolicy, ToolRiskLevel


def build_descriptor() -> MCPToolDescriptor:
    return MCPToolDescriptor(
        name="nurse_priority_alert",
        category="notification",
        external_server="notification",
        local_module="src.tool.notification.nurse_alert",
        description="Send a high-priority alert to the nurse dashboard or paging system.",
        when_to_use="Use only after red-flag safety layer creates an Emergency proposal.",
        input_schema={
            "type": "object",
            "properties": {
                "case_id": {"type": "string"},
                "priority": {"type": "string", "enum": ["high", "standard"]},
                "red_flag_codes": {"type": "array", "items": {"type": "string"}},
                "message": {"type": "string"},
            },
            "required": ["case_id", "priority", "message"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "alert_id": {"type": "string"},
                "delivered": {"type": "boolean"},
                "channel": {"type": "string"},
            },
            "required": ["alert_id", "delivered"],
        },
        policy=ToolCallPolicy(
            risk_level=ToolRiskLevel.SIDE_EFFECT,
            requires_human_approval=False,
            patient_visible=False,
            allow_before_hitl=True,
        ),
    )
