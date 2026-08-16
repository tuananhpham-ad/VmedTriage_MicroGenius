"""Extract and cache validated Patient Graph JSONL via DeepSeek."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from src.graph_triage.common import load_data
from src.graph_triage.deepseek_extractor import DeepSeekExtractor, FatalExtractionError
from src.graph_triage.graph_schema import ClinicalGraph


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/clean/golden.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/graphs/deepseek_v4_flash_v1.jsonl"))
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--limit", type=int, help="Use for a low-cost pilot before full extraction.")
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--max-tokens", type=int, default=4000)
    parser.add_argument("--workers", type=int, default=8, help="Concurrent DeepSeek requests.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.limit is not None and args.limit < 1:
        raise ValueError("--limit must be positive.")
    if args.workers < 1:
        raise ValueError("--workers must be positive.")
    dataset = load_data(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    completed: set[int] = set()
    if args.output.exists():
        for line in args.output.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                try:
                    ClinicalGraph.model_validate(record["graph"])
                except Exception as error:
                    raise ValueError(f"Existing cache {args.output} is not patient_graph_v1. Use a new --output path instead of mixing schemas.") from error
                completed.add(record["source_row"])
    extractor = DeepSeekExtractor(model=args.model, retries=args.retries, max_tokens=args.max_tokens)
    candidates = dataset.frame.iloc[:args.limit] if args.limit else dataset.frame
    todo = [(int(row["source_row"]), row["text"]) for _, row in candidates.iterrows() if int(row["source_row"]) not in completed]
    written, failures = 0, []
    write_lock = threading.Lock()
    aborted = threading.Event()

    with args.output.open("a", encoding="utf-8", newline="\n") as handle:
        def extract_one(source_row: int, text: str) -> None:
            """Persist each finished row immediately so an interrupted run stays resumable."""
            nonlocal written
            if aborted.is_set():  # An account-level failure would hit this row too.
                return
            graph = extractor.extract(text)
            record = {
                "source_row": source_row,
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "graph": graph.model_dump(mode="json"),
            }
            with write_lock:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                handle.flush()
                written += 1
                print(f"Extracted {written}/{len(todo)} new graphs", flush=True)

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(extract_one, source_row, text): source_row for source_row, text in todo}
            for future in as_completed(futures):
                try:
                    future.result()
                except FatalExtractionError as error:
                    if not aborted.is_set():
                        aborted.set()
                        print(f"ABORTED: {error}", flush=True)
                except Exception as error:  # One unextractable row must not discard the whole run.
                    failures.append(futures[future])
                    print(f"FAILED source row {futures[future]}: {error}", flush=True)

    print(f"Saved {written} new graphs to {args.output}")
    if aborted.is_set():
        print("Fix the account problem above, then re-run the same command; the rows already saved are skipped.")
        sys.exit(1)
    if failures:
        print(f"{len(failures)} rows failed and were not written: {sorted(failures)}")
        print("Re-run the same command to retry only these rows; completed rows are skipped.")
        sys.exit(1)


if __name__ == "__main__":
    main()
