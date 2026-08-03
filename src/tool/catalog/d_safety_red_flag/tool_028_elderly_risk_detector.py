"""Tool stub: detect elderly-specific risk."""

TOOL_SPEC = {
    "id": 28,
    "name": "elderly_risk_detector",
    "description": "Apply elderly-specific risk checks and atypical presentation safeguards.",
    "input": {"age": "Patient age.", "structured_symptoms": "Structured symptoms.", "profile": "Optional patient profile."},
    "output": {"elderly_risks": "Matched elderly risk findings."},
    "action": "Adjust triage routing for older adults.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
