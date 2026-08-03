"""Tool stub: monitor model or rule drift."""

TOOL_SPEC = {
    "id": 75,
    "name": "drift_monitor",
    "description": "Monitor changes in symptom mapping, triage priority, red flags, or nurse overrides over time.",
    "input": {"time_window": "Monitoring window.", "metrics": "Current metrics."},
    "output": {"drift_detected": "Drift decision.", "signals": "Drift signals."},
    "action": "Detect when rules, prompts, or models need review.",
}

# TODO: Implement MCP/local adapter.
