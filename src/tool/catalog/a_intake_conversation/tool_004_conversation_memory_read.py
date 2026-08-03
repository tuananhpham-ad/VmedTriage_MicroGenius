"""Tool stub: read case conversation memory."""

TOOL_SPEC = {
    "id": 4,
    "name": "conversation_memory_read",
    "description": "Read prior conversation turns for an existing triage case.",
    "input": {"case_id": "Existing triage case id."},
    "output": {"conversation": "Ordered list of prior messages."},
    "action": "Recover context when the patient continues an earlier case.",
}

# TODO: Implement MCP/local adapter.
