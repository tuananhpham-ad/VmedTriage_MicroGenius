"""Shared data, split, and evaluation utilities for triage experiments."""

from __future__ import annotations

import json
import random
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)
from sklearn.model_selection import StratifiedGroupKFold

from src.graph_triage.labels import EMERGENCY_LABEL, LABEL_ALIASES, TRIAGE_LABELS, normalize_label

# Re-export để các script train cũ vẫn `from ...common import TRIAGE_LABELS` được. Định nghĩa thật
# nằm ở `labels.py` - module đó không kéo theo scikit-learn/pandas nên đường inference dùng được.
__all__ = [
    "EMERGENCY_LABEL", "LABEL_ALIASES", "TRIAGE_LABELS", "PreparedData", "evaluation_payload",
    "load_data", "normalize_label", "repair_mojibake", "save_json", "save_markdown_report",
    "set_seed", "stratified_group_split", "text_group",
]


@dataclass(frozen=True)
class PreparedData:
    frame: pd.DataFrame
    summary: dict[str, int]


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)


def repair_mojibake(value: str) -> str:
    """Repair one safe UTF-8-as-Latin-1 corruption pass if present."""
    if not any(marker in value for marker in ("Ãƒ", "Ã„", "Ã‚", "Ã¢â‚¬")):
        return value
    try:
        return value.encode("latin1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def text_group(value: str) -> str:
    """Stable group ID that keeps exact normalized patient reports together."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).casefold()).strip()


def load_data(input_path: Path, text_column: str = "patient", label_column: str = "status") -> PreparedData:
    """Load only patient text and labels; ``doctor`` is deliberately ignored."""
    data = pd.read_csv(input_path, encoding="utf-8-sig", skipinitialspace=True)
    missing = {text_column, label_column}.difference(data.columns)
    if missing:
        raise ValueError(f"Missing CSV columns: {sorted(missing)}. Available: {list(data.columns)}")
    prepared = pd.DataFrame({
        "source_row": np.arange(2, len(data) + 2),
        "text": data[text_column].fillna("").astype(str).map(repair_mojibake).str.strip(),
        "raw_label": data[label_column].fillna("").astype(str).str.strip(),
    })
    prepared["triage_label"] = prepared["raw_label"].map(normalize_label)
    prepared = prepared[prepared["text"].ne("") & prepared["triage_label"].notna()].copy()
    prepared["label_id"] = prepared["triage_label"].map({label: index for index, label in enumerate(TRIAGE_LABELS)})
    prepared["group_id"] = prepared["text"].map(text_group)
    prepared.reset_index(drop=True, inplace=True)
    counts = prepared["triage_label"].value_counts().reindex(TRIAGE_LABELS, fill_value=0)
    if counts.min() < 3:
        raise ValueError("Each triage class needs at least three usable examples.")
    return PreparedData(prepared, {
        "rows_before_cleaning": len(data), "rows_used": len(prepared),
        "rows_dropped": len(data) - len(prepared), "unique_text_groups": int(prepared["group_id"].nunique()),
    })


def stratified_group_split(labels: np.ndarray, groups: np.ndarray, fraction: float, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Make a stratified group holdout split without exact-text overlap."""
    if not 0 < fraction < 0.5:
        raise ValueError("Split fraction must be in (0, 0.5).")
    folds = round(1 / fraction)
    if not np.isclose(1 / folds, fraction, atol=0.01):
        raise ValueError("Use a reciprocal split fraction such as 0.2 or 0.125 for grouped stratification.")
    splitter = StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=seed)
    indices = np.arange(len(labels))
    train_index, holdout_index = next(splitter.split(indices, labels, groups))
    if set(groups[train_index]).intersection(groups[holdout_index]):
        raise RuntimeError("Group leakage detected in split construction.")
    return train_index, holdout_index


def evaluation_payload(y_true: np.ndarray, y_pred: np.ndarray, probabilities: np.ndarray) -> dict[str, Any]:
    emergency_index = TRIAGE_LABELS.index(EMERGENCY_LABEL)
    precision, recall, emergency_f1, support = precision_recall_fscore_support(y_true, y_pred, labels=[emergency_index], zero_division=0)
    label_ids = list(range(len(TRIAGE_LABELS)))
    return {
        "metrics": {
            "accuracy": float(accuracy_score(y_true, y_pred)),
            "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
            "macro_precision": float(precision_recall_fscore_support(y_true, y_pred, average="macro", zero_division=0)[0]),
            "macro_recall": float(precision_recall_fscore_support(y_true, y_pred, average="macro", zero_division=0)[1]),
            "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
            "weighted_f1": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
            "emergency_precision": float(precision[0]), "emergency_recall": float(recall[0]),
            "emergency_f1": float(emergency_f1[0]), "emergency_false_negative_rate": float(1 - recall[0]),
            "emergency_support": int(support[0]), "mean_max_probability": float(np.max(probabilities, axis=1).mean()),
        },
        "per_class": classification_report(y_true, y_pred, labels=label_ids, target_names=list(TRIAGE_LABELS), output_dict=True, zero_division=0),
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=label_ids).tolist(),
    }


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def save_markdown_report(path: Path, title: str, evaluation: dict[str, Any], evaluation_note: str = "Evaluation is on the same full dataset used for training. These values measure training fit, not generalization or clinical safety.") -> None:
    """Write the requested headline metrics and confusion matrix as Markdown."""
    metrics = evaluation["metrics"]
    matrix = evaluation["confusion_matrix"]
    lines = [
        f"# {title}",
        "",
        f"> {evaluation_note}",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key in ("accuracy", "macro_precision", "macro_recall", "macro_f1", "emergency_precision", "emergency_recall", "emergency_f1"):
        lines.append(f"| {key} | {metrics[key]:.4f} |")
    lines.extend(["", "## Confusion matrix", "", "Rows are true labels; columns are predicted labels.", ""])
    lines.append("| true \\ predicted | " + " | ".join(TRIAGE_LABELS) + " |")
    lines.append("|---|" + "---:|" * len(TRIAGE_LABELS))
    for label, row in zip(TRIAGE_LABELS, matrix):
        lines.append("| " + label + " | " + " | ".join(str(value) for value in row) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
