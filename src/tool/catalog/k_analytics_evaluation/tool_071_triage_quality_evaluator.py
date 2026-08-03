"""Tool stub: evaluate triage quality."""

TOOL_SPEC = {
    "id": 71,
    "name": "triage_quality_evaluator",
    "description": "Compare triage outputs against labeled test cases or nurse-reviewed outcomes.",
    "input": {"cases": "Evaluation cases.", "expected": "Expected labels or outcomes."},
    "output": {"scores": "Quality scores and error analysis."},
    "action": "Measure triage accuracy and identify failure modes.",
}

# TODO: Implement MCP/local adapter.
