"""Tool stub: generate nurse handoff summary."""

TOOL_SPEC = {
    "id": 55,
    "name": "handoff_summary_generator",
    "description": "Generate a concise nurse-facing summary of chief complaint, severity, missing data, red flags, and proposal.",
    "input": {"case_context": "Structured case data, validation, red flags, and proposal."},
    "output": {"summary": "Nurse-facing handoff summary."},
    "action": "Prepare clinical review context for the nurse dashboard.",
}

# TODO: Implement MCP/local adapter.
