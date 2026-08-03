"""Tool stub: read case conversation memory."""

TOOL_SPEC = {
    "id": 4,
    "name": "conversation_memory_read",
    "description": "Read prior conversation turns for an existing triage case.",
    "input": {"case_id": "Existing triage case id."},
    "output": {"conversation": "Ordered list of prior messages."},
    "action": "Recover context when the patient continues an earlier case.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
