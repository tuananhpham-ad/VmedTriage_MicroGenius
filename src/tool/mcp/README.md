# Thu muc `src/tool/mcp`

Thu muc nay chua phan ha tang de goi MCP server ben ngoai qua Streamable HTTP/JSON-RPC.

## File

| File | Lam gi |
|---|---|
| `__init__.py` | Danh dau package `src.tool.mcp`. |
| `client.py` | `StreamableHTTPMCPClient` tao request JSON-RPC `tools/call`, gui bang `httpx`, parse response thanh `MCPToolCallResult`. |
| `errors.py` | Dinh nghia `MCPToolError` cho loi goi MCP. |

Neu URL server khong co trong `.env`, `MCPToolRegistry` se tra loi "not configured" cho MCP descriptor tuong ung.

