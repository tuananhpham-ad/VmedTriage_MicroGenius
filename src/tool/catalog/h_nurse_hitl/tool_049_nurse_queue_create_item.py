"""Tool stub: create nurse queue item."""

TOOL_SPEC = {
    "id": 49,
    "name": "nurse_queue_create_item",
    "description": "Create a nurse queue item from a triage case and proposal.",
    "input": {"case_id": "Triage case id.", "summary": "Handoff summary.", "proposal": "Triage proposal."},
    "output": {"queue_item": "Created nurse queue item."},
    "action": "Route the case into human-in-the-loop review.",
}

# TODO: Implement MCP/local adapter.
