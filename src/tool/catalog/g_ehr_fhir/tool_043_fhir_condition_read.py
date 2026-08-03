"""Tool stub: read FHIR conditions."""

TOOL_SPEC = {
    "id": 43,
    "name": "fhir_condition_read",
    "description": "Read active or historical conditions from FHIR.",
    "input": {"patient_id": "FHIR patient id.", "clinical_status": "Optional active/resolved filter."},
    "output": {"conditions": "FHIR Condition resources or normalized condition summaries."},
    "action": "Provide comorbidity context for triage risk.",
}

# TODO: Implement MCP/local adapter.
