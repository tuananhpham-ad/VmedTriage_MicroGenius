"""Tool stub: extract medications."""

TOOL_SPEC = {
    "id": 14,
    "name": "medication_extraction_tool",
    "description": "Extract current medications, dose mentions, and timing from patient text.",
    "input": {"text": "Patient text or clinical note."},
    "output": {"medications": "Extracted medication entries."},
    "action": "Identify medication context for nurse review and risk checks.",
}

# TODO: Implement MCP/local adapter.
