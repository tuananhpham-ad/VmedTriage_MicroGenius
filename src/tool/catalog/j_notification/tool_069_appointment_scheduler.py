"""Tool stub: schedule appointment."""

TOOL_SPEC = {
    "id": 69,
    "name": "appointment_scheduler",
    "description": "Schedule a clinic appointment after user confirmation and policy approval.",
    "input": {"patient_id": "Patient id.", "case_id": "Triage case id.", "slot": "Requested appointment slot.", "reason": "Visit reason."},
    "output": {"appointment_id": "Appointment id.", "scheduled": "Scheduling status."},
    "action": "Create appointment workflow after human or user confirmation.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
