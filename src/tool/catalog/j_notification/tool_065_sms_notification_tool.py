"""Tool stub: send SMS notification."""

TOOL_SPEC = {
    "id": 65,
    "name": "sms_notification_tool",
    "description": "Send SMS notification to patient or staff after required approval.",
    "input": {"recipient": "Phone number or recipient id.", "message": "Approved message.", "case_id": "Triage case id."},
    "output": {"sent": "Delivery status.", "message_id": "SMS message id."},
    "action": "Deliver approved operational notifications by SMS.",
}

# TODO: Implement MCP/local adapter.
