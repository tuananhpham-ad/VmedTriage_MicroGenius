"""Tool stub: check contraindications."""

TOOL_SPEC = {
    "id": 33,
    "name": "contraindication_checker",
    "description": "Check contraindications based on allergies, pregnancy, conditions, or medications.",
    "input": {"candidate_action": "Clinical action under review.", "patient_context": "Relevant patient context."},
    "output": {"contraindications": "Contraindication findings."},
    "action": "Warn clinicians before approving advice or workflow actions.",
}

# TODO: Implement MCP/local adapter.
