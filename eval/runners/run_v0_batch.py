"""Phase 1 - Vibe Check: chạy 15 case của `eval/datasets/v0_manual_cases.jsonl` qua Track 1 THẬT
(`TriagePipeline.handle_patient_message`, rule-based, AUTHORITATIVE), một Braintrust trace/case
trong project "vmedtriage-vibe-check", gắn metadata (case id, note, expected_urgency,
expected_department). In bảng tóm tắt cuối cùng.

KHÔNG tự động duyệt/gửi bất kỳ kết quả nào cho bệnh nhân - đây chỉ là chạy thử để đọc trace bằng
mắt. `expected_*` trong dataset là DRAFT, chưa qua bác sĩ xác nhận (xem file `_meta` record đầu
`v0_manual_cases.jsonl` và docs/eval/00_PLAN.md).

Chạy: `python eval/runners/run_v0_batch.py`
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from eval.config import BRAINTRUST_PROJECT_VIBE_CHECK  # noqa: E402
from src.observability.braintrust_tracing import braintrust_enabled, traced_root_span  # noqa: E402
from src.services.triage_pipeline import TriagePipeline  # noqa: E402

DATASET_PATH = Path(__file__).resolve().parents[1] / "datasets" / "v0_manual_cases.jsonl"


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("_meta"):
                continue
            cases.append(record)
    return cases


async def run_one(pipeline: TriagePipeline, case: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    row: dict[str, Any] = {
        "id": case["id"],
        "note": case.get("note", "")[:60],
        "expected_urgency": case.get("expected_urgency"),
        "provider": "none/rule-based",  # Track 1 không gọi LLM - xem docs/eval/01_evaluation_units.md mục 8.
        "trace_link": None,
        "error": None,
        "actual_priority": None,
        "runtime_ms": None,
    }
    try:
        with traced_root_span(
            f"v0_batch/{case['id']}",
            project=BRAINTRUST_PROJECT_VIBE_CHECK,
            case_id=case["id"],
            metadata={
                "dataset": "v0_manual_cases",
                "case_id": case["id"],
                "note": case.get("note"),
                "expected_urgency": case.get("expected_urgency"),
                "expected_department": case.get("expected_department"),
            },
        ) as (span, trace_link):
            row["trace_link"] = trace_link
            triage_case = await pipeline.handle_patient_message(case["input"])
            priority = triage_case.triage_proposal.priority if triage_case.triage_proposal else None
            row["actual_priority"] = str(priority) if priority is not None else None
            row["requires_manual_review"] = (
                triage_case.triage_proposal.requires_manual_review if triage_case.triage_proposal else None
            )
            span.log(
                input={"message": case["input"]},
                output={"priority": str(priority) if priority is not None else None, "status": str(triage_case.status)},
                metadata={"expected_urgency": case.get("expected_urgency")},
            )
    except Exception as error:  # Per-case error KHÔNG được làm hỏng cả batch - catch, log, tiếp tục.
        row["error"] = f"{type(error).__name__}: {error}"
    row["runtime_ms"] = int((time.perf_counter() - started) * 1000)
    return row


async def _run() -> list[dict[str, Any]]:
    cases = load_cases(DATASET_PATH)
    pipeline = TriagePipeline()
    rows = []
    for case in cases:
        rows.append(await run_one(pipeline, case))
    return rows


def print_summary(rows: list[dict[str, Any]]) -> None:
    header = f"{'id':<8} {'runtime_ms':>10} {'provider':<16} {'priority':<20} {'expected':<15} {'trace_link/error'}"
    print(header)
    print("-" * len(header))
    for row in rows:
        status = row["error"] or (row["trace_link"] or "no_trace_link (BRAINTRUST_API_KEY unset)")
        print(
            f"{row['id']:<8} {row['runtime_ms']:>10} {row['provider']:<16} "
            f"{str(row['actual_priority']):<20} {str(row['expected_urgency']):<15} {status}"
        )
    n_errors = sum(1 for r in rows if r["error"])
    print(f"\n{len(rows)} case(s), {n_errors} error(s).")


def main() -> None:
    print(f"BRAINTRUST_API_KEY set: {braintrust_enabled()}")
    print(f"Braintrust project: {BRAINTRUST_PROJECT_VIBE_CHECK}")
    rows = asyncio.run(_run())
    print()
    print_summary(rows)


if __name__ == "__main__":
    main()
