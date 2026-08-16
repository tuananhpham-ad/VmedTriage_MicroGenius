"""Train a character TF-IDF + logistic-regression triage baseline."""

from __future__ import annotations

import argparse
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from src.graph_triage.common import (
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
    parser.add_argument("--output-dir", type=Path, default=Path("runs/logreg"))
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    set_seed(args.seed)
    dataset = load_data(args.input)
    frame, labels = dataset.frame, dataset.frame["label_id"].to_numpy()
    model = Pipeline([
        ("tfidf", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=2)),
        ("classifier", LogisticRegression(class_weight="balanced", max_iter=5000, random_state=args.seed)),
    ])
    model.fit(frame["text"], labels)
    prediction = model.predict(frame["text"])
    probabilities = model.predict_proba(frame["text"])
    training_evaluation = evaluation_payload(labels, prediction, probabilities)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, args.output_dir / "model.joblib")
    report = {
        "setup": {"input": str(args.input), "text_column": "patient", "excluded_columns": ["doctor"],
                  "model": "character word-boundary TF-IDF (3-5 grams) + balanced logistic regression",
                  "evaluation": "training set only", "seed": args.seed},
        "data_cleaning": dataset.summary,
        "class_distribution": frame["triage_label"].value_counts().reindex(TRIAGE_LABELS).to_dict(),
        "train_rows": int(len(frame)), "train": training_evaluation,
    }
    save_json(args.output_dir / "metrics.json", report)
    save_markdown_report(args.output_dir / "report.md", "Logistic Regression training report", training_evaluation)
    predictions = frame.loc[:, ["source_row", "text", "raw_label", "triage_label"]].copy()
    predictions["prediction"] = [TRIAGE_LABELS[index] for index in prediction]
    for index, label in enumerate(TRIAGE_LABELS):
        predictions[f"prob_{label}"] = probabilities[:, index]
    predictions.to_csv(args.output_dir / "train_predictions.csv", index=False, encoding="utf-8-sig")
    print(training_evaluation["metrics"])
    print(f"Saved model and report to {args.output_dir}")


if __name__ == "__main__":
    main()
