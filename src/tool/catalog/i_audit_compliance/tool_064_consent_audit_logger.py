"""Tool stub: audit consent events."""

TOOL_SPEC = {
    "id": 64,
    "name": "consent_audit_logger",
    "description": "Log consent grant, refusal, or revocation events.",
    "input": {"case_id": "Triage case id.", "patient_id": "Patient id.", "consent_event": "Consent event payload."},
    "output": {"event_id": "Audit event id.", "stored": "Storage status."},
    "action": "Maintain traceable consent history.",
}

# TODO: Implement MCP/local adapter.
