"""Validate triage-v1 draft data without changing it."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
TRIAGE_DIR = ROOT / "data" / "triage_v1"
GEMINI_CACHE_PATH = TRIAGE_DIR / "gemini_turn_cache.jsonl"
LEVELS = {
    "emergency_now",
    "same_day",
    "soon_24_72h",
    "home_monitoring",
    "insufficient_information_or_handoff",
}
SPEAKER_ROLES = {"self", "proxy"}
EXPECTED_TRIAGE_DISTRIBUTION = {
    "emergency_now": 45,
    "same_day": 25,
    "soon_24_72h": 20,
    "home_monitoring": 15,
    "insufficient_information_or_handoff": 15,
}
REVIEW_STATUSES = {
    "pending",
    "pending_demo_only",
    "approved",
    "rejected",
    "needs_revision",
}
TURN_GENERATION_PROVIDERS = {"rule_based", "gemini", "rule_based_fallback"}
GEMINI_CACHE_STATUSES = {"hit", "refreshed"}
GEMINI_DISALLOWED_PHRASES = (
    "chẩn đoán",
    "bệnh gì",
    "có thể bị",
    "kê đơn",
    "uống thuốc",
    "dùng thuốc",
    "liều thuốc",
    "điều trị",
)


def load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def require(value: Any, label: str, errors: list[str]) -> None:
    if value in (None, "", [], {}):
        errors.append(f"missing {label}")


def validate_red_flags(errors: list[str]) -> int:
    data = load_yaml(TRIAGE_DIR / "red_flags_draft.yaml")
    flags = data.get("red_flags", []) if isinstance(data, dict) else []
    if not flags:
        errors.append("red_flags_draft.yaml has no red_flags")
    seen: set[str] = set()
    for item in flags:
        flag_id = item.get("id")
        require(flag_id, "red flag id", errors)
        if flag_id in seen:
            errors.append(f"duplicate red flag id: {flag_id}")
        seen.add(flag_id)
        for field in ("symptom_group", "screening_questions", "trigger_summary", "minimum_triage", "sources", "corpus_evidence", "review_status", "reviewer"):
            require(item.get(field), f"{flag_id}.{field}", errors)
        if item.get("minimum_triage") not in LEVELS:
            errors.append(f"{flag_id}: invalid minimum_triage")
        if item.get("review_status") not in REVIEW_STATUSES:
            errors.append(f"{flag_id}: invalid review_status")
        if item.get("review_status") == "approved" and item.get("reviewer") == "unassigned":
            errors.append(f"{flag_id}: approved item needs a named reviewer")
        for source in item.get("sources", []):
            if not str(source).startswith("https://"):
                errors.append(f"{flag_id}: source is not an HTTPS URL")
        evidence = item.get("corpus_evidence", {})
        for field in ("source_id", "source_url", "source_sha256", "excerpt"):
            require(evidence.get(field), f"{flag_id}.corpus_evidence.{field}", errors)
    return len(flags)


def validate_flows(errors: list[str]) -> int:
    data = load_yaml(TRIAGE_DIR / "question_flows.yaml")
    flows = data.get("flows", []) if isinstance(data, dict) else []
    if not flows:
        errors.append("question_flows.yaml has no flows")
    for flow in flows:
        for field in ("id", "entry_prompt", "red_flag_questions", "information_questions", "handoff_conditions"):
            require(flow.get(field), f"flow.{field}", errors)
    return len(flows)


def load_gemini_cache(errors: list[str]) -> dict[tuple[str, str], dict[str, Any]]:
    if not GEMINI_CACHE_PATH.exists():
        return {}
    cache: dict[tuple[str, str], dict[str, Any]] = {}
    with GEMINI_CACHE_PATH.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                key = (entry["case_id"], entry["input_hash"])
                if entry.get("provider") != "gemini" or not isinstance(entry.get("response"), dict):
                    raise ValueError("missing provider or response")
                cache[key] = entry
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"Gemini cache line {line_number}: invalid entry ({exc})")
    return cache


def validate_cases(errors: list[str]) -> int:
    path = TRIAGE_DIR / "golden_cases_v1.jsonl"
    if not path.exists():
        errors.append("golden_cases_v1.jsonl is missing; run build_triage_v1_dataset.py")
        return 0
    cases: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if line.strip():
                try:
                    cases.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    errors.append(f"golden case line {line_number}: invalid JSON ({exc.msg})")
    seen: set[str] = set()
    prohibited = {"diagnosis", "disease_label", "predicted_disease"}
    self_agent_wording = ("người bệnh", "ở cùng người bệnh")
    gemini_cache = load_gemini_cache(errors)
    for case in cases:
        case_id = case.get("case_id")
        require(case_id, "case_id", errors)
        if case_id in seen:
            errors.append(f"duplicate case_id: {case_id}")
        seen.add(case_id)
        for field in ("artifact_status", "source_id", "source_url", "source_sha256", "source_evidence", "conversation", "required_questions", "speaker_role", "turn_generation", "expected_triage", "expected_handoff", "rationale", "review_status", "reviewer"):
            require(case.get(field), f"{case_id}.{field}", errors)
        if case.get("speaker_role") not in SPEAKER_ROLES:
            errors.append(f"{case_id}: invalid speaker_role")
        if case.get("expected_triage") not in LEVELS:
            errors.append(f"{case_id}: invalid expected_triage")
        if case.get("review_status") not in REVIEW_STATUSES:
            errors.append(f"{case_id}: invalid review_status")
        if case.get("artifact_status") != "pending_demo_only":
            errors.append(f"{case_id}: artifact_status must be pending_demo_only")
        if prohibited.intersection(case):
            errors.append(f"{case_id}: contains prohibited diagnostic output field")
        if case.get("expected_handoff") is not True:
            errors.append(f"{case_id}: expected_handoff must be true in v1")
        evidence = case.get("source_evidence", {})
        for field in ("locator", "excerpt"):
            require(evidence.get(field), f"{case_id}.source_evidence.{field}", errors)
        if case.get("speaker_role") == "self":
            for turn in case.get("conversation", []):
                if turn.get("role") != "agent_expected_question":
                    continue
                message = str(turn.get("message", "")).casefold()
                if any(wording in message for wording in self_agent_wording):
                    errors.append(f"{case_id}: self speaker has caregiver-oriented agent wording")
        generation = case.get("turn_generation", {})
        if not isinstance(generation, dict):
            errors.append(f"{case_id}: turn_generation must be an object")
            continue
        provider = generation.get("provider")
        if provider not in TURN_GENERATION_PROVIDERS:
            errors.append(f"{case_id}: invalid turn_generation.provider")
        elif provider == "rule_based":
            expected = {
                "provider": "rule_based",
                "model": None,
                "prompt_version": "rule_based_v1",
                "input_hash": None,
                "cache_status": "not_applicable",
                "generated_roles": [],
                "follow_up_choice_index": generation.get("follow_up_choice_index"),
            }
            if generation != expected:
                errors.append(f"{case_id}: invalid rule_based turn_generation metadata")
        elif provider == "rule_based_fallback":
            for field in ("model", "prompt_version", "cache_status", "generated_roles", "follow_up_choice_index", "failure_reason"):
                require(generation.get(field), f"{case_id}.turn_generation.{field}", errors)
            if generation.get("cache_status") != "fallback":
                errors.append(f"{case_id}: invalid rule_based_fallback cache_status")
            if generation.get("generated_roles") != []:
                errors.append(f"{case_id}: rule_based_fallback must not claim generated roles")
        else:
            for field in ("model", "prompt_version", "input_hash", "cache_status", "generated_roles", "follow_up_choice_index"):
                require(generation.get(field), f"{case_id}.turn_generation.{field}", errors)
            if generation.get("cache_status") not in GEMINI_CACHE_STATUSES:
                errors.append(f"{case_id}: invalid Gemini cache_status")
            if generation.get("generated_roles") != ["agent_expected_question", "follow_up_choice_index"]:
                errors.append(f"{case_id}: Gemini must generate agent_expected_question and follow_up_choice_index")
            cache_entry = gemini_cache.get((case_id, generation.get("input_hash")))
            if cache_entry is None:
                errors.append(f"{case_id}: no matching Gemini cache/audit entry")
            else:
                if cache_entry.get("model") != generation.get("model"):
                    errors.append(f"{case_id}: Gemini cache model does not match case metadata")
                if cache_entry.get("prompt_version") != generation.get("prompt_version"):
                    errors.append(f"{case_id}: Gemini cache prompt version does not match case metadata")
                conversation = case.get("conversation", [])
                agent_message = next(
                    (turn.get("message") for turn in conversation if turn.get("role") == "agent_expected_question"),
                    None,
                )
                response = cache_entry.get("response", {})
                if agent_message != response.get("agent_question"):
                    errors.append(f"{case_id}: agent question does not match Gemini cache response")
                if generation.get("follow_up_choice_index") != response.get("follow_up_choice_index"):
                    errors.append(f"{case_id}: follow-up choice does not match Gemini cache response")
                if cache_entry.get("prompt_version") == "gemini_agent_question_and_follow_up_choice_v1" and not isinstance(
                    cache_entry.get("source_fingerprint"), str
                ):
                    errors.append(f"{case_id}: Gemini agent-only cache has no source_fingerprint")
            generated_text = " ".join(
                str(turn.get("message", ""))
                for turn in case.get("conversation", [])
                if turn.get("role") == "agent_expected_question"
            ).casefold()
            if any(phrase in generated_text for phrase in GEMINI_DISALLOWED_PHRASES):
                errors.append(f"{case_id}: Gemini turns contain prohibited diagnosis or treatment wording")

    if len(cases) != 120:
        errors.append(f"golden cases has {len(cases)} entries; expected 120")
    distribution = dict(Counter(case.get("expected_triage") for case in cases))
    if distribution != EXPECTED_TRIAGE_DISTRIBUTION:
        errors.append(
            "golden cases triage distribution is "
            f"{distribution}; expected {EXPECTED_TRIAGE_DISTRIBUTION}"
        )
    return len(cases)


def validate_manifest(errors: list[str]) -> int:
    path = TRIAGE_DIR / "source_manifest.jsonl"
    if not path.exists():
        errors.append("source_manifest.jsonl is missing; run audit_medical_dataset.py --write-manifest")
        return 0
    entries = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if len(entries) != 603:
        errors.append(f"manifest has {len(entries)} entries; expected 603")
    for entry in entries:
        for field in ("corpus_url", "corpus_sha256", "title", "headings", "evidence_excerpt", "quality_status"):
            require(entry.get(field), f"{entry.get('source_id')}.{field}", errors)
    return len(entries)


def validate_quality_report(errors: list[str]) -> None:
    path = TRIAGE_DIR / "quality_report.json"
    if not path.exists():
        errors.append("quality_report.json is missing; run build_triage_v1_dataset.py")
        return
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("golden_case_count") != 120:
        errors.append("quality report must contain 120 golden cases")
    if report.get("unique_case_sources") != 120:
        errors.append("quality report must contain 120 unique case sources")
    if report.get("quality_gate") != "pass":
        errors.append("quality report did not pass its quality gate")
    if report.get("triage_distribution") != EXPECTED_TRIAGE_DISTRIBUTION:
        errors.append("quality report has an unexpected triage distribution")
    if report.get("cases_missing_evidence"):
        errors.append("quality report has golden cases without evidence")
    if report.get("missing_red_flag_coverage"):
        errors.append("quality report has red flags without golden-case coverage")
    providers = report.get("turn_generation_provider_distribution", {})
    if sum(providers.values()) != 120 or set(providers) - TURN_GENERATION_PROVIDERS:
        errors.append("quality report has an invalid turn-generation provider distribution")


def validate_review_log(errors: list[str]) -> None:
    path = TRIAGE_DIR / "review_log.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        headers = set(csv.DictReader(handle).fieldnames or [])
    required = {"review_id", "artifact_type", "artifact_id", "decision", "reviewer", "reviewed_at", "notes"}
    missing = required - headers
    if missing:
        errors.append(f"review_log.csv missing headers: {', '.join(sorted(missing))}")


def main() -> int:
    errors: list[str] = []
    counts = {
        "red_flags": validate_red_flags(errors),
        "flows": validate_flows(errors),
        "golden_cases": validate_cases(errors),
        "manifest_entries": validate_manifest(errors),
    }
    validate_review_log(errors)
    validate_quality_report(errors)
    if errors:
        print("VALIDATION FAILED")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print("VALIDATION PASSED")
    print(json.dumps(counts, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
