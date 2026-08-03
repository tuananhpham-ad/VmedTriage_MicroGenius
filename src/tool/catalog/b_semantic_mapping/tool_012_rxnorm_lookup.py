"""Tool stub: lookup RxNorm medications."""

TOOL_SPEC = {
    "id": 12,
    "name": "rxnorm_lookup",
    "description": "Normalize medication names to RxNorm concepts.",
    "input": {"medication_name": "Medication name from user or EHR."},
    "output": {"concepts": "Candidate RxNorm concepts."},
    "action": "Standardize medication data for interaction or risk checks.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
