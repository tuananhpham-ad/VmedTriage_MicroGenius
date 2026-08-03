"""Tool stub: read patient profile."""

TOOL_SPEC = {
    "id": 6,
    "name": "patient_profile_read",
    "description": "Read patient demographics and high-level profile context such as age, sex, pregnancy, and known risks.",
    "input": {"patient_id": "Patient identifier or case-linked patient reference."},
    "output": {"profile": "Limited patient profile fields approved for triage."},
    "action": "Provide context that can change triage risk thresholds.",
}

# TODO: Implement MCP/local adapter.
