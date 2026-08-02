from __future__ import annotations

import argparse
import asyncio
import json
import logging
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

logger = logging.getLogger("eval.run_eval")


EXPECTED_TRIAGE_TO_PRIORITY = {
    "emergency_now": "Emergency",
    "same_day": "Urgent",
    "soon_24_72h": "Routine",
    "home_monitoring": "Self-care",
    "insufficient_information_or_handoff": "Manual review",
}

ACTUAL_RED_FLAG_CODE_ALIASES = {
    "chest_pain_with_shortness_of_breath": "RF-CHEST-PAIN-001",
    "severe_shortness_of_breath": "RF-AIRWAY-BREATHING-001",
    "stroke_signs": "RF-NEURO-FAST-001",
    "heavy_bleeding": "RF-BLEEDING-SHOCK-001",
    "loss_of_consciousness": "RF-BLEEDING-SHOCK-001",
    "seizure": "RF-NEURO-FAST-001",
}

HANDOFF_STATUSES = {
    "needs_nurse_review",
    "awaiting_approval",
    "escalated",
    "approved",
}


@dataclass(frozen=True)
class EvalConfig:
    cases_path: Path
    output_dir: Path
    version: str
    mode: str
    base_url: str
    limit: int | None
    log_level: str
    fail_under_triage_accuracy: float | None
    fail_under_red_flag_recall: float | None


def parse_args() -> EvalConfig:
    parser = argparse.ArgumentParser(description="Run VMedTriage golden-case evaluation.")
    parser.add_argument("--cases", default="data/golden_cases_v1.jsonl", help="Path to .jsonl or .json cases.")
    parser.add_argument(
        "--output-dir",
        default="eval/results/logging",
        help="Directory for versioned eval outputs.",
    )
    parser.add_argument(
        "--version",
        default=None,
        help="Version name. Defaults to current local timestamp, for example 20260803_014512.",
    )
    parser.add_argument(
        "--mode",
        choices=("direct", "api"),
        default="direct",
        help="direct calls the Python pipeline; api calls a running FastAPI server.",
    )
    parser.add_argument("--base-url", default="http://localhost:8000", help="FastAPI base URL for --mode api.")
    parser.add_argument("--limit", type=int, default=None, help="Evaluate only the first N cases.")
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
        help="Console/file logging verbosity.",
    )
    parser.add_argument("--fail-under-triage-accuracy", type=float, default=None)
    parser.add_argument("--fail-under-red-flag-recall", type=float, default=None)
    args = parser.parse_args()

    return EvalConfig(
        cases_path=Path(args.cases),
        output_dir=Path(args.output_dir),
        version=args.version or timestamp_version(),
        mode=args.mode,
        base_url=args.base_url.rstrip("/"),
        limit=args.limit,
        log_level=args.log_level,
        fail_under_triage_accuracy=args.fail_under_triage_accuracy,
        fail_under_red_flag_recall=args.fail_under_red_flag_recall,
    )


def setup_logging(config: EvalConfig) -> Path:
    run_dir = config.output_dir / config.version
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "eval.log"

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_path, encoding="utf-8"),
    ]

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(getattr(logging, config.log_level))
    for handler in handlers:
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

    return log_path


def timestamp_version() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def load_cases(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Cases file not found: {path}")

    if path.suffix == ".jsonl":
        cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    elif path.suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError(f"Expected a JSON list in {path}")
        cases = data
    else:
        raise ValueError(f"Unsupported cases file extension: {path.suffix}")

    return cases[:limit] if limit is not None else cases


def patient_messages(case: dict[str, Any]) -> list[str]:
    return [
        str(turn["message"])
        for turn in case.get("conversation", [])
        if turn.get("role") == "patient" and turn.get("message")
    ]


async def run_case_direct(case: dict[str, Any]) -> dict[str, Any]:
    from src.services.case_store import InMemoryCaseStore
    from src.services.triage_pipeline import TriagePipeline

    pipeline = TriagePipeline(store=InMemoryCaseStore())
    case_id: str | None = None
    triage_case: Any = None

    for message in patient_messages(case):
        triage_case = await pipeline.handle_patient_message(message, case_id=case_id)
        case_id = triage_case.case_id

    if triage_case is None:
        raise ValueError("Case has no patient messages.")

    return triage_case.model_dump(mode="json")


async def run_case_api(case: dict[str, Any], base_url: str) -> dict[str, Any]:
    case_id: str | None = None
    response_payload: dict[str, Any] | None = None

    for message in patient_messages(case):
        payload: dict[str, Any] = {"message": message}
        if case_id:
            payload["case_id"] = case_id

        response_payload = await asyncio.to_thread(post_json, f"{base_url}/api/v1/chat", payload)
        case_id = response_payload["case_id"]

    if response_payload is None:
        raise ValueError("Case has no patient messages.")

    return response_payload


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {error_body}") from exc


async def run_one_case(case: dict[str, Any], config: EvalConfig) -> dict[str, Any]:
    started = time.perf_counter()
    if config.mode == "api":
        actual = await run_case_api(case, config.base_url)
    else:
        actual = await run_case_direct(case)
    latency_ms = (time.perf_counter() - started) * 1000
    return build_prediction(case, actual, latency_ms)


def build_prediction(case: dict[str, Any], actual: dict[str, Any], latency_ms: float) -> dict[str, Any]:
    expected_priority = EXPECTED_TRIAGE_TO_PRIORITY.get(str(case.get("expected_triage")))
    actual_priority = get_nested(actual, "triage_proposal", "priority")
    expected_red_flags = set(case.get("expected_red_flags") or [])
    actual_red_flags = normalize_actual_red_flags(actual.get("red_flags") or [])
    expected_handoff = bool(case.get("expected_handoff"))
    actual_handoff = is_handoff(actual)

    return {
        "case_id": case.get("case_id"),
        "scenario_type": case.get("scenario_type"),
        "source_id": case.get("source_id"),
        "expected": {
            "triage": case.get("expected_triage"),
            "priority": expected_priority,
            "red_flags": sorted(expected_red_flags),
            "handoff": expected_handoff,
        },
        "actual": {
            "priority": actual_priority,
            "red_flags": sorted(actual_red_flags),
            "handoff": actual_handoff,
            "status": actual.get("status"),
            "symptom_group": get_nested(actual, "structured_data", "symptom_group"),
            "missing_fields": get_nested(actual, "validation", "missing_fields") or [],
            "follow_up_questions": get_nested(actual, "validation", "follow_up_questions") or [],
            "response": actual.get("patient_visible_response") or actual.get("response"),
        },
        "scores": {
            "triage_match": actual_priority == expected_priority,
            "handoff_match": actual_handoff == expected_handoff,
            "red_flag_exact_match": actual_red_flags == expected_red_flags,
            "red_flag_recall": recall(expected_red_flags, actual_red_flags),
            "red_flag_precision": precision(expected_red_flags, actual_red_flags),
        },
        "latency_ms": round(latency_ms, 2),
    }


def get_nested(value: dict[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def normalize_actual_red_flags(findings: list[dict[str, Any]]) -> set[str]:
    codes: set[str] = set()
    for finding in findings:
        raw_code = str(finding.get("code", ""))
        codes.add(ACTUAL_RED_FLAG_CODE_ALIASES.get(raw_code, raw_code))
    return {code for code in codes if code}


def is_handoff(actual: dict[str, Any]) -> bool:
    status = actual.get("status")
    if status in HANDOFF_STATUSES:
        return True
    proposal = actual.get("triage_proposal") or {}
    return bool(proposal.get("requires_manual_review"))


def recall(expected: set[str], actual: set[str]) -> float | None:
    if not expected:
        return None
    return len(expected & actual) / len(expected)


def precision(expected: set[str], actual: set[str]) -> float | None:
    if not actual:
        return None
    return len(expected & actual) / len(actual)


def summarize(predictions: list[dict[str, Any]], failures: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(predictions)
    latencies = [item["latency_ms"] for item in predictions]
    expected_with_red_flags = [item for item in predictions if item["expected"]["red_flags"]]
    actual_with_red_flags = [item for item in predictions if item["actual"]["red_flags"]]
    red_flag_recalls = [
        item["scores"]["red_flag_recall"]
        for item in expected_with_red_flags
        if item["scores"]["red_flag_recall"] is not None
    ]
    red_flag_precisions = [
        item["scores"]["red_flag_precision"]
        for item in actual_with_red_flags
        if item["scores"]["red_flag_precision"] is not None
    ]

    return {
        "total_cases": total,
        "failed_runs": len(failures),
        "triage_accuracy": ratio(count_true(predictions, "triage_match"), total),
        "handoff_accuracy": ratio(count_true(predictions, "handoff_match"), total),
        "red_flag_exact_match_accuracy": ratio(count_true(predictions, "red_flag_exact_match"), total),
        "red_flag_macro_recall": mean_or_none(red_flag_recalls),
        "red_flag_macro_precision": mean_or_none(red_flag_precisions),
        "emergency_recall": emergency_recall(predictions),
        "latency_ms": {
            "avg": round(statistics.mean(latencies), 2) if latencies else None,
            "p95": percentile(latencies, 95),
            "max": max(latencies) if latencies else None,
        },
        "expected_priority_distribution": dict(Counter(item["expected"]["priority"] for item in predictions)),
        "actual_priority_distribution": dict(Counter(item["actual"]["priority"] for item in predictions)),
        "expected_red_flag_distribution": red_flag_distribution(predictions, "expected"),
        "actual_red_flag_distribution": red_flag_distribution(predictions, "actual"),
        "red_flag_code_metrics": build_red_flag_code_metrics(predictions),
        "confusion_matrix": build_confusion_matrix(predictions),
        "scenario_metrics": build_scenario_metrics(predictions),
    }


def count_true(predictions: list[dict[str, Any]], key: str) -> int:
    return sum(1 for item in predictions if item["scores"][key])


def ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def mean_or_none(values: list[float]) -> float | None:
    return round(statistics.mean(values), 4) if values else None


def percentile(values: list[float], pct: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((pct / 100) * (len(ordered) - 1)))
    return round(ordered[index], 2)


def emergency_recall(predictions: list[dict[str, Any]]) -> float | None:
    emergency_cases = [item for item in predictions if item["expected"]["priority"] == "Emergency"]
    if not emergency_cases:
        return None
    detected = sum(1 for item in emergency_cases if item["actual"]["priority"] == "Emergency")
    return ratio(detected, len(emergency_cases))


def red_flag_distribution(predictions: list[dict[str, Any]], side: str) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for item in predictions:
        counts.update(item[side]["red_flags"])
    return dict(sorted(counts.items()))


def build_red_flag_code_metrics(predictions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    all_codes = sorted(
        {
            code
            for item in predictions
            for side in ("expected", "actual")
            for code in item[side]["red_flags"]
        }
    )

    metrics = {}
    for code in all_codes:
        true_positive = false_positive = false_negative = 0
        for item in predictions:
            expected = code in item["expected"]["red_flags"]
            actual = code in item["actual"]["red_flags"]
            if expected and actual:
                true_positive += 1
            elif actual:
                false_positive += 1
            elif expected:
                false_negative += 1

        metrics[code] = {
            "true_positive": true_positive,
            "false_positive": false_positive,
            "false_negative": false_negative,
            "precision": ratio(true_positive, true_positive + false_positive),
            "recall": ratio(true_positive, true_positive + false_negative),
        }
    return metrics


def build_confusion_matrix(predictions: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for item in predictions:
        expected = str(item["expected"]["priority"])
        actual = str(item["actual"]["priority"])
        matrix[expected][actual] += 1
    return {expected: dict(actuals) for expected, actuals in sorted(matrix.items())}


def build_scenario_metrics(predictions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in predictions:
        grouped[str(item["scenario_type"])].append(item)

    metrics = {}
    for scenario, items in sorted(grouped.items()):
        red_flag_recalls = [
            item["scores"]["red_flag_recall"]
            for item in items
            if item["scores"]["red_flag_recall"] is not None
        ]
        metrics[scenario] = {
            "total_cases": len(items),
            "triage_accuracy": ratio(count_true(items, "triage_match"), len(items)),
            "handoff_accuracy": ratio(count_true(items, "handoff_match"), len(items)),
            "red_flag_macro_recall": mean_or_none(red_flag_recalls),
        }
    return metrics


def write_outputs(
    config: EvalConfig,
    cases: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    metrics: dict[str, Any],
    started_at: datetime,
    duration_seconds: float,
    log_path: Path,
) -> Path:
    run_dir = config.output_dir / config.version
    run_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "version": config.version,
        "mode": config.mode,
        "cases_path": str(config.cases_path),
        "started_at": started_at.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(duration_seconds, 3),
        "input_cases": len(cases),
        "log_path": str(log_path),
    }
    (run_dir / "metrics.json").write_text(
        json.dumps({"metadata": metadata, "metrics": metrics}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_jsonl(run_dir / "predictions.jsonl", predictions)
    write_jsonl(run_dir / "failures.jsonl", failures)
    (run_dir / "report.md").write_text(build_report(metadata, metrics, failures), encoding="utf-8")
    return run_dir


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_report(metadata: dict[str, Any], metrics: dict[str, Any], failures: list[dict[str, Any]]) -> str:
    lines = [
        f"# VMedTriage Evaluation - {metadata['version']}",
        "",
        "## Run Metadata",
        "",
        f"- Mode: `{metadata['mode']}`",
        f"- Cases: `{metadata['cases_path']}`",
        f"- Generated at: `{metadata['generated_at']}`",
        f"- Input cases: `{metadata['input_cases']}`",
        "",
        "## Summary Metrics",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Total cases | {metrics['total_cases']} |",
        f"| Failed runs | {metrics['failed_runs']} |",
        f"| Triage accuracy | {format_pct(metrics['triage_accuracy'])} |",
        f"| Handoff accuracy | {format_pct(metrics['handoff_accuracy'])} |",
        f"| Red-flag exact match | {format_pct(metrics['red_flag_exact_match_accuracy'])} |",
        f"| Red-flag macro recall | {format_pct(metrics['red_flag_macro_recall'])} |",
        f"| Red-flag macro precision | {format_pct(metrics['red_flag_macro_precision'])} |",
        f"| Emergency recall | {format_pct(metrics['emergency_recall'])} |",
        f"| Avg latency | {metrics['latency_ms']['avg']} ms |",
        f"| P95 latency | {metrics['latency_ms']['p95']} ms |",
        "",
        "## Priority Distribution",
        "",
        "### Expected",
        "",
        dict_table(metrics["expected_priority_distribution"]),
        "",
        "### Actual",
        "",
        dict_table(metrics["actual_priority_distribution"]),
        "",
        "## Confusion Matrix",
        "",
        confusion_table(metrics["confusion_matrix"]),
        "",
        "## Red-Flag Distribution",
        "",
        "### Expected",
        "",
        dict_table(metrics["expected_red_flag_distribution"]),
        "",
        "### Actual",
        "",
        dict_table(metrics["actual_red_flag_distribution"]),
        "",
        "## Red-Flag Code Metrics",
        "",
        red_flag_code_table(metrics["red_flag_code_metrics"]),
        "",
        "## Scenario Metrics",
        "",
        scenario_table(metrics["scenario_metrics"]),
        "",
        "## Failures",
        "",
    ]

    if failures:
        lines.extend(f"- `{failure['case_id']}`: {failure['error']}" for failure in failures[:20])
        if len(failures) > 20:
            lines.append(f"- ... {len(failures) - 20} more")
    else:
        lines.append("No runtime failures.")

    lines.append("")
    return "\n".join(lines)


def format_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.2f}%"


def dict_table(values: dict[str, int]) -> str:
    lines = ["| Label | Count |", "|---|---:|"]
    for key, value in sorted(values.items()):
        lines.append(f"| {key} | {value} |")
    return "\n".join(lines)


def confusion_table(matrix: dict[str, dict[str, int]]) -> str:
    actual_labels = sorted({actual for actuals in matrix.values() for actual in actuals})
    lines = ["| Expected \\ Actual | " + " | ".join(actual_labels) + " |"]
    lines.append("|---|" + "|".join("---:" for _ in actual_labels) + "|")
    for expected, actuals in matrix.items():
        counts = [str(actuals.get(label, 0)) for label in actual_labels]
        lines.append(f"| {expected} | " + " | ".join(counts) + " |")
    return "\n".join(lines)


def red_flag_code_table(metrics: dict[str, dict[str, Any]]) -> str:
    if not metrics:
        return "No red flags in expected or actual outputs."

    lines = [
        "| Code | TP | FP | FN | Precision | Recall |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for code, values in metrics.items():
        lines.append(
            f"| {code} | {values['true_positive']} | {values['false_positive']} | "
            f"{values['false_negative']} | {format_pct(values['precision'])} | "
            f"{format_pct(values['recall'])} |"
        )
    return "\n".join(lines)


def scenario_table(metrics: dict[str, dict[str, Any]]) -> str:
    lines = [
        "| Scenario | Cases | Triage accuracy | Handoff accuracy | Red-flag recall |",
        "|---|---:|---:|---:|---:|",
    ]
    for scenario, values in metrics.items():
        lines.append(
            f"| {scenario} | {values['total_cases']} | "
            f"{format_pct(values['triage_accuracy'])} | "
            f"{format_pct(values['handoff_accuracy'])} | "
            f"{format_pct(values['red_flag_macro_recall'])} |"
        )
    return "\n".join(lines)


def enforce_thresholds(config: EvalConfig, metrics: dict[str, Any]) -> None:
    failures = []
    triage_accuracy = metrics["triage_accuracy"]
    red_flag_recall = metrics["red_flag_macro_recall"]

    if (
        config.fail_under_triage_accuracy is not None
        and triage_accuracy is not None
        and triage_accuracy < config.fail_under_triage_accuracy
    ):
        failures.append(
            f"triage_accuracy {triage_accuracy:.4f} < {config.fail_under_triage_accuracy:.4f}"
        )

    if (
        config.fail_under_red_flag_recall is not None
        and red_flag_recall is not None
        and red_flag_recall < config.fail_under_red_flag_recall
    ):
        failures.append(
            f"red_flag_macro_recall {red_flag_recall:.4f} < {config.fail_under_red_flag_recall:.4f}"
        )

    if failures:
        raise SystemExit("Evaluation thresholds failed: " + "; ".join(failures))


async def main() -> None:
    config = parse_args()
    log_path = setup_logging(config)
    started = time.perf_counter()
    started_at = datetime.now(timezone.utc)

    logger.info(
        "Starting evaluation version=%s mode=%s cases=%s limit=%s output_dir=%s",
        config.version,
        config.mode,
        config.cases_path,
        config.limit,
        config.output_dir,
    )
    cases = load_cases(config.cases_path, config.limit)
    logger.info("Loaded %s cases", len(cases))
    predictions: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for index, case in enumerate(cases, start=1):
        case_id = case.get("case_id", f"case-{index}")
        logger.info("Running case %s/%s case_id=%s", index, len(cases), case_id)
        try:
            prediction = await run_one_case(case, config)
            predictions.append(prediction)
            logger.info(
                "Completed case_id=%s triage_match=%s expected=%s actual=%s expected_red_flags=%s actual_red_flags=%s latency_ms=%.2f",
                case_id,
                prediction["scores"]["triage_match"],
                prediction["expected"]["priority"],
                prediction["actual"]["priority"],
                ",".join(prediction["expected"]["red_flags"]) or "none",
                ",".join(prediction["actual"]["red_flags"]) or "none",
                prediction["latency_ms"],
            )
        except Exception as exc:
            logger.exception("Failed case_id=%s", case_id)
            failures.append(
                {
                    "case_id": case_id,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                }
            )

    metrics = summarize(predictions, failures)
    duration_seconds = time.perf_counter() - started
    run_dir = write_outputs(
        config,
        cases,
        predictions,
        failures,
        metrics,
        started_at,
        duration_seconds,
        log_path,
    )

    logger.info(
        "Evaluation complete run_dir=%s passed_runner=%s failed_runner=%s triage_accuracy=%s red_flag_recall=%s duration_seconds=%.3f",
        run_dir,
        metrics["total_cases"],
        metrics["failed_runs"],
        format_pct(metrics["triage_accuracy"]),
        format_pct(metrics["red_flag_macro_recall"]),
        duration_seconds,
    )

    print(f"Evaluation complete: {run_dir}")
    print(f"Cases: {metrics['total_cases']} passed runner, {metrics['failed_runs']} failed runner")
    print(f"Triage accuracy: {format_pct(metrics['triage_accuracy'])}")
    print(f"Red-flag macro recall: {format_pct(metrics['red_flag_macro_recall'])}")
    print(f"Report: {run_dir / 'report.md'}")
    print(f"Log: {log_path}")
    enforce_thresholds(config, metrics)


if __name__ == "__main__":
    asyncio.run(main())
