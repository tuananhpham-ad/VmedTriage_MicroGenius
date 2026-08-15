"""Tool stub: detect self-harm risk."""

TOOL_SPEC = {
    "id": 24,
    "name": "self_harm_risk_detector",
    "description": "Detect self-harm, suicidal ideation, or crisis risk in patient messages.",
    "input": {"patient_message": "Raw or normalized user query."},
    "output": {"risk_detected": "Whether risk was detected.", "risk_level": "Estimated severity.", "evidence": "Text evidence."},
    "action": "Trigger crisis-safe routing and human escalation.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
