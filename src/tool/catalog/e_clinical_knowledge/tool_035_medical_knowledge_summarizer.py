"""Tool stub: summarize medical knowledge."""

TOOL_SPEC = {
    "id": 35,
    "name": "medical_knowledge_summarizer",
    "description": "Summarize long guideline or protocol content for clinician review.",
    "input": {"documents": "Guideline excerpts or documents.", "case_context": "Structured case context."},
    "output": {"summary": "Clinician-facing concise summary.", "citations": "Source references."},
    "action": "Reduce reading burden while preserving source grounding.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
