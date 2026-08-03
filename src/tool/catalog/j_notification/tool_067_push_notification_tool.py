"""Tool stub: send push notification."""

TOOL_SPEC = {
    "id": 67,
    "name": "push_notification_tool",
    "description": "Send push notification to app, nurse dashboard, or patient device.",
    "input": {"recipient": "Recipient id.", "message": "Approved message.", "case_id": "Triage case id."},
    "output": {"sent": "Delivery status.", "notification_id": "Push notification id."},
    "action": "Notify users inside app-controlled channels.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
