"""Tool stub: lookup LOINC observations."""

TOOL_SPEC = {
    "id": 11,
    "name": "loinc_lookup",
    "description": "Map lab or observation names to LOINC codes.",
    "input": {"term": "Observation or lab name."},
    "output": {"codes": "Candidate LOINC codes and displays."},
    "action": "Normalize observations retrieved from FHIR or user input.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
