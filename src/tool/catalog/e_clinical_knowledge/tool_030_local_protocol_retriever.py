"""Tool stub: retrieve local protocols."""

TOOL_SPEC = {
    "id": 30,
    "name": "local_protocol_retriever",
    "description": "Retrieve hospital or clinic-specific triage protocols.",
    "input": {"symptom_group": "Symptom group.", "site_id": "Clinical site identifier."},
    "output": {"protocols": "Relevant local protocols."},
    "action": "Use local workflow rules before generic guidance.",
}

# TODO: Implement MCP/local adapter.
