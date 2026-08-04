"""Tool stub: lookup SNOMED CT concepts."""

TOOL_SPEC = {
    "id": 9,
    "name": "snomed_concept_lookup",
    "description": "Normalize mapped symptoms to SNOMED CT concepts through a terminology service.",
    "input": {"term": "Clinical term.", "language": "Language code.", "system": "Terminology system URI."},
    "output": {"concepts": "Candidate SNOMED concepts with code, display, and confidence."},
    "action": "Standardize symptom terminology for downstream matching.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
