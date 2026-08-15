"""Tool stub: decide manual review requirement."""

TOOL_SPEC = {
    "id": 39,
    "name": "manual_review_decider",
    "description": "Decide whether a clinical or patient-facing output requires human review.",
    "input": {"proposal": "Triage proposal.", "tool_results": "Relevant tool outputs.", "policy": "Safety policy context."},
    "output": {"requires_review": "Review decision.", "reason": "Policy rationale."},
    "action": "Enforce HITL before clinical output reaches the patient.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
