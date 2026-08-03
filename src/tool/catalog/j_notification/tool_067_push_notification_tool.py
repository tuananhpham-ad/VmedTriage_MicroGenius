"""Tool stub: send push notification."""

TOOL_SPEC = {
    "id": 67,
    "name": "push_notification_tool",
    "description": "Send push notification to app, nurse dashboard, or patient device.",
    "input": {"recipient": "Recipient id.", "message": "Approved message.", "case_id": "Triage case id."},
    "output": {"sent": "Delivery status.", "notification_id": "Push notification id."},
    "action": "Notify users inside app-controlled channels.",
}

# TODO: Implement MCP/local adapter.
