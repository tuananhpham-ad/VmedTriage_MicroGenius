"""Tool stub: list available tools."""

TOOL_SPEC = {
    "id": 76,
    "name": "tool_registry_list",
    "description": "List available MCP tool descriptors and local tool capabilities.",
    "input": {"filters": "Optional category or risk filters."},
    "output": {"tools": "Available tool descriptors."},
    "action": "Let the orchestrator discover callable tools.",
}

# TODO: Implement MCP/local adapter.
