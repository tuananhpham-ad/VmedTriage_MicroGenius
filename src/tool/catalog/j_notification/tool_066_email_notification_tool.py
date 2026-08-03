"""Tool stub: send email notification."""

TOOL_SPEC = {
    "id": 66,
    "name": "email_notification_tool",
    "description": "Send approved email notification or summary.",
    "input": {"recipient": "Email or recipient id.", "subject": "Email subject.", "body": "Approved email body.", "case_id": "Triage case id."},
    "output": {"sent": "Delivery status.", "message_id": "Email message id."},
    "action": "Deliver approved workflow messages by email.",
}

# TODO: Implement MCP/local adapter.
