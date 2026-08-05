# Thu muc `src/agents`

Day la lop LangGraph cua he thong. Agent hien tai khong phai ReAct agent tu do; no la workflow ngan, co kiem soat, goi deterministic triage pipeline roi tao response an toan.

## File va folder

| Duong dan | Lam gi |
|---|---|
| `__init__.py` | Danh dau package `src.agents`. |
| `state.py` | Khai bao `AgentState`, gom `query`, `case_id`, `triage_case`, `analysis`, `response`, `error`, `metadata`. |
| `graph.py` | Build LangGraph voi node `triage_pipeline` va `respond`; neu co loi thi ket thuc, neu khong thi sang node response. |
| `nodes/` | Chua cac ham node duoc gan vao graph. |
| `tools/` | Tool mau theo kieu LangChain; hien chu yeu de tham khao/template. |

## Luong xu ly

1. API gui `{"query": message, "case_id": optional}` vao `agent.ainvoke`.
2. Node `triage_pipeline` goi `TriagePipeline.handle_patient_message`.
3. `should_continue()` kiem tra `state.error`.
4. Node `respond` lay `triage_case.patient_visible_response` lam response cuoi.

