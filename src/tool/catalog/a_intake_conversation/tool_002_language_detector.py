"""Tool stub: detect patient message language."""

TOOL_SPEC = {
    "id": 2,
    "name": "language_detector",
    "description": "Detect whether the patient query is Vietnamese, English, or mixed language.",
    "input": {"text": "Patient message or clinical text."},
    "output": {"language": "Detected language code.", "confidence": "Detection confidence."},
    "action": "Choose prompts, terminology systems, and translation paths.",
}

async def execute(arguments, context=None):
    """Execute this tool through the shared catalog runtime."""
    from src.tool.catalog.framework import catalog_tool

    return await catalog_tool(TOOL_SPEC)(arguments, context)
