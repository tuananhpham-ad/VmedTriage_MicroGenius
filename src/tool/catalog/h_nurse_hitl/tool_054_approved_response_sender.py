"""Tool stub: send approved patient response."""

TOOL_SPEC = {
    "id": 54,
    "name": "approved_response_sender",
    "description": "Send only nurse-approved patient-facing response to the patient channel.",
    "input": {"case_id": "Triage case id.", "approved_response": "Human-approved response.", "channel": "Delivery channel."},
    "output": {"sent": "Delivery status.", "message_id": "Sent message id."},
    "action": "Prevent unapproved clinical text from reaching the patient.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
