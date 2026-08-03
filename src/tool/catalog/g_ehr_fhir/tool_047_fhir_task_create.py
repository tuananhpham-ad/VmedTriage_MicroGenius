"""Tool stub: create FHIR task."""

TOOL_SPEC = {
    "id": 47,
    "name": "fhir_task_create",
    "description": "Create a FHIR Task for nurse or clinician follow-up.",
    "input": {"patient_id": "FHIR patient id.", "case_id": "Triage case id.", "task_payload": "Task fields."},
    "output": {"task_id": "Created task id.", "created": "Creation status."},
    "action": "Connect triage case to operational clinical work queue.",
}

# TODO: Implement MCP/local adapter.
