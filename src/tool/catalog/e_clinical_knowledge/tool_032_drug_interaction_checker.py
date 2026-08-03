"""Tool stub: check drug interactions."""

TOOL_SPEC = {
    "id": 32,
    "name": "drug_interaction_checker",
    "description": "Check potential interactions among current medications.",
    "input": {"medications": "Medication list."},
    "output": {"interactions": "Interaction findings with severity and explanation."},
    "action": "Provide clinician-facing medication safety context.",
}

# TODO: Implement MCP/local adapter.
