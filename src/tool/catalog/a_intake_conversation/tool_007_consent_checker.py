"""Tool stub: check patient consent."""

TOOL_SPEC = {
    "id": 7,
    "name": "consent_checker",
    "description": "Check whether the user has granted consent for storing or processing health information.",
    "input": {"case_id": "Triage case id.", "patient_id": "Optional patient id.", "scope": "Processing scope to check."},
    "output": {"has_consent": "Consent decision.", "missing_scope": "Missing consent scope if any."},
    "action": "Gate data processing and external tool calls by consent policy.",
}

# TODO: Implement MCP/local adapter.
