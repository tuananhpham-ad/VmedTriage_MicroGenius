"""Run the research-only triage ensemble for one patient report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch

from src.graph_triage.agent.decision import (
    BertPredictor,
    DecisionAgent,
    FusionPredictor,
    GraphResolver,
    LogRegPredictor,
)
from src.graph_triage.common import load_data


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
    parser.add_argument("--max-length", type=int, default=256, help="Maximum tokens for standalone PhoBERT inference.")
    parser.add_argument("--allow-live-extraction", action="store_true", help="Call DeepSeek when no exact graph-cache match exists; this consumes API tokens.")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--output", type=Path, help="Optional JSON result path.")
    return parser.parse_args()


def resolve_text(args: argparse.Namespace) -> str:
    if args.patient is not None:
        return args.patient.strip()
    dataset = load_data(args.input)
    matches = dataset.frame.loc[dataset.frame["source_row"] == args.source_row, "text"]
    if matches.empty:
        raise ValueError(f"source_row {args.source_row} is not a usable patient record in {args.input}.")
    return str(matches.iloc[0])


def build_ensemble(args: argparse.Namespace, device: torch.device) -> DecisionAgent:
    return DecisionAgent(
        logreg=LogRegPredictor(args.logreg_model),
        bert=BertPredictor(args.bert_model, device, args.max_length),
        graph_resolver=GraphResolver(args.graphs, args.allow_live_extraction),
        fusion=FusionPredictor(args.fusion_model, device) if args.fusion_model else None,
    )


def main() -> None:
    args = parse_args()
    if args.max_length < 1:
        raise ValueError("--max-length must be positive.")
    device_name = "cuda" if args.device == "auto" and torch.cuda.is_available() else "cpu" if args.device == "auto" else args.device
    device = torch.device(device_name)
    if args.device == "cuda" and device.type != "cuda":
        raise RuntimeError("CUDA was requested but is unavailable.")
    agent = build_ensemble(args, device)
    result = agent.decide(resolve_text(args))
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    print(payload)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
        print(f"Saved decision result to {args.output}")


if __name__ == "__main__":
    main()
