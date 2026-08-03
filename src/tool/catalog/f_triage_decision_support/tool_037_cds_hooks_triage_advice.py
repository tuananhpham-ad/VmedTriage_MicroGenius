"""Tool stub: call CDS Hooks triage service."""

TOOL_SPEC = {
    "id": 37,
    "name": "cds_hooks_triage_advice",
    "description": "Request CDS Hooks cards for clinician-facing triage decision support.",
    "input": {"hook": "CDS hook name.", "context": "CDS context.", "prefetch": "Optional prefetch data."},
    "output": {"cards": "CDS Hooks cards."},
    "action": "Cross-check local proposal with external CDS service.",
}

# TODO: Implement MCP/local adapter.
