"""Tool stub: generate nurse handoff summary."""

TOOL_SPEC = {
    "id": 55,
    "name": "handoff_summary_generator",
    "description": "Generate a concise nurse-facing summary of chief complaint, severity, missing data, red flags, and proposal.",
    "input": {"case_context": "Structured case data, validation, red flags, and proposal."},
    "output": {"summary": "Nurse-facing handoff summary."},
    "action": "Prepare clinical review context for the nurse dashboard.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
