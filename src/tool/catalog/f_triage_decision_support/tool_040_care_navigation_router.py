"""Tool stub: route care navigation."""

TOOL_SPEC = {
    "id": 40,
    "name": "care_navigation_router",
    "description": "Route cases toward ER, urgent nurse review, routine appointment, or more information collection.",
    "input": {"case_context": "Structured case context and triage proposal."},
    "output": {"route": "Selected route.", "reason": "Routing rationale."},
    "action": "Select operational pathway without bypassing human approval.",
}

# TODO: Implement MCP/local adapter.
