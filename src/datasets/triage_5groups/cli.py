"""Command line entry point for building the five-group agent dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .builder import DEFAULT_OUTPUT_DIR, build_dataset
from .validator import validate_dataset


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "validate"))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--refresh-gemini", action="store_true", help="Generate constrained agent questions through Gemini")
    args = parser.parse_args(argv)
    if args.command == "build":
        build_dataset(args.output_dir, use_gemini=args.refresh_gemini)
    report = validate_dataset(args.output_dir)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
