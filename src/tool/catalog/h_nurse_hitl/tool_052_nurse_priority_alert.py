"""Tool stub: alert nurse about priority case."""

TOOL_SPEC = {
    "id": 52,
    "name": "nurse_priority_alert",
    "description": "Send a high-priority alert to the nurse dashboard or paging system.",
    "input": {"case_id": "Triage case id.", "priority": "Queue priority.", "red_flag_codes": "Red flag codes.", "message": "Alert message."},
    "output": {"alert_id": "Alert id.", "delivered": "Delivery status.", "channel": "Notification channel."},
    "action": "Notify staff when red flags require rapid review.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
