"""Tool stub: create FHIR encounter."""

TOOL_SPEC = {
    "id": 46,
    "name": "fhir_encounter_create",
    "description": "Create a triage encounter in an EHR/FHIR system.",
    "input": {"patient_id": "FHIR patient id.", "case_id": "Triage case id.", "encounter_payload": "Encounter fields."},
    "output": {"encounter_id": "Created encounter id.", "created": "Creation status."},
    "action": "Open an EHR encounter for reviewed triage workflow.",
}

# TODO: Implement MCP/local adapter.
