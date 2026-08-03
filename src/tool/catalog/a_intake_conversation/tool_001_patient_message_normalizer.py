"""Tool stub: normalize noisy patient text."""

TOOL_SPEC = {
    "id": 1,
    "name": "patient_message_normalizer",
    "description": "Normalize typos, no-accent Vietnamese, mixed slang, and whitespace in patient messages.",
    "input": {"patient_message": "Raw user query from patient chat."},
    "output": {"normalized_message": "Cleaned patient message for downstream tools."},
    "action": "Clean and normalize text before semantic extraction.",
}

# TODO: Implement MCP/local adapter.
