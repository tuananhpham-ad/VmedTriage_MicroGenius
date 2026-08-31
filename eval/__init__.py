"""Package eval/ cho VMedTriage — instrumentation + dataset + runner cho Braintrust.

Tách biệt khỏi `eval/scripts/run_eval.py` (script offline eval model graph_triage cũ, đã có từ
trước) — package này (`eval/__init__.py`, `eval/config.py`, `eval/runners/`) là phần mới thêm để
trace Track 1 (`TriagePipeline`, authoritative) và Track 2 (`graph_triage_service`, advisory) qua
Braintrust. Xem `docs/eval/00_PLAN.md` và `docs/eval/01_evaluation_units.md`.
"""
