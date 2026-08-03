"""Tool stub: retrieve local protocols."""

TOOL_SPEC = {
    "id": 30,
    "name": "local_protocol_retriever",
    "description": "Retrieve hospital or clinic-specific triage protocols.",
    "input": {"symptom_group": "Symptom group.", "site_id": "Clinical site identifier."},
    "output": {"protocols": "Relevant local protocols."},
    "action": "Use local workflow rules before generic guidance.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
