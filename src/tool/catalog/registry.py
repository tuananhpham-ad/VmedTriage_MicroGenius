from __future__ import annotations

import importlib
import pkgutil
from typing import Any

from pydantic import BaseModel, Field

from src.tool.base import ToolRiskLevel
from src.tool.catalog.framework import (
    CatalogToolMetadata,
    CatalogToolResult,
    ToolExecutionContext,
    invoke_handler,
)
from src.tool.catalog.implementations import run_tool
from src.tool.catalog.state import catalog_state

SIDE_EFFECT_TOOL_IDS = {
    5,
    46,
    47,
    48,
    49,
    51,
    52,
    53,
    54,
    56,
    64,
    65,
    66,
    67,
    68,
    69,
    74,
}
CLINICAL_TOOL_IDS = set(range(22, 41)) | {55, 60, 61, 71, 72, 73}


class CatalogToolDefinition(BaseModel):
    id: int
    name: str
    category: str
    description: str
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    action: str
    risk_level: ToolRiskLevel
    requires_human_approval: bool
    patient_visible: bool = False
    local_module: str


class CatalogToolRegistry:
    """Discovers catalog modules and executes them through one guarded contract."""

    def __init__(self) -> None:
        self._definitions: dict[str, CatalogToolDefinition] = {}
        self._discover()

    def _discover(self) -> None:
        import src.tool.catalog as catalog_package

        prefix = f"{catalog_package.__name__}."
        for module_info in pkgutil.walk_packages(catalog_package.__path__, prefix):
            leaf = module_info.name.rsplit(".", 1)[-1]
            if module_info.ispkg or not leaf.startswith("tool_"):
                continue
            module = importlib.import_module(module_info.name)
            spec = getattr(module, "TOOL_SPEC", None)
            if not isinstance(spec, dict):
                continue
            tool_id = int(spec["id"])
            risk_level = (
                ToolRiskLevel.SIDE_EFFECT
                if tool_id in SIDE_EFFECT_TOOL_IDS
                else ToolRiskLevel.CLINICAL_DECISION_SUPPORT
                if tool_id in CLINICAL_TOOL_IDS
                else ToolRiskLevel.READ_ONLY
            )
            category = module_info.name.split(".")[-2]
            definition = CatalogToolDefinition(
                **spec,
                category=category,
                risk_level=risk_level,
                requires_human_approval=risk_level == ToolRiskLevel.SIDE_EFFECT,
                patient_visible=False,
                local_module=module_info.name,
            )
            self._definitions[definition.name] = definition

    def list_tools(self) -> list[CatalogToolDefinition]:
        return sorted(self._definitions.values(), key=lambda item: item.id)

    def get(self, name: str) -> CatalogToolDefinition | None:
        return self._definitions.get(name)

    async def call(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        context: ToolExecutionContext | None = None,
    ) -> CatalogToolResult:
        definition = self.get(name)
        if definition is None:
            return CatalogToolResult(tool_id=0, tool_name=name, ok=False, error="Tool is not registered.")
        if not isinstance(arguments, dict):
            return self._error(definition, "Tool arguments must be a dictionary.")

        execution = context or ToolExecutionContext()
        execution.state = execution.state or catalog_state
        execution.registry = self

        if definition.requires_human_approval and not execution.approved:
            return self._error(
                definition,
                "Explicit human approval is required for this side-effect tool.",
                requires_review=True,
            )

        try:
            data, latency_ms = await invoke_handler(
                lambda payload, ctx: run_tool(name, payload, ctx),
                arguments,
                execution,
            )
            missing_outputs = [key for key in definition.output if key not in data]
            if missing_outputs:
                return self._error(
                    definition,
                    "Handler output is missing required keys: " + ", ".join(missing_outputs),
                )
            result = CatalogToolResult(
                tool_id=definition.id,
                tool_name=definition.name,
                ok=True,
                data=data,
                metadata=CatalogToolMetadata(
                    source="local",
                    requires_human_review=definition.risk_level
                    == ToolRiskLevel.CLINICAL_DECISION_SUPPORT,
                    patient_visible=definition.patient_visible,
                    latency_ms=latency_ms,
                ),
            )
            self._audit(definition, arguments, result, execution)
            return result
        except (KeyError, TypeError, ValueError) as error:
            result = self._error(definition, str(error))
            self._audit(definition, arguments, result, execution)
            return result

    def _error(
        self,
        definition: CatalogToolDefinition,
        message: str,
        *,
        requires_review: bool = False,
    ) -> CatalogToolResult:
        return CatalogToolResult(
            tool_id=definition.id,
            tool_name=definition.name,
            ok=False,
            error=message,
            metadata=CatalogToolMetadata(requires_human_review=requires_review),
        )

    def _audit(
        self,
        definition: CatalogToolDefinition,
        arguments: dict[str, Any],
        result: CatalogToolResult,
        context: ToolExecutionContext,
    ) -> None:
        if definition.name in {"tool_call_audit_logger", "triage_audit_log_write"}:
            return
        context.state.audit_events.append(
            {
                "event_type": "catalog_tool_call",
                "tool_id": definition.id,
                "tool_name": definition.name,
                "case_id": context.case_id,
                "actor_role": context.actor_role,
                "ok": result.ok,
                "argument_keys": sorted(arguments),
                "error": result.error,
                "latency_ms": result.metadata.latency_ms,
            }
        )


catalog_tool_registry = CatalogToolRegistry()
