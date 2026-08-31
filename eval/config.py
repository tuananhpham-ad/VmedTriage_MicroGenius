"""Cấu hình package `eval/` — tên project Braintrust, dataset version hiện hành, và re-export
tracer từ `src/observability/braintrust_tracing.py` (nơi thật sự cài đặt wrapper, vì
`TriagePipeline`/`graph_triage_service` trong `src/` cũng cần dùng nó và KHÔNG được phụ thuộc
ngược vào `eval/`).
"""

from __future__ import annotations

from src.observability.braintrust_tracing import (  # noqa: F401 - re-export cho runner/test dùng
    braintrust_enabled,
    traced_root_span,
    traced_span,
)

# Dataset version hiện hành cho Vibe Check (Phase 1). Tăng lên khi sửa rubric/thêm case sau
# incident thay vì ghi đè file cũ (xem quy ước versioning ở docs/eval/00_PLAN.md).
V0_DATASET_VERSION = "v0_manual_cases"

BRAINTRUST_PROJECT_VIBE_CHECK = "vmedtriage-vibe-check"
