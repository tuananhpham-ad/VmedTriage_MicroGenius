from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CatalogStateStore:
    """Replaceable in-memory backend used by local/demo tool implementations."""

    conversations: dict[str, list[dict[str, Any]]] = field(default_factory=lambda: defaultdict(list))
    patient_profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    consents: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    fhir_resources: dict[str, dict[str, list[dict[str, Any]]]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(list))
    )
    queue: dict[str, dict[str, Any]] = field(default_factory=dict)
    case_statuses: dict[str, str] = field(default_factory=dict)
    assignments: dict[str, str] = field(default_factory=dict)
    audit_events: list[dict[str, Any]] = field(default_factory=list)
    outbox: list[dict[str, Any]] = field(default_factory=list)
    appointments: list[dict[str, Any]] = field(default_factory=list)
    metrics: list[dict[str, Any]] = field(default_factory=list)
    feedback: list[dict[str, Any]] = field(default_factory=list)
    traces: list[dict[str, Any]] = field(default_factory=list)


catalog_state = CatalogStateStore()
