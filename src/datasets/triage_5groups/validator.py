"""Validation for the complete, unsplit five-group dataset release."""

from __future__ import annotations

import ast
import csv
import json
from collections import Counter
from pathlib import Path

from .builder import CSV_COLUMNS, DEFAULT_OUTPUT_DIR
from .schemas import ConversationRecord


def validate_dataset(output_dir: Path = DEFAULT_OUTPUT_DIR, write_report: bool = True) -> dict:
    errors: list[str] = []
    csv_path = output_dir / "triage_5groups.csv"
    json_path = output_dir / "triage_5groups_conversations.json"
    if not csv_path.exists() or not json_path.exists():
        raise FileNotFoundError("build the dataset before validation")
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        if reader.fieldnames != CSV_COLUMNS:
            errors.append("CSV columns do not exactly match the SymCat schema")
    if len(rows) != 375:
        errors.append(f"expected 375 CSV rows, found {len(rows)}")
    for index, row in enumerate(rows):
        try:
            probabilities = ast.literal_eval(row["symptom_probabilities"])
            if int(row["num_symptoms"]) != len(probabilities):
                errors.append(f"CSV row {index}: symptom count mismatch")
            mapping = {"self_monitor": 0, "consult_gp": 1, "urgent": 2}
            if mapping.get(row["label"]) != int(row["label_numeric"]):
                errors.append(f"CSV row {index}: label mapping mismatch")
        except (ValueError, SyntaxError):
            errors.append(f"CSV row {index}: invalid list or numeric field")
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    records = [ConversationRecord.model_validate(item) for item in payload.get("records", [])]
    if len(records) != 500:
        errors.append(f"expected 500 conversations, found {len(records)}")
    by_group_action = Counter((record.symptom_group, record.action) for record in records)
    if len(by_group_action) != 20 or any(count != 25 for count in by_group_action.values()):
        errors.append("each group/action combination must contain exactly 25 records")
    blocked = ("tôi có thể đang bị bệnh gì", "chẩn đoán", "disease_label", "condition_slug")
    csv_links = set()
    for record in records:
        messages = record.messages
        if messages[0].role != "system" or messages[1].role != "user" or messages[2].role != "assistant":
            errors.append(f"{record.conversation_id}: invalid initial role sequence")
        if any(token in message.content.casefold() for message in messages if message.role == "user" for token in blocked):
            errors.append(f"{record.conversation_id}: contains diagnostic leakage")
        if record.requires_followup:
            if record.triage_label is not None or len(messages) != 3 or record.csv_row_index is not None:
                errors.append(f"{record.conversation_id}: invalid ask_followup record")
        else:
            if record.triage_label is None or len(messages) != 5 or record.csv_row_index is None:
                errors.append(f"{record.conversation_id}: invalid labelled conversation")
            else:
                csv_links.add(record.csv_row_index)
        if record.action == "urgent_handoff" and not record.expected_red_flags:
            errors.append(f"{record.conversation_id}: urgent record has no red flag")
    if csv_links != set(range(len(rows))):
        errors.append("CSV rows are not linked one-to-one to labelled conversations")
    report = {
        "schema_version": "1.0",
        "artifact_status": "demo_only",
        "conversation_count": len(records),
        "csv_row_count": len(rows),
        "group_action_distribution": {f"{group}:{action}": count for (group, action), count in sorted(by_group_action.items())},
        "errors": errors,
        "quality_gate": "pass" if not errors else "fail",
    }
    if write_report:
        (output_dir / "quality_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if errors:
        raise ValueError("dataset validation failed: " + "; ".join(errors))
    return report
