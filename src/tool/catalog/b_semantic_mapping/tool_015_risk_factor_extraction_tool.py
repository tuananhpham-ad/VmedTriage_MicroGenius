"""Tool stub: extract risk factors."""

TOOL_SPEC = {
    "id": 15,
    "name": "risk_factor_extraction_tool",
    "description": "Extract triage risk factors such as age, pregnancy, cardiac disease, diabetes, or immunosuppression.",
    "input": {"text": "Patient message, profile, or clinical note."},
    "output": {"risk_factors": "Extracted risk factor list with confidence."},
    "action": "Provide risk context for validation and triage routing.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
