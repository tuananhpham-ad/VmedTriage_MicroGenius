"""Tool stub: lookup SNOMED CT concepts."""

TOOL_SPEC = {
    "id": 9,
    "name": "snomed_concept_lookup",
    "description": "Normalize mapped symptoms to SNOMED CT concepts through a terminology service.",
    "input": {"term": "Clinical term.", "language": "Language code.", "system": "Terminology system URI."},
    "output": {"concepts": "Candidate SNOMED concepts with code, display, and confidence."},
    "action": "Standardize symptom terminology for downstream matching.",
}

# TODO: Implement MCP/local adapter.
