"""Fine-tune PhoBERT for three-class text-only medical-triage research."""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as functional
from torch.optim import AdamW
from torch.utils.data import DataLoader, Dataset
from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup

from src.graph_triage.common import (
    EMERGENCY_LABEL,
    TRIAGE_LABELS,
    evaluation_payload,
    load_data,
    save_json,
    save_markdown_report,
    set_seed,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/clean/golden.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("runs/bert"))
    parser.add_argument("--model", default="vinai/phobert-base-v2")
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--warmup-ratio", type=float, default=0.1)
    parser.add_argument("--emergency-loss-multiplier", type=float, default=1.5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--local-files-only", action="store_true")
    return parser.parse_args()


class TextDataset(Dataset):
    def __init__(self, texts: list[str], labels: np.ndarray):
        self.texts, self.labels = texts, labels

    def __len__(self) -> int:
        return len(self.labels)

    def __getitem__(self, index: int) -> tuple[str, int]:
        return self.texts[index], int(self.labels[index])


@dataclass
class Collator:
    tokenizer: Any
    max_length: int

    def __call__(self, batch: list[tuple[str, int]]) -> dict[str, torch.Tensor]:
        texts, labels = zip(*batch)
        encoded = self.tokenizer(list(texts), padding=True, truncation=True, max_length=self.max_length, return_tensors="pt")
        encoded["labels"] = torch.tensor(labels, dtype=torch.long)
        return encoded


def make_loader(texts: list[str], labels: np.ndarray, tokenizer: Any, max_length: int, batch_size: int, shuffle: bool) -> DataLoader:
    return DataLoader(TextDataset(texts, labels), batch_size=batch_size, shuffle=shuffle, collate_fn=Collator(tokenizer, max_length))


def evaluate(model: torch.nn.Module, data_loader: DataLoader, device: torch.device) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    model.eval()
    truth, predicted, probabilities = [], [], []
    with torch.inference_mode():
        for batch in data_loader:
            labels = batch.pop("labels").numpy()
            logits = model(**{name: value.to(device) for name, value in batch.items()}).logits
            truth.append(labels)
            predicted.append(logits.argmax(dim=1).cpu().numpy())
            probabilities.append(torch.softmax(logits, dim=1).cpu().numpy())
    return np.concatenate(truth), np.concatenate(predicted), np.concatenate(probabilities)


def main() -> None:
    args = parse_args()
    if args.epochs < 1 or args.batch_size < 1:
        raise ValueError("--epochs and --batch-size must be positive.")
    if args.emergency_loss_multiplier < 1:
        raise ValueError("--emergency-loss-multiplier must be at least 1.")
    set_seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
    random.seed(args.seed)
    device_name = "cuda" if args.device == "auto" and torch.cuda.is_available() else "cpu" if args.device == "auto" else args.device
    device = torch.device(device_name)
    if args.device == "cuda" and device.type != "cuda":
        raise RuntimeError("CUDA was requested but is unavailable.")

    dataset = load_data(args.input)
    frame = dataset.frame
    labels = frame["label_id"].to_numpy()

    config = AutoConfig.from_pretrained(args.model, local_files_only=args.local_files_only)
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=args.local_files_only)
    usable_max_length = config.max_position_embeddings - tokenizer.num_special_tokens_to_add(pair=False)
    if args.max_length > usable_max_length:
        raise ValueError(f"--max-length exceeds this model's usable limit of {usable_max_length} tokens.")
    label_to_id = {label: index for index, label in enumerate(TRIAGE_LABELS)}
    model = AutoModelForSequenceClassification.from_pretrained(
        args.model, num_labels=len(TRIAGE_LABELS), label2id=label_to_id,
        id2label={index: label for label, index in label_to_id.items()}, ignore_mismatched_sizes=True,
        local_files_only=args.local_files_only,
    ).to(device)
    texts = frame["text"].tolist()
    train_loader = make_loader(texts, labels, tokenizer, args.max_length, args.batch_size, True)
    evaluation_loader = make_loader(texts, labels, tokenizer, args.max_length, args.batch_size, False)
    class_counts = np.bincount(labels, minlength=len(TRIAGE_LABELS))
    class_weights = torch.tensor(len(labels) / (len(TRIAGE_LABELS) * class_counts), dtype=torch.float32, device=device)
    optimizer = AdamW(model.parameters(), lr=args.learning_rate, weight_decay=args.weight_decay)
    total_steps = max(1, len(train_loader) * args.epochs)
    scheduler = get_linear_schedule_with_warmup(optimizer, int(total_steps * args.warmup_ratio), total_steps)

    history: list[dict[str, Any]] = []
    emergency_index = TRIAGE_LABELS.index(EMERGENCY_LABEL)
    for epoch in range(1, args.epochs + 1):
        model.train()
        loss_total = 0.0
        for batch in train_loader:
            targets = batch.pop("labels").to(device)
            logits = model(**{name: value.to(device) for name, value in batch.items()}).logits
            base_loss = functional.cross_entropy(logits, targets, weight=class_weights, reduction="none")
            loss = (base_loss * torch.where(targets == emergency_index, args.emergency_loss_multiplier, 1.0)).mean()
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            loss_total += float(loss.item())
        history.append({"epoch": epoch, "train_loss": loss_total / len(train_loader)})
        print(f"epoch={epoch} loss={history[-1]['train_loss']:.4f}")

    train_true, train_prediction, train_probabilities = evaluate(model, evaluation_loader, device)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(args.output_dir / "model")
    tokenizer.save_pretrained(args.output_dir / "model")
    training_evaluation = evaluation_payload(train_true, train_prediction, train_probabilities)
    report = {
        "setup": {"input": str(args.input), "text_column": "patient", "excluded_columns": ["doctor"],
                  "model": args.model, "device": str(device), "max_length": args.max_length,
                  "evaluation": "training set only", "decision_rule": "three-class argmax", "seed": args.seed},
        "data_cleaning": dataset.summary,
        "train_rows": int(len(frame)), "history": history, "train": training_evaluation,
    }
    save_json(args.output_dir / "metrics.json", report)
    save_markdown_report(args.output_dir / "report.md", "PhoBERT training report", training_evaluation)
    predictions = frame.loc[:, ["source_row", "text", "raw_label", "triage_label"]].copy()
    predictions["prediction"] = [TRIAGE_LABELS[index] for index in train_prediction]
    for index, label in enumerate(TRIAGE_LABELS):
        predictions[f"prob_{label}"] = train_probabilities[:, index]
    predictions.to_csv(args.output_dir / "train_predictions.csv", index=False, encoding="utf-8-sig")
    print(training_evaluation["metrics"])
    print(f"Saved model and report to {args.output_dir}")


if __name__ == "__main__":
    main()
