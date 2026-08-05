# Thu muc `src/tool`

Thu muc nay gom hai lop tool:

1. MCP-facing tools: descriptor va client de goi server MCP ben ngoai neu duoc cau hinh.
2. Local tool catalog: 82 tool chay noi bo trong repo, dung cho intake, mapping, safety, HITL, audit, notification, analytics.

## File va folder

| Duong dan | Lam gi |
|---|---|
| `__init__.py` | Danh dau package `src.tool`. |
| `base.py` | Model dung chung cho tool: risk level, policy, descriptor, call request/result, client protocol. |
| `registry.py` | `MCPToolRegistry`: list/call MCP descriptors; fallback goi local catalog neu tool nam trong catalog. |
| `catalog/` | Local catalog 82 tool va framework discover/execute/audit. |
| `mcp/` | Client HTTP JSON-RPC toi MCP server va exception rieng. |
| `audit/` | Descriptor cho audit MCP tool. |
| `cds/` | Descriptor cho CDS Hooks MCP tool. |
| `fhir/` | Descriptor cho FHIR/EHR context MCP tool. |
| `notification/` | Descriptor cho nurse alert MCP tool. |
| `search/` | Descriptor cho clinical guideline search MCP tool. |
| `terminology/` | Descriptor cho SNOMED lookup MCP tool. |

## Risk level

| Level | Y nghia |
|---|---|
| `read_only` | Chi doc/tinh toan, it rui ro side effect. |
| `clinical_decision_support` | Anh huong clinical workflow, khong duoc dua thang cho benh nhan neu chua review. |
| `side_effect` | Ghi EHR, gui thong bao, tao task/appointment; bat buoc co human approval. |

