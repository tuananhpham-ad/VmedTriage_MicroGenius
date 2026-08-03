"""Tool stub: update case status."""

TOOL_SPEC = {
    "id": 56,
    "name": "case_status_updater",
    "description": "Update triage case status such as collecting, awaiting approval, approved, rejected, or escalated.",
    "input": {"case_id": "Triage case id.", "status": "New case status.", "reason": "Status update reason."},
    "output": {"case_id": "Case id.", "status": "Updated status."},
    "action": "Keep workflow state synchronized after each decision.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
