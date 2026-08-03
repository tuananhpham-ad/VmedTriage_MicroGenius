"""Tool stub: page on-call staff."""

TOOL_SPEC = {
    "id": 68,
    "name": "on_call_paging_tool",
    "description": "Page on-call clinical staff for emergency or escalation workflows.",
    "input": {"case_id": "Triage case id.", "priority": "Page priority.", "message": "Approved page message.", "team": "On-call team."},
    "output": {"page_id": "Page id.", "delivered": "Delivery status."},
    "action": "Escalate urgent reviewed cases to on-call staff.",
}

# TODO: Implement MCP/local adapter.
