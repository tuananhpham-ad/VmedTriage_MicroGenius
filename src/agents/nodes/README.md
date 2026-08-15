# Thu muc `src/agents/nodes`

Thu muc nay chua cac node function cua LangGraph. Moi node nhan `AgentState` va tra ve dict cac field can cap nhat vao state.

## File

| File | Lam gi |
|---|---|
| `__init__.py` | Danh dau package `src.agents.nodes`. |
| `triage_nodes.py` | Chua node `run_triage_pipeline_node`, node `patient_safe_response_node`, va helper `_build_analysis`. |

## Chi tiet `triage_nodes.py`

| Thanh phan | Vai tro |
|---|---|
| `run_triage_pipeline_node()` | Kiem tra message rong, goi `triage_pipeline.handle_patient_message()`, tra ve `case_id`, `triage_case`, `analysis`. |
| `patient_safe_response_node()` | Neu co loi thi tra thong bao loi; neu co case thi lay `patient_visible_response`. |
| `_build_analysis()` | Tao chuoi tom tat noi bo gom case id, status, priority, missing fields va red flags. |

