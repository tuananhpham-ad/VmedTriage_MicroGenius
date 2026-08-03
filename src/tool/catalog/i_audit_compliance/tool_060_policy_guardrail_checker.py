"""Tool stub: check medical safety policy."""

TOOL_SPEC = {
    "id": 60,
    "name": "policy_guardrail_checker",
    "description": "Detect policy violations such as diagnosis, prescribing, or unsafe delay of emergency care.",
    "input": {"draft_output": "Candidate patient or clinician-facing text.", "case_context": "Structured case context."},
    "output": {"allowed": "Whether output is allowed.", "violations": "Detected policy violations."},
    "action": "Block unsafe outputs before they are shown or saved.",
}

# TODO: Implement MCP/local adapter.
