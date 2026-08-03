"""Tool stub: audit MCP tool calls."""

TOOL_SPEC = {
    "id": 58,
    "name": "tool_call_audit_logger",
    "description": "Log every MCP tool call with input, output, policy, latency, and result status.",
    "input": {"tool_name": "Tool name.", "arguments": "Tool arguments.", "result": "Tool result.", "policy": "Tool policy."},
    "output": {"event_id": "Audit event id.", "stored": "Storage status."},
    "action": "Make tool orchestration auditable.",
}

# TODO: Implement MCP/local adapter.
