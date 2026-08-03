"""Tool stub: submit human review decision."""

TOOL_SPEC = {
    "id": 53,
    "name": "human_review_submit",
    "description": "Submit nurse action: approve, edit, reject, escalate, or ask for more information.",
    "input": {"case_id": "Triage case id.", "action": "Review action.", "approved_response": "Optional patient response.", "nurse_notes": "Optional notes."},
    "output": {"case_id": "Case id.", "status": "New case status.", "patient_visible_response": "Approved patient response if any."},
    "action": "Apply HITL decision to a triage case.",
}

# TODO: Implement MCP/local adapter.
