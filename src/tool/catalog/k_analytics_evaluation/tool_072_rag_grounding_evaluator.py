"""Tool stub: evaluate RAG grounding."""

TOOL_SPEC = {
    "id": 72,
    "name": "rag_grounding_evaluator",
    "description": "Evaluate whether guideline-grounded outputs are supported by retrieved evidence.",
    "input": {"output": "Generated or proposed content.", "evidence": "Retrieved guideline evidence."},
    "output": {"grounded": "Grounding decision.", "issues": "Unsupported claims or missing evidence."},
    "action": "Check evidence support for clinician-facing summaries.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
