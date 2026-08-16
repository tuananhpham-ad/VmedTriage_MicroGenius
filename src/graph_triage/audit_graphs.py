"""Validate a DeepSeek graph cache and create a reproducible manual-review sample."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

from src.graph_triage.common import load_data, save_json
from src.graph_triage.graph_schema import ClinicalGraph, validate_provenance
from src.graph_triage.patient_graph import PatientGraphBuilder


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/clean/golden.csv"))
    parser.add_argument("--graphs", type=Path, default=Path("data/graphs/deepseek_v4_flash_v1.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/graphs/deepseek_v4_flash_v1.audit.json"))
    parser.add_argument("--sample-output", type=Path, default=Path("data/graphs/deepseek_v4_flash_v1.review.md"))
    parser.add_argument("--sample-size", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.sample_size < 1:
        raise ValueError("--sample-size must be positive.")
    dataset = load_data(args.input)
    if not args.graphs.is_file():
        raise FileNotFoundError(f"Graph cache not found: {args.graphs}")
    records = {int(record["source_row"]): record for record in (json.loads(line) for line in args.graphs.read_text(encoding="utf-8").splitlines() if line.strip())}
    expected = set(dataset.frame["source_row"])
    if missing := expected.difference(records):
        raise ValueError(f"Graph cache is incomplete: {len(missing)} source rows are missing.")
    graphs, validated_rows = [], []
    for _, row in dataset.frame.iterrows():
        record = records[int(row["source_row"])]
        if record.get("text_sha256") != hashlib.sha256(row["text"].encode("utf-8")).hexdigest():
            raise ValueError(f"Text fingerprint mismatch at source row {row['source_row']}.")
        graph = ClinicalGraph.model_validate(record["graph"])
        validate_provenance(graph, row["text"])
        graphs.append(graph)
        validated_rows.append((row, graph))
    audit = PatientGraphBuilder().audit(graphs)
    audit.update({"schema_version": "patient_graph_v1", "input": str(args.input), "graphs": str(args.graphs), "rows_validated": len(graphs), "manual_review_checklist": ["target patient vs reporter/other experiencer", "explicit PRESENT/ABSENT and omitted UNKNOWN facts", "canonical concept plus source span", "episode/timeline separation", "location versus radiation", "temporal, functional, and family-extension attributes", "relation evidence and provenance"]})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    save_json(args.output, audit)

    sample = random.Random(args.seed).sample(validated_rows, k=min(args.sample_size, len(validated_rows)))
    lines = ["# Patient Graph manual review", "", "Review each case against the checklist in the adjacent audit JSON. Mark extraction errors before allowing full model training.", ""]
    for row, graph in sorted(sample, key=lambda item: int(item[0]["source_row"])):
        lines.extend([f"## Source row {row['source_row']}", "", "### Patient text", "", row["text"], "", "### Extracted graph", "", "```json", json.dumps(graph.model_dump(mode="json"), ensure_ascii=False, indent=2), "```", ""])
    args.sample_output.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    print(f"Saved audit to {args.output} and review sample to {args.sample_output}")


if __name__ == "__main__":
    main()
