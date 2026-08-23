"""Run graph-triage inference for one Vietnamese Semigran case selected by ID.

Example:
    python eval/scripts/run_graph_triage_infer.py --id semigran_37
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.scripts.run_graph_triage_eval import (  # noqa: E402
    build_agent,
    final_label_vi,
    load_cases,
    model_probability_lines,
)
from src.config import get_settings  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run one Vietnamese Semigran case through DeepSeek graph extraction, "
            "the available local models, and the OpenAI decision model."
        )
    )
    parser.add_argument("--id", dest="case_id", required=True, help="Semigran case ID, for example semigran_37.")
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("data/semigran_vignettes_vi.jsonl"),
        help="Vietnamese Semigran JSONL input.",
    )
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument(
        "--model",
        default=get_settings().openai_model_name,
        help="OpenAI decision model; defaults to OPENAI_MODEL_NAME from .env.",
    )
    parser.add_argument("--max-length", type=int, default=256, help="Maximum PhoBERT input length.")
    parser.add_argument("--max-tokens", type=int, default=1100, help="Maximum tokens for the GPT response.")
    parser.add_argument(
        "--skip-bert", action="store_true",
        help="Exclude PhoBERT from the ensemble, matching run_graph_triage_eval.py.",
    )
    parser.add_argument(
        "--skip-fusion", action="store_true",
        help="Exclude PhoBERT+HGT fusion, matching run_graph_triage_eval.py.",
    )
    parser.add_argument("--output", type=Path, help="Optional UTF-8 JSON result path.")
    args = parser.parse_args(argv)
    if args.max_length < 1 or args.max_tokens < 1:
        parser.error("--max-length and --max-tokens must be positive.")
    return args


def select_case(cases: list[Any], case_id: str) -> Any:
    """Return the requested case or fail clearly before loading any models."""
    for case in cases:
        if case.case_id == case_id:
            return case
    raise ValueError(f"No Semigran case with id={case_id!r} was found in the supplied --cases file.")


def build_payload(case: Any, result: dict[str, Any]) -> dict[str, Any]:
    """Add case metadata and a concise model summary to the raw inference result."""
    predicted_label_vi = final_label_vi(result)
    return {
        "id": case.case_id,
        "case_description_vi": case.patient_text,
        "expected_urgency_level_vi": case.expected_label_vi,
        "predicted_urgency_level_vi": predicted_label_vi,
        "is_correct": predicted_label_vi == case.expected_label_vi,
        "model_probability_summary": model_probability_lines(result),
        "inference_result": result,
    }


def main(argv: list[str] | None = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    case = select_case(load_cases(args.cases), args.case_id)
    result = build_agent(args).decide(case.patient_text)
    payload = json.dumps(build_payload(case, result), ensure_ascii=False, indent=2)
    print(payload)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
        print(f"Saved inference result to {args.output}")


if __name__ == "__main__":
    main()
