from __future__ import annotations

import inspect
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field


class CatalogToolMetadata(BaseModel):
    source: str = "local"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    requires_human_review: bool = False
    patient_visible: bool = False
    latency_ms: float = 0.0
    trace_id: str | None = None


class CatalogToolResult(BaseModel):
    tool_id: int
    tool_name: str
    ok: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    metadata: CatalogToolMetadata = Field(default_factory=CatalogToolMetadata)


@dataclass
class ToolExecutionContext:
    case_id: str | None = None
    actor_id: str = "system"
    actor_role: str = "system"
    approved: bool = False
    patient_visible: bool = False
    state: Any = None
    registry: Any = None
    extra: dict[str, Any] = field(default_factory=dict)


ToolHandler = Callable[[dict[str, Any], ToolExecutionContext], dict[str, Any] | Awaitable[dict[str, Any]]]


def catalog_tool(spec: dict[str, Any]) -> Callable[..., Awaitable[CatalogToolResult]]:
    """Create the public execute() entry point used by every catalog module."""

    async def execute(
        arguments: dict[str, Any],
        context: ToolExecutionContext | None = None,
    ) -> CatalogToolResult:
        from src.tool.catalog.registry import catalog_tool_registry

        return await catalog_tool_registry.call(
            str(spec["name"]),
            arguments,
            context=context,
        )

    return execute


async def invoke_handler(
    handler: ToolHandler,
    arguments: dict[str, Any],
    context: ToolExecutionContext,
) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    value = handler(arguments, context)
    if inspect.isawaitable(value):
        value = await value
    if not isinstance(value, dict):
        raise TypeError("Tool handler must return a dictionary.")
    return value, round((time.perf_counter() - started) * 1000, 3)
