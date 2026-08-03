"""Tool stub: extract risk factors."""

TOOL_SPEC = {
    "id": 15,
    "name": "risk_factor_extraction_tool",
    "description": "Extract triage risk factors such as age, pregnancy, cardiac disease, diabetes, or immunosuppression.",
    "input": {"text": "Patient message, profile, or clinical note."},
    "output": {"risk_factors": "Extracted risk factor list with confidence."},
    "action": "Provide risk context for validation and triage routing.",
}

# TODO: Implement MCP/local adapter.
