from __future__ import annotations

from typing import TypedDict

from src.models.schemas import TriageCase


class AgentState(TypedDict, total=False):
    """LangGraph state for the VMedTriage controlled pipeline."""

    query: str
    case_id: str
    triage_case: TriageCase
    analysis: str
    response: str
    error: str
    metadata: dict
