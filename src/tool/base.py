from __future__ import annotations

from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, Field


class ToolRiskLevel(str, Enum):
    READ_ONLY = "read_only"
    CLINICAL_DECISION_SUPPORT = "clinical_decision_support"
    SIDE_EFFECT = "side_effect"


class ToolCallPolicy(BaseModel):
    risk_level: ToolRiskLevel
    requires_human_approval: bool = True
    patient_visible: bool = False
    allow_before_hitl: bool = False


class MCPToolDescriptor(BaseModel):
    name: str
    category: str
    external_server: str
    local_module: str
    description: str
    when_to_use: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    policy: ToolCallPolicy


class MCPToolCallRequest(BaseModel):
    case_id: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)


class MCPToolCallResult(BaseModel):
    tool_name: str
    ok: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    source: str = "mcp"


class MCPToolClient(Protocol):
    async def call_tool(self, descriptor: MCPToolDescriptor, arguments: dict[str, Any]) -> MCPToolCallResult:
        """Call an external MCP tool using the descriptor metadata."""
