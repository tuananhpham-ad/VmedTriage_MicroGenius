"""Tool stub: search triage pathways."""

TOOL_SPEC = {
    "id": 31,
    "name": "triage_pathway_search",
    "description": "Find symptom-specific triage pathways such as chest pain, breathing, neurologic, or bleeding.",
    "input": {"symptom_group": "Detected symptom group.", "structured_symptoms": "Structured case fields."},
    "output": {"pathways": "Candidate triage pathways and decision points."},
    "action": "Provide pathway options for clinician-facing decision support.",
}

# TODO: Implement MCP/local adapter.
