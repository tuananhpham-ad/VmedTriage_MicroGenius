"""Tool stub: lookup ICD-10 concepts."""

TOOL_SPEC = {
    "id": 10,
    "name": "icd10_lookup",
    "description": "Map symptoms or clinician-reviewed conditions to ICD-10 codes for reporting.",
    "input": {"term": "Clinical term.", "language": "Language code."},
    "output": {"codes": "Candidate ICD-10 codes and descriptions."},
    "action": "Support coding/reporting after clinical review; not for diagnosis.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
