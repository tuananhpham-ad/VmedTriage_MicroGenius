"""Tool stub: detect abuse or violence risk."""

TOOL_SPEC = {
    "id": 25,
    "name": "abuse_or_violence_detector",
    "description": "Detect signs of abuse, violence, coercion, or immediate personal safety risk.",
    "input": {"patient_message": "Patient text and optional context."},
    "output": {"risk_detected": "Whether risk was detected.", "risk_type": "Risk category.", "evidence": "Text evidence."},
    "action": "Escalate to human review and safety protocol when needed.",
}

# TODO: Implement MCP/local adapter.
