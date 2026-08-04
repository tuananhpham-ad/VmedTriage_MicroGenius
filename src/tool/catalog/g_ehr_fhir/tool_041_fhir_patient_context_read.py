"""Tool stub: read FHIR patient context."""

TOOL_SPEC = {
    "id": 41,
    "name": "fhir_patient_context_read",
    "description": "Read limited patient context from an EHR/FHIR server for nurse review.",
    "input": {"patient_id": "FHIR patient id.", "resources": "FHIR resource types to read."},
    "output": {"bundle": "FHIR Bundle.", "resource_count": "Number of resources.", "redacted": "Whether data was redacted."},
    "action": "Provide authenticated nurse-facing EHR context.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
