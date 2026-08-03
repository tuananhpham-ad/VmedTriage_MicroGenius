"""Tool stub: validate required triage checklist."""

TOOL_SPEC = {
    "id": 16,
    "name": "required_checklist_validator",
    "description": "Check whether required fields are present for the detected symptom group.",
    "input": {"structured_symptoms": "Structured symptom data."},
    "output": {"is_valid": "Validation status.", "missing_fields": "Required fields still missing."},
    "action": "Decide whether the case can proceed or needs follow-up questions.",
}

# TODO: Implement MCP/local adapter.
