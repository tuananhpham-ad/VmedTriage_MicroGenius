"""Tool stub: check access control."""

TOOL_SPEC = {
    "id": 63,
    "name": "access_control_checker",
    "description": "Check whether an actor may access a case, tool, resource, or action.",
    "input": {"actor_id": "Actor id.", "actor_role": "Actor role.", "resource": "Resource id.", "action": "Requested action."},
    "output": {"allowed": "Access decision.", "reason": "Policy reason."},
    "action": "Enforce role-based access before sensitive operations.",
}

# TODO: Implement MCP/local adapter.
