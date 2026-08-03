"""Tool stub: calculate clinical scores."""

TOOL_SPEC = {
    "id": 34,
    "name": "clinical_calculator_tool",
    "description": "Calculate clinician-facing scores such as GCS, NEWS2, or pain score summaries when inputs are available.",
    "input": {"calculator": "Calculator name.", "values": "Required input values."},
    "output": {"score": "Calculated score.", "interpretation": "Clinician-facing interpretation."},
    "action": "Support nurse review with validated calculators.",
}

# TODO: Implement MCP/local adapter.
