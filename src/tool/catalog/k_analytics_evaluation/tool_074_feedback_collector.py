"""Tool stub: collect feedback."""

TOOL_SPEC = {
    "id": 74,
    "name": "feedback_collector",
    "description": "Collect structured feedback from nurse, clinician, or patient.",
    "input": {"case_id": "Triage case id.", "actor_role": "Feedback source role.", "feedback": "Feedback payload."},
    "output": {"feedback_id": "Stored feedback id.", "stored": "Storage status."},
    "action": "Gather data for product and clinical quality improvement.",
}

# TODO: Implement MCP/local adapter.
