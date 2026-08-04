"""Tool stub: check drug interactions."""

TOOL_SPEC = {
    "id": 32,
    "name": "drug_interaction_checker",
    "description": "Check potential interactions among current medications.",
    "input": {"medications": "Medication list."},
    "output": {"interactions": "Interaction findings with severity and explanation."},
    "action": "Provide clinician-facing medication safety context.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
