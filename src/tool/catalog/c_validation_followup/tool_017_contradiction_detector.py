"""Tool stub: detect contradictory symptom data."""

TOOL_SPEC = {
    "id": 17,
    "name": "contradiction_detector",
    "description": "Detect conflicting or impossible values in structured triage data.",
    "input": {"structured_symptoms": "Structured symptom data and prior conversation."},
    "output": {"contradictions": "Detected contradiction issues."},
    "action": "Flag inconsistent data before triage proposal.",
}

# TODO: Implement MCP/local adapter.
