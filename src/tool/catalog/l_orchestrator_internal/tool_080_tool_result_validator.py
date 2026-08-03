"""Tool stub: validate tool result."""

TOOL_SPEC = {
    "id": 80,
    "name": "tool_result_validator",
    "description": "Validate MCP tool output against expected schema before it affects case state.",
    "input": {"tool_descriptor": "Tool descriptor.", "result": "Raw tool result."},
    "output": {"valid": "Validation decision.", "normalized_result": "Schema-normalized result.", "errors": "Validation errors."},
    "action": "Prevent malformed external data from entering the pipeline.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
