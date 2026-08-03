"""Tool stub: create nurse queue item."""

TOOL_SPEC = {
    "id": 49,
    "name": "nurse_queue_create_item",
    "description": "Create a nurse queue item from a triage case and proposal.",
    "input": {"case_id": "Triage case id.", "summary": "Handoff summary.", "proposal": "Triage proposal."},
    "output": {"queue_item": "Created nurse queue item."},
    "action": "Route the case into human-in-the-loop review.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
