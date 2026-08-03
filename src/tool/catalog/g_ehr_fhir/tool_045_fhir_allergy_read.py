"""Tool stub: read FHIR allergies."""

TOOL_SPEC = {
    "id": 45,
    "name": "fhir_allergy_read",
    "description": "Read allergy and intolerance records from FHIR.",
    "input": {"patient_id": "FHIR patient id."},
    "output": {"allergies": "FHIR AllergyIntolerance resources or normalized allergies."},
    "action": "Provide allergy context for handoff and safety checks.",
}

# TODO: Implement MCP/local adapter.
