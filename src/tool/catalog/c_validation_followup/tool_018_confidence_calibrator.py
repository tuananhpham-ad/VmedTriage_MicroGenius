"""Tool stub: calibrate extraction confidence."""

TOOL_SPEC = {
    "id": 18,
    "name": "confidence_calibrator",
    "description": "Estimate calibrated confidence for mapped symptoms and extracted fields.",
    "input": {"structured_symptoms": "Mapped symptom data.", "evidence": "Source text spans or notes."},
    "output": {"confidence": "Calibrated confidence.", "low_confidence_fields": "Fields needing review."},
    "action": "Determine whether the system should ask more questions or route to manual review.",
}

# TODO: Implement MCP/local adapter.
