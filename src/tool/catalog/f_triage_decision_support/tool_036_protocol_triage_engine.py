"""Tool stub: propose triage priority from protocols."""

TOOL_SPEC = {
    "id": 36,
    "name": "protocol_triage_engine",
    "description": "Match structured symptom data against protocol rules to create a triage proposal.",
    "input": {"structured_symptoms": "Structured symptoms.", "validation": "Validation result.", "red_flags": "Red flag findings."},
    "output": {"triage_proposal": "Priority, protocol id, reason, confidence, and review requirement."},
    "action": "Generate a clinician-facing proposal that still requires human review.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
