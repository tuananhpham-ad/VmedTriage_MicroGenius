"""Tool stub: extract allergies."""

TOOL_SPEC = {
    "id": 13,
    "name": "allergy_extraction_tool",
    "description": "Extract allergies and adverse reactions from patient text or EHR snippets.",
    "input": {"text": "Patient text or clinical note."},
    "output": {"allergies": "Extracted allergy entries with substance and reaction."},
    "action": "Identify allergy context for nurse handoff and safety checks.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
