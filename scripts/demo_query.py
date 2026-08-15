from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from fastapi.encoders import jsonable_encoder

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agents.graph import agent  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one VMedTriage demo query from terminal input.")
    parser.add_argument(
        "-m",
        "--message",
        help="Patient message. If omitted, the script asks for input interactively.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full ChatResponse-like payload as JSON only.",
    )
    return parser


async def _run_query(message: str) -> dict:
    result = await agent.ainvoke({"query": message})
    triage_case = result["triage_case"]

    return {
        "case_id": triage_case.case_id,
        "response": result.get("response", ""),
        "status": triage_case.status,
        "analysis": result.get("analysis", ""),
        "structured_data": triage_case.structured_data,
        "validation": triage_case.validation,
        "red_flags": triage_case.red_flags,
        "triage_proposal": triage_case.triage_proposal,
        "summary": triage_case.summary,
        "requires_human_approval": True,
    }


def _print_human_readable(payload: dict) -> None:
    proposal = payload["triage_proposal"]
    red_flags = payload["red_flags"]
    validation = payload["validation"]

    print("\n=== Demo result ===")
    print(f"Case ID: {payload['case_id']}")
    print(f"Status: {payload['status']}")
    print(f"Priority: {proposal.priority if proposal else '-'}")
    print(f"Requires human approval: {payload['requires_human_approval']}")
    print(f"Patient response: {payload['response']}")

    if red_flags:
        print("Red flags:")
        for finding in red_flags:
            print(f"- {finding.code}: {finding.label}")
    else:
        print("Red flags: none")

    if validation and validation.follow_up_questions:
        print("Follow-up questions:")
        for question in validation.follow_up_questions:
            print(f"- {question}")

    print("\nStructured output:")
    print(json.dumps(jsonable_encoder(payload), ensure_ascii=False, indent=2))


def main() -> None:
    args = _build_parser().parse_args()
    message = args.message or input("Nhap query benh nhan: ").strip()
    if not message:
        raise SystemExit("Query khong duoc de trong.")

    payload = asyncio.run(_run_query(message))
    if args.json:
        print(json.dumps(jsonable_encoder(payload), ensure_ascii=False, indent=2))
    else:
        _print_human_readable(payload)


if __name__ == "__main__":
    main()
