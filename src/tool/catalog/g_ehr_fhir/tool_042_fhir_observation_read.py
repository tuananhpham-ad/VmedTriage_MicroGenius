"""Tool stub: read FHIR observations."""

TOOL_SPEC = {
    "id": 42,
    "name": "fhir_observation_read",
    "description": "Read recent vital signs or lab observations from FHIR.",
    "input": {"patient_id": "FHIR patient id.", "codes": "Optional LOINC or observation codes.", "date_range": "Optional date filter."},
    "output": {"observations": "FHIR Observation resources or normalized summaries."},
    "action": "Add objective clinical context for nurse review.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
