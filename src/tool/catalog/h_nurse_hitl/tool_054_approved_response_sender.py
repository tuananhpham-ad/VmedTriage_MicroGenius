"""Tool stub: send approved patient response."""

TOOL_SPEC = {
    "id": 54,
    "name": "approved_response_sender",
    "description": "Send only nurse-approved patient-facing response to the patient channel.",
    "input": {"case_id": "Triage case id.", "approved_response": "Human-approved response.", "channel": "Delivery channel."},
    "output": {"sent": "Delivery status.", "message_id": "Sent message id."},
    "action": "Prevent unapproved clinical text from reaching the patient.",
}

# TODO: Implement MCP/local adapter.
