"""Tool stub: schedule appointment."""

TOOL_SPEC = {
    "id": 69,
    "name": "appointment_scheduler",
    "description": "Schedule a clinic appointment after user confirmation and policy approval.",
    "input": {"patient_id": "Patient id.", "case_id": "Triage case id.", "slot": "Requested appointment slot.", "reason": "Visit reason."},
    "output": {"appointment_id": "Appointment id.", "scheduled": "Scheduling status."},
    "action": "Create appointment workflow after human or user confirmation.",
}

# TODO: Implement MCP/local adapter.
