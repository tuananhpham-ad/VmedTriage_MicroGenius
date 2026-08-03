"""Tool stub: detect elderly-specific risk."""

TOOL_SPEC = {
    "id": 28,
    "name": "elderly_risk_detector",
    "description": "Apply elderly-specific risk checks and atypical presentation safeguards.",
    "input": {"age": "Patient age.", "structured_symptoms": "Structured symptoms.", "profile": "Optional patient profile."},
    "output": {"elderly_risks": "Matched elderly risk findings."},
    "action": "Adjust triage routing for older adults.",
}

# TODO: Implement MCP/local adapter.
