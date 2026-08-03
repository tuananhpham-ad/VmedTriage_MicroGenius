"""Tool stub: calculate queue priority score."""

TOOL_SPEC = {
    "id": 38,
    "name": "priority_score_calculator",
    "description": "Calculate a queue priority score from red flags, risk factors, validation state, and wait time.",
    "input": {"case_context": "Full structured case context."},
    "output": {"priority_score": "Numeric score.", "priority_bucket": "Queue bucket."},
    "action": "Rank cases in nurse queue.",
}

# TODO: Implement MCP/local adapter.
