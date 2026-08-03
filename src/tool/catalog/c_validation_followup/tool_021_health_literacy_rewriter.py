"""Tool stub: rewrite text for patient readability."""

TOOL_SPEC = {
    "id": 21,
    "name": "health_literacy_rewriter",
    "description": "Rewrite medical questions or messages into simple patient-friendly wording.",
    "input": {"text": "Draft text.", "language": "Target language.", "reading_level": "Desired simplicity."},
    "output": {"rewritten_text": "Patient-friendly text."},
    "action": "Improve clarity without changing clinical meaning.",
}

# TODO: Implement MCP/local adapter.
