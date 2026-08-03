"""Tool stub: read nurse queue."""

TOOL_SPEC = {
    "id": 50,
    "name": "nurse_queue_read",
    "description": "Read cases waiting in the nurse review queue.",
    "input": {"filters": "Optional queue filters such as priority or status."},
    "output": {"items": "Matching nurse queue items."},
    "action": "Power nurse dashboard queue views.",
}

# TODO: Implement MCP/local adapter.
