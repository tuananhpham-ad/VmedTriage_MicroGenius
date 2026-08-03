"""Tool stub: prioritize follow-up questions."""

TOOL_SPEC = {
    "id": 20,
    "name": "question_prioritizer",
    "description": "Rank follow-up questions by clinical urgency and user burden.",
    "input": {"questions": "Candidate questions.", "case_context": "Structured case context."},
    "output": {"prioritized_questions": "Short ordered list of questions."},
    "action": "Ask the most important questions first.",
}

# TODO: Implement MCP/local adapter.
