"""Tool stub: generate safe follow-up questions."""

TOOL_SPEC = {
    "id": 19,
    "name": "follow_up_question_generator",
    "description": "Generate patient-safe follow-up questions for missing or unclear triage fields.",
    "input": {"missing_fields": "Fields to ask about.", "symptom_group": "Detected symptom group."},
    "output": {"questions": "Ordered patient-facing follow-up questions."},
    "action": "Collect enough information without giving clinical advice.",
}

# TODO: Implement MCP/local adapter.
