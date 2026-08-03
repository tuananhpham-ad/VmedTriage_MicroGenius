"""Tool stub: search clinical guidelines."""

TOOL_SPEC = {
    "id": 29,
    "name": "clinical_guideline_search",
    "description": "Search approved clinical triage protocols or guideline documents.",
    "input": {"symptom_group": "Symptom group.", "query": "Search query.", "red_flags": "Optional red flag codes."},
    "output": {"matches": "Guideline matches with title, excerpt, priority hint, and source."},
    "action": "Ground clinician-facing triage support in approved guidance.",
}

# TODO: Implement MCP/local adapter.
