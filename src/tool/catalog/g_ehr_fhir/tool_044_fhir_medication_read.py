"""Tool stub: read FHIR medications."""

TOOL_SPEC = {
    "id": 44,
    "name": "fhir_medication_read",
    "description": "Read current medications from FHIR.",
    "input": {"patient_id": "FHIR patient id.", "status": "Optional medication status filter."},
    "output": {"medications": "FHIR MedicationStatement resources or normalized medications."},
    "action": "Provide medication context for nurse review.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
