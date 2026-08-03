"""Tool stub: write FHIR document reference."""

TOOL_SPEC = {
    "id": 48,
    "name": "fhir_document_reference_write",
    "description": "Write nurse-approved handoff summary as a FHIR DocumentReference.",
    "input": {"patient_id": "FHIR patient id.", "case_id": "Triage case id.", "document": "Approved clinical document."},
    "output": {"document_reference_id": "Created document reference id.", "stored": "Storage status."},
    "action": "Persist approved triage documentation to EHR.",
}

# TODO: Implement MCP/local adapter.
