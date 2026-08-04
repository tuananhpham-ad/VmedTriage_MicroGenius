"""Tool stub: write case conversation memory."""

TOOL_SPEC = {
    "id": 5,
    "name": "conversation_memory_write",
    "description": "Append a patient, nurse, system, or tool message to case memory.",
    "input": {"case_id": "Triage case id.", "role": "Actor role.", "content": "Message content."},
    "output": {"stored": "Whether the message was stored.", "message_id": "Stored message id."},
    "action": "Persist conversation continuity and audit context.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
