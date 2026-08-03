"""Tool stub: read patient profile."""

TOOL_SPEC = {
    "id": 6,
    "name": "patient_profile_read",
    "description": "Read patient demographics and high-level profile context such as age, sex, pregnancy, and known risks.",
    "input": {"patient_id": "Patient identifier or case-linked patient reference."},
    "output": {"profile": "Limited patient profile fields approved for triage."},
    "action": "Provide context that can change triage risk thresholds.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
