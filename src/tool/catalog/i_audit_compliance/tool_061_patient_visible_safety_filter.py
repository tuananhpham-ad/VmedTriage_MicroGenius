"""Tool stub: filter patient-visible response."""

TOOL_SPEC = {
    "id": 61,
    "name": "patient_visible_safety_filter",
    "description": "Check patient-facing response for unsafe clinical advice, missing disclaimers, or unapproved content.",
    "input": {"response": "Candidate patient response.", "case_context": "Structured case context.", "approval_state": "Human approval state."},
    "output": {"safe_response": "Filtered response.", "blocked": "Whether response was blocked.", "issues": "Safety issues."},
    "action": "Ensure only safe and approved text reaches the patient.",
}

# TODO: Implement MCP/local adapter.
