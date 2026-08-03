"""Tool stub: classify emergency escalation."""

TOOL_SPEC = {
    "id": 23,
    "name": "emergency_escalation_classifier",
    "description": "Classify whether a case should be treated as Emergency, Urgent, Routine, or Manual review.",
    "input": {"structured_symptoms": "Structured symptoms.", "red_flags": "Red-flag findings.", "risk_factors": "Risk factors."},
    "output": {"priority": "Escalation priority.", "reason": "Classifier rationale."},
    "action": "Create a safety-first routing signal for the orchestrator.",
}

# TODO: Implement MCP/local adapter.
