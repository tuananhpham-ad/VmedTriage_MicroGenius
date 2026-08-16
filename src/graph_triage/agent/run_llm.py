"""Run the GPT-4o tool-calling decision agent for one patient report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch

from src.config import get_settings
from src.graph_triage.agent.llm_decision import ToolCallingDecisionAgent
from src.graph_triage.agent.run import build_ensemble, resolve_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--patient", help="Exact patient report. It must exist in graph cache unless live extraction is enabled.")
    source.add_argument("--source-row", type=int, help="CSV source_row from data/clean/golden.csv.")
    parser.add_argument("--input", type=Path, default=Path("data/clean/golden.csv"))
    parser.add_argument("--logreg-model", type=Path, default=Path("runs/logreg_full/model.joblib"))
    parser.add_argument("--bert-model", type=Path, default=Path("runs/bert_full/model"))
    parser.add_argument("--fusion-model", type=Path, help="Bỏ trống khi chưa train fusion; agent chạy với logreg + bert.")
    parser.add_argument("--graphs", type=Path, help="Graph cache JSONL. Bỏ trống thì mọi ca đều cần --allow-live-extraction.")
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--allow-live-extraction", action="store_true", help="Call DeepSeek for a graph-cache miss; this consumes separate API tokens.")
    parser.add_argument("--model", default=get_settings().openai_model_name, help="OpenAI decision model. Mặc định lấy OPENAI_MODEL_NAME trong .env.")
    parser.add_argument("--max-tokens", type=int, default=1100)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--output", type=Path, help="Optional JSON result path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.max_length < 1 or args.max_tokens < 1:
        raise ValueError("--max-length and --max-tokens must be positive.")
    device_name = "cuda" if args.device == "auto" and torch.cuda.is_available() else "cpu" if args.device == "auto" else args.device
    device = torch.device(device_name)
    if args.device == "cuda" and device.type != "cuda":
        raise RuntimeError("CUDA was requested but is unavailable.")
    result = ToolCallingDecisionAgent(build_ensemble(args, device), model=args.model, max_tokens=args.max_tokens).decide(resolve_text(args))
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    print(payload)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
        print(f"Saved agent decision to {args.output}")


if __name__ == "__main__":
    main()
