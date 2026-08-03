"""Tool stub: read FHIR medications."""

TOOL_SPEC = {
    "id": 44,
    "name": "fhir_medication_read",
    "description": "Read current medications from FHIR.",
    "input": {"patient_id": "FHIR patient id.", "status": "Optional medication status filter."},
    "output": {"medications": "FHIR MedicationStatement resources or normalized medications."},
    "action": "Provide medication context for nurse review.",
}

# TODO: Implement MCP/local adapter.
