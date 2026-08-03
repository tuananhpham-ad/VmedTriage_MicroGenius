"""Tool stub: detect contradictory symptom data."""

TOOL_SPEC = {
    "id": 17,
    "name": "contradiction_detector",
    "description": "Detect conflicting or impossible values in structured triage data.",
    "input": {"structured_symptoms": "Structured symptom data and prior conversation."},
    "output": {"contradictions": "Detected contradiction issues."},
    "action": "Flag inconsistent data before triage proposal.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
