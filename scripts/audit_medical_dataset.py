"""Read-only audit for the existing medical source collections.

By default this script prints a compact quality report.  Pass
``--write-manifest`` to deliberately create ``data/triage_v1/source_manifest.jsonl``.
It never changes files under the three source collections or the CSV source.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CORPUS_DIR = DATA_DIR / "Corpus"
REDONE_DIR = DATA_DIR / "Corpus_Redone"
QUESTION_DIR = DATA_DIR / "Question_for_dataset"
CSV_PATH = DATA_DIR / "ViMedical_Disease.csv"
MANIFEST_PATH = DATA_DIR / "triage_v1" / "source_manifest.jsonl"


def normalize_name(value: str) -> str:
    """Create a conservative filename key without changing source data."""
    decomposed = unicodedata.normalize("NFD", value.casefold())
    without_marks = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    ).replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", "", without_marks)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def utf8_status(path: Path) -> str:
    try:
        path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return "invalid_utf8"
    return "utf8"


def source_url(html_path: Path) -> str | None:
    for line in html_path.read_text(encoding="utf-8").splitlines():
        candidate = line.strip()
        if candidate.startswith(("https://", "http://")):
            return candidate
    return None


def duplicate_count(paths: list[Path]) -> int:
    counts = Counter(sha256(path) for path in paths)
    return sum(count - 1 for count in counts.values() if count > 1)


def build_manifest() -> tuple[list[dict[str, Any]], dict[str, int]]:
    corpus_files = sorted(CORPUS_DIR.glob("*.html"))
    redone_by_stem = {path.stem: path for path in REDONE_DIR.glob("*.txt")}
    questions_by_key: dict[str, list[Path]] = {}
    for path in QUESTION_DIR.glob("*.txt"):
        questions_by_key.setdefault(normalize_name(path.stem), []).append(path)

    entries: list[dict[str, Any]] = []
    question_matches = 0
    for html_path in corpus_files:
        redone_path = redone_by_stem.get(html_path.stem)
        candidates = questions_by_key.get(normalize_name(html_path.stem), [])
        question_path = candidates[0] if len(candidates) == 1 else None
        if question_path:
            question_matches += 1

        path_status = "verified_paths" if redone_path else "missing_redone_text"
        if len(candidates) > 1:
            path_status = "ambiguous_question_mapping"
        elif not question_path:
            path_status = f"{path_status}; question_unmatched"

        entries.append(
            {
                "source_id": f"corpus:{html_path.stem}",
                "source_type": "medical_reference",
                "corpus_html_path": html_path.relative_to(ROOT).as_posix(),
                "corpus_url": source_url(html_path),
                "corpus_sha256": sha256(html_path),
                "corpus_encoding": utf8_status(html_path),
                "redone_text_path": (
                    redone_path.relative_to(ROOT).as_posix() if redone_path else None
                ),
                "redone_sha256": sha256(redone_path) if redone_path else None,
                "redone_encoding": utf8_status(redone_path) if redone_path else None,
                "question_seed_path": (
                    question_path.relative_to(ROOT).as_posix() if question_path else None
                ),
                "question_mapping_status": (
                    "matched" if question_path else "unmatched_or_ambiguous"
                ),
                "usage_constraint": (
                    "Reference and symptom-phrasing seed only; never a diagnosis or "
                    "triage ground-truth label."
                ),
                "path_status": path_status,
            }
        )

    stats = {
        "corpus_files": len(corpus_files),
        "redone_files": len(list(REDONE_DIR.glob("*.txt"))),
        "question_files": len(list(QUESTION_DIR.glob("*.txt"))),
        "question_matches": question_matches,
        "question_unmatched_or_ambiguous": len(corpus_files) - question_matches,
    }
    return entries, stats


def csv_stats() -> dict[str, int]:
    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    pairs = {(row["Disease"], row["Question"].strip()) for row in rows}
    question_labels: dict[str, set[str]] = {}
    for row in rows:
        question_labels.setdefault(row["Question"].strip(), set()).add(row["Disease"])
    return {
        "csv_rows": len(rows),
        "csv_diseases": len({row["Disease"] for row in rows}),
        "csv_empty_questions": sum(not row["Question"].strip() for row in rows),
        "csv_duplicate_pairs": len(rows) - len(pairs),
        "csv_cross_label_question_collisions": sum(
            len(labels) > 1 for labels in question_labels.values()
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-manifest",
        action="store_true",
        help="Write the derived manifest; source datasets remain read-only.",
    )
    args = parser.parse_args()

    entries, stats = build_manifest()
    collections = {
        "Corpus": sorted(CORPUS_DIR.glob("*.html")),
        "Corpus_Redone": sorted(REDONE_DIR.glob("*.txt")),
        "Question_for_dataset": sorted(QUESTION_DIR.glob("*.txt")),
    }
    report: dict[str, Any] = {
        "collections": {
            name: {
                "files": len(paths),
                "empty": sum(not path.read_text(encoding="utf-8").strip() for path in paths),
                "invalid_utf8": sum(utf8_status(path) != "utf8" for path in paths),
                "duplicate_files": duplicate_count(paths),
            }
            for name, paths in collections.items()
        },
        "manifest": stats,
        "csv": csv_stats(),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.write_manifest:
        # Import lazily to avoid a module cycle during normal dataset builds.
        # The enriched manifest preserves source evidence, headings and seed
        # linkage required by the triage-v1 dataset; source collections remain
        # read-only in either path.
        from build_triage_v1_dataset import build_enriched_manifest

        entries = build_enriched_manifest()
        MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        with MANIFEST_PATH.open("w", encoding="utf-8", newline="\n") as handle:
            for entry in entries:
                handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
        print(f"Wrote {len(entries)} entries to {MANIFEST_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
