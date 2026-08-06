"""Tool stub: rewrite text for patient readability."""

TOOL_SPEC = {
    "id": 21,
    "name": "health_literacy_rewriter",
    "description": "Rewrite medical questions or messages into simple patient-friendly wording.",
    "input": {"text": "Draft text.", "language": "Target language.", "reading_level": "Desired simplicity."},
    "output": {"rewritten_text": "Patient-friendly text."},
    "action": "Improve clarity without changing clinical meaning.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
