"""Tool stub: lookup LOINC observations."""

TOOL_SPEC = {
    "id": 11,
    "name": "loinc_lookup",
    "description": "Map lab or observation names to LOINC codes.",
    "input": {"term": "Observation or lab name."},
    "output": {"codes": "Candidate LOINC codes and displays."},
    "action": "Normalize observations retrieved from FHIR or user input.",
}

# TODO: Implement MCP/local adapter.
