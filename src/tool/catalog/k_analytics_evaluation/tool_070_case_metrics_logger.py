"""Tool stub: log case metrics."""

TOOL_SPEC = {
    "id": 70,
    "name": "case_metrics_logger",
    "description": "Log latency, case status, priority distribution, red flag count, and review outcomes.",
    "input": {"case_id": "Triage case id.", "metrics": "Metrics payload."},
    "output": {"stored": "Storage status.", "metric_event_id": "Metric event id."},
    "action": "Support operational analytics and quality monitoring.",
}

# TODO: Implement MCP/local adapter.
