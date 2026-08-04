"""Tool stub: prioritize follow-up questions."""

TOOL_SPEC = {
    "id": 20,
    "name": "question_prioritizer",
    "description": "Rank follow-up questions by clinical urgency and user burden.",
    "input": {"questions": "Candidate questions.", "case_context": "Structured case context."},
    "output": {"prioritized_questions": "Short ordered list of questions."},
    "action": "Ask the most important questions first.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
