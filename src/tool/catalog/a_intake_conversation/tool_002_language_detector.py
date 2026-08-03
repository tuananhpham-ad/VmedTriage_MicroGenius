"""Tool stub: detect patient message language."""

TOOL_SPEC = {
    "id": 2,
    "name": "language_detector",
    "description": "Detect whether the patient query is Vietnamese, English, or mixed language.",
    "input": {"text": "Patient message or clinical text."},
    "output": {"language": "Detected language code.", "confidence": "Detection confidence."},
    "action": "Choose prompts, terminology systems, and translation paths.",
}

# TODO: Implement MCP/local adapter.
