"""Tool stub: create FHIR encounter."""

TOOL_SPEC = {
    "id": 46,
    "name": "fhir_encounter_create",
    "description": "Create a triage encounter in an EHR/FHIR system.",
    "input": {"patient_id": "FHIR patient id.", "case_id": "Triage case id.", "encounter_payload": "Encounter fields."},
    "output": {"encounter_id": "Created encounter id.", "created": "Creation status."},
    "action": "Open an EHR encounter for reviewed triage workflow.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
