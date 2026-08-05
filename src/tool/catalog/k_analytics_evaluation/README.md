# Nhom K - Analytics va evaluation

Nhom nay ghi metric va danh gia chat luong/safety cua he thong.

| File | Tool | Lam gi |
|---|---|---|
| `__init__.py` | Package marker | Danh dau package tool group K. |
| `tool_070_case_metrics_logger.py` | `case_metrics_logger` | Log latency, status, priority, red flag count va review outcome. |
| `tool_071_triage_quality_evaluator.py` | `triage_quality_evaluator` | So sanh triage output voi label/gold/nurse outcome. |
| `tool_072_rag_grounding_evaluator.py` | `rag_grounding_evaluator` | Kiem tra output RAG co dua tren evidence retrieve duoc hay khong. |
| `tool_073_safety_event_detector.py` | `safety_event_detector` | Phat hien safety incident hoac near miss tu case trace. |
| `tool_074_feedback_collector.py` | `feedback_collector` | Thu feedback co cau truc tu nurse/clinician/patient. |
| `tool_075_drift_monitor.py` | `drift_monitor` | Theo doi drift trong mapping, priority, red flags, nurse overrides. |

