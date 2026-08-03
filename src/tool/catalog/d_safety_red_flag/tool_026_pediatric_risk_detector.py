"""Tool stub: detect pediatric-specific risk."""

TOOL_SPEC = {
    "id": 26,
    "name": "pediatric_risk_detector",
    "description": "Apply pediatric-specific risk checks and lower escalation thresholds.",
    "input": {"age": "Patient age.", "structured_symptoms": "Structured symptoms."},
    "output": {"pediatric_risks": "Matched pediatric risk findings."},
    "action": "Adjust triage routing for children.",
}

# TODO: Implement MCP/local adapter.
