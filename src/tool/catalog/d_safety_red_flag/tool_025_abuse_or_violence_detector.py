"""Tool stub: detect abuse or violence risk."""

TOOL_SPEC = {
    "id": 25,
    "name": "abuse_or_violence_detector",
    "description": "Detect signs of abuse, violence, coercion, or immediate personal safety risk.",
    "input": {"patient_message": "Patient text and optional context."},
    "output": {"risk_detected": "Whether risk was detected.", "risk_type": "Risk category.", "evidence": "Text evidence."},
    "action": "Escalate to human review and safety protocol when needed.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
