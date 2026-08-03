"""Tool stub: select fallback strategy."""

TOOL_SPEC = {
    "id": 81,
    "name": "fallback_strategy_selector",
    "description": "Choose a fallback when an MCP server is unavailable, unconfigured, or returns an unsafe result.",
    "input": {"failed_tool": "Tool name.", "error": "Failure detail.", "case_context": "Case context."},
    "output": {"fallback": "Selected fallback action.", "reason": "Fallback rationale."},
    "action": "Keep the pipeline safe and usable when external tools fail.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
