# Nhom L - Orchestrator internal

Nhom nay khong phai tool clinical truc tiep. No ho tro orchestrator liet ke tool, chon tool, enforce policy, build arguments, validate result, chon fallback va ghi trace.

| File | Tool | Lam gi |
|---|---|---|
| `__init__.py` | Package marker | Danh dau package tool group L. |
| `tool_076_tool_registry_list.py` | `tool_registry_list` | Liet ke tool descriptor va capability hien co. |
| `tool_077_tool_capability_matcher.py` | `tool_capability_matcher` | Match intent/case state/policy voi candidate tools. |
| `tool_078_tool_policy_enforcer.py` | `tool_policy_enforcer` | Kiem tra risk level, approval va patient visibility truoc khi goi tool. |
| `tool_079_tool_argument_builder.py` | `tool_argument_builder` | Build arguments dung schema tu agent state va case context. |
| `tool_080_tool_result_validator.py` | `tool_result_validator` | Validate output tool truoc khi dung vao case state. |
| `tool_081_fallback_strategy_selector.py` | `fallback_strategy_selector` | Chon fallback khi MCP unavailable/unconfigured/unsafe. |
| `tool_082_orchestration_trace_writer.py` | `orchestration_trace_writer` | Ghi trace quyet dinh cua orchestrator de debug/demo. |

