from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.tool.catalog.framework import CatalogToolResult, ToolExecutionContext
from src.tool.catalog.registry import CatalogToolRegistry, catalog_tool_registry


@dataclass
class OrchestrationRun:
    intent: str
    results: list[CatalogToolResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(item.ok for item in self.results)

    def data_for(self, tool_name: str) -> dict[str, Any]:
        for item in self.results:
            if item.tool_name == tool_name:
                return item.data
        return {}


class ToolOrchestrator:
    """Small deterministic orchestrator; an LLM may supply a plan, policy remains here."""

    def __init__(self, registry: CatalogToolRegistry | None = None) -> None:
        self.registry = registry or catalog_tool_registry

    def plan_for_patient_query(self, query: str) -> list[tuple[str, dict[str, Any]]]:
        return [
            ("patient_message_normalizer", {"patient_message": query}),
            ("language_detector", {"text": query}),
            ("symptom_extraction_tool", {"patient_message": query}),
            ("self_harm_risk_detector", {"patient_message": query}),
            ("abuse_or_violence_detector", {"patient_message": query}),
            ("risk_factor_extraction_tool", {"text": query}),
        ]

    async def run_patient_query(
        self,
        query: str,
        *,
        case_id: str | None = None,
    ) -> OrchestrationRun:
        run = OrchestrationRun(intent="patient_triage_intake")
        context = ToolExecutionContext(case_id=case_id, actor_role="patient")
        for name, arguments in self.plan_for_patient_query(query):
            result = await self.registry.call(name, arguments, context=context)
            run.results.append(result)
            if not result.ok:
                break
        return run


tool_orchestrator = ToolOrchestrator()
