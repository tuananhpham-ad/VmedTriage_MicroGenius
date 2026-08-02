from __future__ import annotations

from itertools import count
from typing import Any

import httpx

from src.config import get_settings
from src.tool.base import MCPToolCallResult, MCPToolDescriptor
from src.tool.mcp.errors import MCPToolError


class StreamableHTTPMCPClient:
    """Minimal JSON-RPC client for configured Streamable HTTP MCP servers."""

    def __init__(self, server_url: str) -> None:
        self.server_url = server_url.rstrip("/")
        self._request_ids = count(1)

    async def call_tool(self, descriptor: MCPToolDescriptor, arguments: dict[str, Any]) -> MCPToolCallResult:
        if not self.server_url:
            raise MCPToolError(f"MCP server URL is not configured for {descriptor.external_server}.")

        payload = {
            "jsonrpc": "2.0",
            "id": next(self._request_ids),
            "method": "tools/call",
            "params": {
                "name": descriptor.name,
                "arguments": arguments,
            },
        }

        timeout = get_settings().mcp_call_timeout_seconds
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(self.server_url, json=payload)
            response.raise_for_status()
            body = response.json()

        if "error" in body:
            return MCPToolCallResult(
                tool_name=descriptor.name,
                ok=False,
                error=str(body["error"]),
            )

        result = body.get("result", {})
        if not isinstance(result, dict):
            result = {"content": result}

        return MCPToolCallResult(
            tool_name=descriptor.name,
            ok=True,
            data=result,
        )
