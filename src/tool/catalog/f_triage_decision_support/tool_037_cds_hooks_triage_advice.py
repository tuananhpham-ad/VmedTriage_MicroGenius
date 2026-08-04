"""Tool stub: call CDS Hooks triage service."""

TOOL_SPEC = {
    "id": 37,
    "name": "cds_hooks_triage_advice",
    "description": "Request CDS Hooks cards for clinician-facing triage decision support.",
    "input": {"hook": "CDS hook name.", "context": "CDS context.", "prefetch": "Optional prefetch data."},
    "output": {"cards": "CDS Hooks cards."},
    "action": "Cross-check local proposal with external CDS service.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
