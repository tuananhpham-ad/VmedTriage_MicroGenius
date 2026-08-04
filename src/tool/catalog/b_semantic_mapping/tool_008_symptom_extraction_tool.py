"""Tool stub: extract structured symptoms."""

TOOL_SPEC = {
    "id": 8,
    "name": "symptom_extraction_tool",
    "description": "Extract chief complaint, onset, severity, location, radiation, and associated symptoms from free text.",
    "input": {"patient_message": "Normalized patient message.", "conversation": "Optional prior case context."},
    "output": {"structured_symptoms": "Normalized symptom fields with confidence."},
    "action": "Convert patient text into structured triage data.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
