"""Tool stub: send SMS notification."""

TOOL_SPEC = {
    "id": 65,
    "name": "sms_notification_tool",
    "description": "Send SMS notification to patient or staff after required approval.",
    "input": {"recipient": "Phone number or recipient id.", "message": "Approved message.", "case_id": "Triage case id."},
    "output": {"sent": "Delivery status.", "message_id": "SMS message id."},
    "action": "Deliver approved operational notifications by SMS.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
