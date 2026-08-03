"""Tool stub: search clinical guidelines."""

TOOL_SPEC = {
    "id": 29,
    "name": "clinical_guideline_search",
    "description": "Search approved clinical triage protocols or guideline documents.",
    "input": {"symptom_group": "Symptom group.", "query": "Search query.", "red_flags": "Optional red flag codes."},
    "output": {"matches": "Guideline matches with title, excerpt, priority hint, and source."},
    "action": "Ground clinician-facing triage support in approved guidance.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
