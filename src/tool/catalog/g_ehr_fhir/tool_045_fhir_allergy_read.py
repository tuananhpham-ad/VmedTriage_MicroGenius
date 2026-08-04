"""Tool stub: read FHIR allergies."""

TOOL_SPEC = {
    "id": 45,
    "name": "fhir_allergy_read",
    "description": "Read allergy and intolerance records from FHIR.",
    "input": {"patient_id": "FHIR patient id."},
    "output": {"allergies": "FHIR AllergyIntolerance resources or normalized allergies."},
    "action": "Provide allergy context for handoff and safety checks.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
