from __future__ import annotations

from datetime import datetime, timezone

from src.models.schemas import TriageCase


class InMemoryCaseStore:
    def __init__(self) -> None:
        self._cases: dict[str, TriageCase] = {}

    def get(self, case_id: str) -> TriageCase | None:
        return self._cases.get(case_id)

    def save(self, triage_case: TriageCase) -> TriageCase:
        triage_case.updated_at = datetime.now(timezone.utc)
        self._cases[triage_case.case_id] = triage_case
        return triage_case

    def list_cases(self) -> list[TriageCase]:
        return list(self._cases.values())


case_store = InMemoryCaseStore()
