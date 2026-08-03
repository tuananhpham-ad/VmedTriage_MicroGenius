"""Tool stub: extract allergies."""

TOOL_SPEC = {
    "id": 13,
    "name": "allergy_extraction_tool",
    "description": "Extract allergies and adverse reactions from patient text or EHR snippets.",
    "input": {"text": "Patient text or clinical note."},
    "output": {"allergies": "Extracted allergy entries with substance and reaction."},
    "action": "Identify allergy context for nurse handoff and safety checks.",
}

# TODO: Implement MCP/local adapter.
