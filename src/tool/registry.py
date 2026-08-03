from __future__ import annotations

from collections.abc import Iterable

import httpx

from src.config import MCP_TOOL_SERVER_CONFIGS, get_settings
from src.tool.audit.audit_log import build_descriptor as build_audit_log_descriptor
from src.tool.base import MCPToolCallResult, MCPToolDescriptor
from src.tool.catalog.framework import ToolExecutionContext
from src.tool.catalog.registry import CatalogToolDefinition, catalog_tool_registry
from src.tool.cds.cds_hooks import build_descriptor as build_cds_hooks_descriptor
from src.tool.fhir.ehr_context import build_descriptor as build_fhir_context_descriptor
from src.tool.mcp.client import StreamableHTTPMCPClient
from src.tool.mcp.errors import MCPToolError
from src.tool.notification.nurse_alert import build_descriptor as build_nurse_alert_descriptor
from src.tool.search.clinical_guideline_search import build_descriptor as build_guideline_search_descriptor
from src.tool.terminology.snomed_lookup import build_descriptor as build_snomed_lookup_descriptor


class MCPToolRegistry:
    def __init__(self, descriptors: Iterable[MCPToolDescriptor] | None = None) -> None:
        self._descriptors = {
            descriptor.name: descriptor
            for descriptor in descriptors
            or (
                build_guideline_search_descriptor(),
                build_snomed_lookup_descriptor(),
                build_fhir_context_descriptor(),
                build_cds_hooks_descriptor(),
                build_nurse_alert_descriptor(),
                build_audit_log_descriptor(),
            )
        }

    def list_tools(self) -> list[MCPToolDescriptor]:
        return list(self._descriptors.values())

    def list_catalog_tools(self) -> list[CatalogToolDefinition]:
        """Return all local tools available to an orchestrator or MCP host."""
        return catalog_tool_registry.list_tools()

    def get(self, name: str) -> MCPToolDescriptor | None:
        return self._descriptors.get(name)

    async def call(self, name: str, arguments: dict) -> MCPToolCallResult:
        descriptor = self.get(name)
        catalog_descriptor = catalog_tool_registry.get(name)
        if not descriptor and not catalog_descriptor:
            return MCPToolCallResult(tool_name=name, ok=False, error="Tool is not registered.")

        server_url = self._server_url_for(descriptor) if descriptor else ""
        if descriptor and server_url:
            try:
                client = StreamableHTTPMCPClient(server_url=server_url)
                return await client.call_tool(descriptor, arguments)
            except (MCPToolError, httpx.HTTPError, ValueError) as error:
                return MCPToolCallResult(tool_name=name, ok=False, error=str(error))

        # Existing MCP API routes keep their explicit configuration contract.
        # The local catalog is invoked directly through CatalogToolRegistry.
        if descriptor and not server_url:
            return MCPToolCallResult(
                tool_name=name,
                ok=False,
                error=f"MCP server URL is not configured for {descriptor.external_server}.",
            )

        if catalog_descriptor:
            local_arguments = {key: value for key, value in arguments.items() if not key.startswith("_")}
            context = ToolExecutionContext(
                case_id=arguments.get("_case_id"),
                actor_id=str(arguments.get("_actor_id", "system")),
                actor_role=str(arguments.get("_actor_role", "system")),
                approved=bool(arguments.get("_approved", False)),
            )
            result = await catalog_tool_registry.call(name, local_arguments, context=context)
            return MCPToolCallResult(
                tool_name=name,
                ok=result.ok,
                data=result.data,
                error=result.error,
                source=result.metadata.source,
            )

        return MCPToolCallResult(tool_name=name, ok=False, error="Tool could not be executed.")

    def _server_url_for(self, descriptor: MCPToolDescriptor) -> str:
        server_config = MCP_TOOL_SERVER_CONFIGS.get(descriptor.external_server, {})
        setting_name = server_config.get("setting_name", "")
        if not setting_name:
            return ""
        return str(getattr(get_settings(), setting_name, ""))


tool_registry = MCPToolRegistry()
