"""Tool stub: match capability to user intent."""

TOOL_SPEC = {
    "id": 77,
    "name": "tool_capability_matcher",
    "description": "Match user intent, case state, and policy needs to candidate tools.",
    "input": {"intent": "Detected intent.", "case_context": "Current case state.", "available_tools": "Tool descriptors."},
    "output": {"candidate_tools": "Ranked candidate tools with reasons."},
    "action": "Choose tools for the next orchestration step.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
