"""Tool stub: write orchestration trace."""

TOOL_SPEC = {
    "id": 82,
    "name": "orchestration_trace_writer",
    "description": "Write a readable trace of orchestrator decisions, selected tools, arguments, results, and policy checks.",
    "input": {"case_id": "Triage case id.", "trace_event": "Trace event payload."},
    "output": {"trace_id": "Trace event id.", "stored": "Storage status."},
    "action": "Make orchestration behavior explainable and debuggable.",
}

# TODO: Implement MCP/local adapter.
