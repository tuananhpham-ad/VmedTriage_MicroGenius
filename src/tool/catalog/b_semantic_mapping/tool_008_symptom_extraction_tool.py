"""Tool stub: extract structured symptoms."""

TOOL_SPEC = {
    "id": 8,
    "name": "symptom_extraction_tool",
    "description": "Extract chief complaint, onset, severity, location, radiation, and associated symptoms from free text.",
    "input": {"patient_message": "Normalized patient message.", "conversation": "Optional prior case context."},
    "output": {"structured_symptoms": "Normalized symptom fields with confidence."},
    "action": "Convert patient text into structured triage data.",
}

# TODO: Implement MCP/local adapter.
