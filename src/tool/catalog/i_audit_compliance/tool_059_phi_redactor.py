"""Tool stub: redact protected health information."""

TOOL_SPEC = {
    "id": 59,
    "name": "phi_redactor",
    "description": "Redact protected health information before sending data to external tools or logs.",
    "input": {"text": "Text to redact.", "policy": "Redaction policy."},
    "output": {"redacted_text": "Redacted text.", "redactions": "Redaction metadata."},
    "action": "Reduce privacy risk in external calls and audit logs.",
}

# TODO: Implement MCP/local adapter.
