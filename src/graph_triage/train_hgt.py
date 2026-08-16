"""Train HGT from DeepSeek-extracted, validated Patient Graph JSONL."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as functional
from torch import nn

from src.graph_triage.common import (
    TRIAGE_LABELS,
    evaluation_payload,
    load_data,
    save_json,
    save_markdown_report,
    set_seed,
    stratified_group_split,
)
from src.graph_triage.graph_schema import ClinicalGraph
from src.graph_triage.hgt_model import HGTEncoder
from src.graph_triage.patient_graph import EDGE_TYPES, FEATURE_DIMENSION, NODE_TYPES, PatientGraphBuilder


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/clean/golden.csv"))
    parser.add_argument("--graphs", type=Path, default=Path("data/graphs/deepseek_v4_flash_v1.jsonl"))
    parser.add_argument("--output-dir", type=Path, default=Path("runs/hgt"))
    parser.add_argument("--hidden-channels", type=int, default=64)
    parser.add_argument("--heads", type=int, default=2)
    parser.add_argument("--layers", type=int, default=2)
    parser.add_argument("--dropout", type=float, default=0.2)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--emergency-loss-multiplier", type=float, default=1.5)
    parser.add_argument("--holdout-fraction", type=float, default=0.2)
    parser.add_argument("--train-all", action="store_true", help="Fit a final model on every case; metrics then measure training fit only.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    return parser.parse_args()


class HGTClassifier(nn.Module):
    def __init__(self, hidden_channels: int, heads: int, layers: int, dropout: float):
        super().__init__()
        self.encoder = HGTEncoder(hidden_channels, heads, layers, dropout)
        self.classifier = nn.Linear(hidden_channels, len(TRIAGE_LABELS))

    def forward(self, x_dict, edge_index_dict) -> torch.Tensor:
        return self.classifier(self.encoder(x_dict, edge_index_dict))


def load_graphs(path: Path, frame) -> list[ClinicalGraph]:
    if not path.is_file():
        raise FileNotFoundError(f"Graph cache not found: {path}. Run extract_graphs first.")
    cached = {int(item["source_row"]): item for item in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())}
    expected = set(frame["source_row"])
    if missing := expected.difference(cached):
        raise ValueError(f"Graph cache is incomplete: {len(missing)} source rows are missing.")
    graphs = []
    for _, row in frame.iterrows():
        item = cached[int(row["source_row"])]
        fingerprint = hashlib.sha256(row["text"].encode("utf-8")).hexdigest()
        if item["text_sha256"] != fingerprint:
            raise ValueError(f"Text fingerprint mismatch at source row {row['source_row']}.")
        graphs.append(ClinicalGraph.model_validate(item["graph"]))
    return graphs


def evaluate(model: nn.Module, loader, device: torch.device):
    model.eval()
    truth = []
    prediction = []
    probabilities = []
    with torch.inference_mode():
        for batch in loader:
            batch = batch.to(device)
            logits = model(batch.x_dict, batch.edge_index_dict)
            truth.append(batch.y.cpu().numpy())
            prediction.append(logits.argmax(dim=1).cpu().numpy())
            probabilities.append(torch.softmax(logits, dim=1).cpu().numpy())
    return np.concatenate(truth), np.concatenate(prediction), np.concatenate(probabilities)


def main() -> None:
    args = parse_args()
    if args.hidden_channels % args.heads or min(args.layers, args.batch_size, args.epochs) < 1:
        raise ValueError("hidden-channels must divide evenly by heads; layers, batch-size, and epochs must be positive.")
    try:
        from torch_geometric.loader import DataLoader
    except ImportError as error:
        raise RuntimeError("HGT requires torch-geometric. Run: pip install -r requirements.txt") from error
    set_seed(args.seed)
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
    device_name = "cuda" if args.device == "auto" and torch.cuda.is_available() else "cpu" if args.device == "auto" else args.device
    device = torch.device(device_name)
    if args.device == "cuda" and device.type != "cuda":
        raise RuntimeError("CUDA was requested but is unavailable.")
    dataset = load_data(args.input)
    frame = dataset.frame
    labels = frame["label_id"].to_numpy()
    clinical_graphs = load_graphs(args.graphs, frame)
    builder = PatientGraphBuilder()
    graphs = [builder.build(graph, int(label)) for graph, label in zip(clinical_graphs, labels)]
    if args.train_all:
        train_index = evaluation_index = np.arange(len(graphs))
        evaluation_name = "training set only"
        evaluation_note = "Evaluation is on the same full dataset used for training. These values measure training fit, not generalization or clinical safety."
    else:
        train_index, evaluation_index = stratified_group_split(labels, frame["group_id"].to_numpy(), args.holdout_fraction, args.seed)
        evaluation_name = "grouped holdout set"
        evaluation_note = "Evaluation is on a grouped holdout split; exact normalized patient reports do not overlap with training. This is still research-only, not clinical-safety evidence."
    train_graphs = [graphs[index] for index in train_index]
    evaluation_graphs = [graphs[index] for index in evaluation_index]
    train_loader = DataLoader(train_graphs, batch_size=args.batch_size, shuffle=True)
    evaluation_loader = DataLoader(evaluation_graphs, batch_size=args.batch_size, shuffle=False)
    model = HGTClassifier(args.hidden_channels, args.heads, args.layers, args.dropout).to(device)
    train_labels = labels[train_index]
    counts = np.bincount(train_labels, minlength=len(TRIAGE_LABELS))
    weights = torch.tensor(len(train_labels) / (len(TRIAGE_LABELS) * counts), dtype=torch.float32, device=device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=args.weight_decay)
    emergency = TRIAGE_LABELS.index("cap_cuu")
    history = []
    for epoch in range(1, args.epochs + 1):
        model.train()
        total_loss = 0.0
        for batch in train_loader:
            batch = batch.to(device)
            logits = model(batch.x_dict, batch.edge_index_dict)
            targets = batch.y.view(-1)
            losses = functional.cross_entropy(logits, targets, weight=weights, reduction="none")
            loss = (losses * torch.where(targets == emergency, args.emergency_loss_multiplier, 1.0)).mean()
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            total_loss += float(loss.item())
        history.append({"epoch": epoch, "train_loss": total_loss / len(train_loader)})
        print(f"epoch={epoch} loss={history[-1]['train_loss']:.4f}")
    truth, prediction, probabilities = evaluate(model, evaluation_loader, device)
    training_evaluation = evaluation_payload(truth, prediction, probabilities)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    torch.save({"model_state_dict": model.state_dict(), "node_types": NODE_TYPES, "edge_types": EDGE_TYPES, "feature_dimension": FEATURE_DIMENSION}, args.output_dir / "model.pt")
    report = {"setup": {"input": str(args.input), "graphs": str(args.graphs), "model": "Heterogeneous Graph Transformer", "evaluation": evaluation_name, "device": str(device), "seed": args.seed, "holdout_fraction": None if args.train_all else args.holdout_fraction}, "data_cleaning": dataset.summary, "graph_audit": builder.audit(clinical_graphs), "history": history, "evaluation": training_evaluation}
    save_json(args.output_dir / "metrics.json", report)
    save_json(args.output_dir / "graph_schema.json", {"node_types": NODE_TYPES, "edge_types": EDGE_TYPES, "feature_dimension": FEATURE_DIMENSION})
    save_markdown_report(args.output_dir / "report.md", "HGT training report", training_evaluation, evaluation_note)
    predictions = frame.iloc[evaluation_index].loc[:, ["source_row", "text", "raw_label", "triage_label"]].copy()
    predictions["prediction"] = [TRIAGE_LABELS[index] for index in prediction]
    for index, label in enumerate(TRIAGE_LABELS):
        predictions[f"prob_{label}"] = probabilities[:, index]
    predictions.to_csv(args.output_dir / ("train_predictions.csv" if args.train_all else "holdout_predictions.csv"), index=False, encoding="utf-8-sig")
    print(training_evaluation["metrics"])
    print(f"Saved HGT model and report to {args.output_dir}")


if __name__ == "__main__":
    main()
