"""Tool stub: build tool arguments."""

TOOL_SPEC = {
    "id": 79,
    "name": "tool_argument_builder",
    "description": "Build schema-valid MCP tool arguments from AgentState and case context.",
    "input": {"tool_descriptor": "Target tool descriptor.", "agent_state": "Current agent state.", "case_context": "Case context."},
    "output": {"arguments": "Schema-shaped tool arguments.", "missing_inputs": "Inputs still missing."},
    "action": "Prepare safe structured arguments for tool calls.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
