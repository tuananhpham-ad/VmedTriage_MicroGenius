"""Train a PhoBERT-document + HGT-patient-graph gated fusion model."""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as functional
from torch import nn
from torch.optim import AdamW
from torch.utils.data import DataLoader, Dataset
from transformers import AutoConfig, AutoModel, AutoTokenizer, get_linear_schedule_with_warmup

from src.graph_triage.common import (
    TRIAGE_LABELS,
    evaluation_payload,
    load_data,
    save_json,
    save_markdown_report,
    set_seed,
    stratified_group_split,
)
from src.graph_triage.hgt_model import HGTEncoder
from src.graph_triage.patient_graph import EDGE_TYPES, FEATURE_DIMENSION, NODE_TYPES, PatientGraphBuilder
from src.graph_triage.train_hgt import load_graphs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/clean/golden.csv"))
    parser.add_argument("--graphs", type=Path, default=Path("data/graphs/deepseek_v4_flash_v1.jsonl"))
    parser.add_argument("--output-dir", type=Path, default=Path("runs/fusion"))
    parser.add_argument("--text-model", default="vinai/phobert-base-v2")
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--hidden-channels", type=int, default=64)
    parser.add_argument("--fusion-channels", type=int, default=256)
    parser.add_argument("--heads", type=int, default=2)
    parser.add_argument("--layers", type=int, default=2)
    parser.add_argument("--dropout", type=float, default=0.2)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--graph-learning-rate", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--warmup-ratio", type=float, default=0.1)
    parser.add_argument("--emergency-loss-multiplier", type=float, default=1.5)
    parser.add_argument("--holdout-fraction", type=float, default=0.2)
    parser.add_argument("--train-all", action="store_true", help="Fit a final model on every case; metrics then measure training fit only.")
    parser.add_argument("--freeze-text-encoder", action="store_true", help="Train only the graph and fusion heads after loading PhoBERT.")
    parser.add_argument("--local-files-only", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    return parser.parse_args()


class FusionDataset(Dataset):
    def __init__(self, texts: list[str], graphs: list, labels: np.ndarray):
        self.texts, self.graphs, self.labels = texts, graphs, labels

    def __len__(self) -> int:
        return len(self.labels)

    def __getitem__(self, index: int):
        return self.texts[index], self.graphs[index], int(self.labels[index])


@dataclass
class FusionCollator:
    tokenizer: Any
    max_length: int

    def __call__(self, rows):
        try:
            from torch_geometric.data import Batch
        except ImportError as error:
            raise RuntimeError("Fusion requires torch-geometric. Run: pip install -r requirements.txt") from error
        texts, graphs, labels = zip(*rows)
        encoded = self.tokenizer(list(texts), padding=True, truncation=True, max_length=self.max_length, return_tensors="pt")
        encoded["graph"] = Batch.from_data_list(list(graphs))
        encoded["labels"] = torch.tensor(labels, dtype=torch.long)
        return encoded


def make_loader(texts: list[str], graphs: list, labels: np.ndarray, tokenizer, max_length: int, batch_size: int, shuffle: bool) -> DataLoader:
    return DataLoader(FusionDataset(texts, graphs, labels), batch_size=batch_size, shuffle=shuffle, collate_fn=FusionCollator(tokenizer, max_length))


class GatedFusionClassifier(nn.Module):
    def __init__(self, text_encoder: nn.Module, text_channels: int, hidden_channels: int, fusion_channels: int, heads: int, layers: int, dropout: float):
        super().__init__()
        self.text_encoder = text_encoder
        self.graph_encoder = HGTEncoder(hidden_channels, heads, layers, dropout)
        self.text_projection = nn.Sequential(nn.Linear(text_channels, fusion_channels), nn.ReLU(), nn.Dropout(dropout))
        self.graph_projection = nn.Sequential(nn.Linear(hidden_channels, fusion_channels), nn.ReLU(), nn.Dropout(dropout))
        self.gate = nn.Sequential(nn.Linear(fusion_channels * 2, fusion_channels), nn.Sigmoid())
        self.classifier = nn.Linear(fusion_channels, len(TRIAGE_LABELS))

    def forward(self, text_inputs: dict[str, torch.Tensor], graph) -> tuple[torch.Tensor, torch.Tensor]:
        document_embedding = self.text_encoder(**text_inputs).last_hidden_state[:, 0]
        text_embedding = self.text_projection(document_embedding)
        graph_embedding = self.graph_projection(self.graph_encoder(graph.x_dict, graph.edge_index_dict))
        gate = self.gate(torch.cat((text_embedding, graph_embedding), dim=1))
        fused_embedding = gate * text_embedding + (1 - gate) * graph_embedding
        return self.classifier(fused_embedding), gate


def evaluate(model: nn.Module, loader: DataLoader, device: torch.device) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    model.eval()
    truth, prediction, probabilities, gates = [], [], [], []
    with torch.inference_mode():
        for batch in loader:
            targets = batch.pop("labels").numpy()
            graph = batch.pop("graph").to(device)
            text_inputs = {name: value.to(device) for name, value in batch.items()}
            logits, gate = model(text_inputs, graph)
            truth.append(targets)
            prediction.append(logits.argmax(dim=1).cpu().numpy())
            probabilities.append(torch.softmax(logits, dim=1).cpu().numpy())
            gates.append(gate.cpu().numpy())
    return np.concatenate(truth), np.concatenate(prediction), np.concatenate(probabilities), np.concatenate(gates)


def main() -> None:
    args = parse_args()
    if args.hidden_channels % args.heads or min(args.layers, args.batch_size, args.epochs, args.fusion_channels) < 1:
        raise ValueError("hidden-channels must divide evenly by heads; channels, layers, batch-size, and epochs must be positive.")
    if args.emergency_loss_multiplier < 1 or not 0 <= args.warmup_ratio < 1 or min(args.learning_rate, args.graph_learning_rate) <= 0:
        raise ValueError("Learning rates must be positive; emergency-loss-multiplier must be >= 1 and warmup-ratio must be in [0, 1).")
    try:
        import torch_geometric  # noqa: F401
    except ImportError as error:
        raise RuntimeError("Fusion requires torch-geometric. Run: pip install -r requirements.txt") from error
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
    frame, labels = dataset.frame, dataset.frame["label_id"].to_numpy()
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

    config = AutoConfig.from_pretrained(args.text_model, local_files_only=args.local_files_only)
    tokenizer = AutoTokenizer.from_pretrained(args.text_model, local_files_only=args.local_files_only)
    usable_max_length = config.max_position_embeddings - tokenizer.num_special_tokens_to_add(pair=False)
    if args.max_length > usable_max_length:
        raise ValueError(f"--max-length exceeds this model's usable limit of {usable_max_length} tokens.")
    text_encoder = AutoModel.from_pretrained(args.text_model, local_files_only=args.local_files_only)
    if args.freeze_text_encoder:
        for parameter in text_encoder.parameters():
            parameter.requires_grad = False
    model = GatedFusionClassifier(text_encoder, config.hidden_size, args.hidden_channels, args.fusion_channels, args.heads, args.layers, args.dropout).to(device)
    train_loader = make_loader(frame.iloc[train_index]["text"].tolist(), [graphs[index] for index in train_index], labels[train_index], tokenizer, args.max_length, args.batch_size, True)
    evaluation_loader = make_loader(frame.iloc[evaluation_index]["text"].tolist(), [graphs[index] for index in evaluation_index], labels[evaluation_index], tokenizer, args.max_length, args.batch_size, False)
    train_labels = labels[train_index]
    counts = np.bincount(train_labels, minlength=len(TRIAGE_LABELS))
    class_weights = torch.tensor(len(train_labels) / (len(TRIAGE_LABELS) * counts), dtype=torch.float32, device=device)
    graph_and_fusion_parameters = [parameter for name, parameter in model.named_parameters() if not name.startswith("text_encoder.") and parameter.requires_grad]
    optimizer_groups = [{"params": graph_and_fusion_parameters, "lr": args.graph_learning_rate}]
    text_parameters = [parameter for parameter in model.text_encoder.parameters() if parameter.requires_grad]
    if text_parameters:
        optimizer_groups.append({"params": text_parameters, "lr": args.learning_rate})
    optimizer = AdamW(optimizer_groups, weight_decay=args.weight_decay)
    total_steps = max(1, len(train_loader) * args.epochs)
    scheduler = get_linear_schedule_with_warmup(optimizer, int(total_steps * args.warmup_ratio), total_steps)
    emergency_index = TRIAGE_LABELS.index("cap_cuu")
    history = []
    for epoch in range(1, args.epochs + 1):
        model.train()
        if args.freeze_text_encoder:
            model.text_encoder.eval()
        total_loss = 0.0
        for batch in train_loader:
            targets = batch.pop("labels").to(device)
            graph = batch.pop("graph").to(device)
            text_inputs = {name: value.to(device) for name, value in batch.items()}
            logits, _ = model(text_inputs, graph)
            losses = functional.cross_entropy(logits, targets, weight=class_weights, reduction="none")
            loss = (losses * torch.where(targets == emergency_index, args.emergency_loss_multiplier, 1.0)).mean()
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            total_loss += float(loss.item())
        history.append({"epoch": epoch, "train_loss": total_loss / len(train_loader)})
        print(f"epoch={epoch} loss={history[-1]['train_loss']:.4f}")

    truth, prediction, probabilities, gates = evaluate(model, evaluation_loader, device)
    evaluation = evaluation_payload(truth, prediction, probabilities)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    model.text_encoder.save_pretrained(args.output_dir / "text_encoder")
    tokenizer.save_pretrained(args.output_dir / "text_encoder")
    torch.save({"model_state_dict": model.state_dict(), "text_model": args.text_model, "text_channels": config.hidden_size, "hidden_channels": args.hidden_channels, "fusion_channels": args.fusion_channels, "heads": args.heads, "layers": args.layers, "dropout": args.dropout, "max_length": args.max_length, "node_types": NODE_TYPES, "edge_types": EDGE_TYPES, "feature_dimension": FEATURE_DIMENSION}, args.output_dir / "model.pt")
    report = {"setup": {"input": str(args.input), "graphs": str(args.graphs), "text_model": args.text_model, "model": "PhoBERT + HGT gated fusion", "evaluation": evaluation_name, "device": str(device), "seed": args.seed, "holdout_fraction": None if args.train_all else args.holdout_fraction, "freeze_text_encoder": args.freeze_text_encoder, "text_learning_rate": args.learning_rate, "graph_learning_rate": args.graph_learning_rate}, "data_cleaning": dataset.summary, "graph_audit": builder.audit(clinical_graphs), "history": history, "mean_text_gate": float(gates.mean()), "evaluation": evaluation}
    save_json(args.output_dir / "metrics.json", report)
    save_json(args.output_dir / "graph_schema.json", {"node_types": NODE_TYPES, "edge_types": EDGE_TYPES, "feature_dimension": FEATURE_DIMENSION})
    save_markdown_report(args.output_dir / "report.md", "PhoBERT + HGT gated fusion report", evaluation, evaluation_note)
    predictions = frame.iloc[evaluation_index].loc[:, ["source_row", "text", "raw_label", "triage_label"]].copy()
    predictions["prediction"] = [TRIAGE_LABELS[index] for index in prediction]
    predictions["mean_text_gate"] = gates.mean(axis=1)
    for index, label in enumerate(TRIAGE_LABELS):
        predictions[f"prob_{label}"] = probabilities[:, index]
    predictions.to_csv(args.output_dir / ("train_predictions.csv" if args.train_all else "holdout_predictions.csv"), index=False, encoding="utf-8-sig")
    print(evaluation["metrics"])
    print(f"Saved fusion model and report to {args.output_dir}")


if __name__ == "__main__":
    main()
