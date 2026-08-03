"""Tool stub: write triage audit log."""

TOOL_SPEC = {
    "id": 57,
    "name": "triage_audit_log_write",
    "description": "Write an immutable triage audit event to an external audit store.",
    "input": {"case_id": "Triage case id.", "event_type": "Audit event type.", "actor_role": "Actor role.", "payload": "Event payload."},
    "output": {"event_id": "Audit event id.", "stored": "Storage status."},
    "action": "Record traceable workflow events for compliance.",
}

# TODO: Implement MCP/local adapter.
