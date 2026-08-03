"""Tool stub: list available tools."""

TOOL_SPEC = {
    "id": 76,
    "name": "tool_registry_list",
    "description": "List available MCP tool descriptors and local tool capabilities.",
    "input": {"filters": "Optional category or risk filters."},
    "output": {"tools": "Available tool descriptors."},
    "action": "Let the orchestrator discover callable tools.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
