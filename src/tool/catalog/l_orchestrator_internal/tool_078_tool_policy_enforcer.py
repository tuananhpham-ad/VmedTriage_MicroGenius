"""Tool stub: enforce tool policy."""

TOOL_SPEC = {
    "id": 78,
    "name": "tool_policy_enforcer",
    "description": "Check risk level, human approval requirement, and patient visibility before a tool call.",
    "input": {"tool_descriptor": "Tool descriptor.", "arguments": "Planned arguments.", "case_context": "Case context."},
    "output": {"allowed": "Whether tool call is allowed.", "reason": "Policy rationale."},
    "action": "Prevent unsafe or unauthorized MCP tool calls.",
}

# TODO: Implement MCP/local adapter.
