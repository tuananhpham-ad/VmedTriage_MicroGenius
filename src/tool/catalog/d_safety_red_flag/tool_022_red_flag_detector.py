"""Tool stub: detect red flags."""

TOOL_SPEC = {
    "id": 22,
    "name": "red_flag_detector",
    "description": "Detect emergency red flags such as chest pain with shortness of breath, stroke signs, seizure, or loss of consciousness.",
    "input": {"structured_symptoms": "Structured symptom data."},
    "output": {"red_flags": "Matched red-flag findings."},
    "action": "Route urgent cases to high-priority human review.",
}

# TODO: Implement MCP/local adapter.
