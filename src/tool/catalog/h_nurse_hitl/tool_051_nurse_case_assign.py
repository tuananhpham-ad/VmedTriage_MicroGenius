"""Tool stub: assign case to nurse."""

TOOL_SPEC = {
    "id": 51,
    "name": "nurse_case_assign",
    "description": "Assign a triage case to a specific nurse or clinical reviewer.",
    "input": {"case_id": "Triage case id.", "nurse_id": "Reviewer id."},
    "output": {"assigned": "Assignment status.", "assignee": "Assigned nurse id."},
    "action": "Coordinate ownership of nurse review work.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
