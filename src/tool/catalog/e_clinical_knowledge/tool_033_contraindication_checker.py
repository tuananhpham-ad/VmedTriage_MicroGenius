"""Tool stub: check contraindications."""

TOOL_SPEC = {
    "id": 33,
    "name": "contraindication_checker",
    "description": "Check contraindications based on allergies, pregnancy, conditions, or medications.",
    "input": {"candidate_action": "Clinical action under review.", "patient_context": "Relevant patient context."},
    "output": {"contraindications": "Contraindication findings."},
    "action": "Warn clinicians before approving advice or workflow actions.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
