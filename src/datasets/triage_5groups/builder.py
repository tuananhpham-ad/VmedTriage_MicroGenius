"""Build CSV and conversation JSON artifacts for five Vietnamese symptom groups."""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from .catalog import load_catalogs
from .generation import QuestionGenerator
from .schemas import Action, ConversationRecord, CsvRow, SymptomGroup

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"
DEFAULT_OUTPUT_DIR = DATA_DIR / "agent_triage_5groups_v1"
CSV_COLUMNS = [
    "condition_name", "condition_slug", "symptom_names", "symptom_slugs", "symptom_probabilities", "text",
    "num_symptoms", "max_symptom_probability", "mean_symptom_probability", "urgent_score", "gp_score",
    "self_score", "label", "override_applied", "text_len_words", "label_numeric",
]
SYSTEM_PROMPT = "Bạn là agent triage. Không chẩn đoán hoặc kê đơn. Hỏi thêm khi thiếu thông tin."
LABELS: dict[Action, tuple[str | None, int | None]] = {
    "self_monitor": ("self_monitor", 0),
    "consult_gp": ("consult_gp", 1),
    "urgent_handoff": ("urgent", 2),
    "ask_followup": (None, None),
}


def _safe_text(value: str) -> str:
    value = re.sub(r"Tôi có thể (?:đang )?bị bệnh gì\?", "", value, flags=re.IGNORECASE)
    return " ".join(value.split()).strip(" ,.;:")


def _symptom_slug(value: str) -> str:
    translated = value.lower().translate(str.maketrans({"đ": "d"}))
    translated = re.sub(r"[^a-z0-9]+", "-", translated)
    return translated.strip("-") or "symptom"


def _initial_message(group: SymptomGroup, ordinal: int) -> str:
    template = group.user_templates[ordinal % len(group.user_templates)]
    duration = group.durations[(ordinal // len(group.user_templates)) % len(group.durations)]
    return _safe_text(template.format(duration=duration))


def _pregnancy_status(group: SymptomGroup, ordinal: int) -> str:
    return "unknown" if ordinal % 5 == 0 else ("yes" if ordinal % 7 == 0 else "no")


def _assistant_question(group: SymptomGroup, flags: Iterable, status: str) -> str:
    base = next(iter(flags), None)
    question = base.screening_question if base else group.pregnancy_question
    if status == "unknown":
        return f"{question.rstrip('?')}. Ngoài ra, bạn có đang mang thai không?"
    return question


def _csv_row(group: SymptomGroup, record: ConversationRecord, follow_up: str) -> CsvRow:
    label, label_numeric = LABELS[record.action]
    assert label is not None and label_numeric is not None
    symptoms = list(dict.fromkeys(group.base_symptoms + record.messages[-2].content.split(", ")[:2]))
    symptoms = [item.strip(" .") for item in symptoms if item.strip(" .")]
    relevance = [100] + [90 if record.action == "urgent_handoff" else 70] * (len(symptoms) - 1)
    scores = {"urgent": 0, "consult_gp": 0, "self_monitor": 0}
    scores[label] = 1
    text = f"Người dùng báo: {_safe_text(record.messages[1].content)} {_safe_text(follow_up)}".strip()
    return CsvRow(
        condition_name=group.condition_name,
        condition_slug=group.condition_slug,
        symptom_names=repr(symptoms),
        symptom_slugs=repr([_symptom_slug(item) for item in symptoms]),
        symptom_probabilities=repr(relevance),
        text=text,
        num_symptoms=len(symptoms),
        max_symptom_probability=max(relevance),
        mean_symptom_probability=sum(relevance) / len(relevance),
        urgent_score=scores["urgent"],
        gp_score=scores["consult_gp"],
        self_score=scores["self_monitor"],
        label=label,
        text_len_words=len(text.split()),
        label_numeric=label_numeric,
    )


def _source_catalog(groups: list[SymptomGroup], flags: dict) -> list[dict]:
    result = []
    for group in groups:
        result.append({
            "symptom_group": group.id,
            "source_id": group.source_id,
            "red_flags": [flags[flag_id].model_dump(mode="json") for flag_id in group.red_flag_ids],
        })
    return result


def build_dataset(output_dir: Path = DEFAULT_OUTPUT_DIR, use_gemini: bool = False) -> dict:
    """Create the complete, unsplit demo-only dataset and return its report."""
    output_dir.mkdir(parents=True, exist_ok=True)
    catalog_dir = output_dir if (output_dir / "red_flag_catalog_v1.yaml").exists() else DEFAULT_OUTPUT_DIR
    red_flag_path = catalog_dir / "red_flag_catalog_v1.yaml"
    scenario_path = catalog_dir / "scenario_catalog_v1.yaml"
    version, flags, groups = load_catalogs(red_flag_path, scenario_path)
    if catalog_dir != output_dir:
        (output_dir / red_flag_path.name).write_text(red_flag_path.read_text(encoding="utf-8"), encoding="utf-8")
        (output_dir / scenario_path.name).write_text(scenario_path.read_text(encoding="utf-8"), encoding="utf-8")
    generator = QuestionGenerator(output_dir / "gemini_turn_cache.jsonl", use_gemini=use_gemini)
    records: list[ConversationRecord] = []
    csv_rows: list[CsvRow] = []
    actions: tuple[Action, ...] = ("self_monitor", "consult_gp", "urgent_handoff", "ask_followup")

    for group in groups:
        group_flags = [flags[flag_id] for flag_id in group.red_flag_ids]
        evidence = [flag.evidence for flag in group_flags]
        for action in actions:
            scenario = group.scenarios[action]
            for ordinal in range(25):
                initial = _initial_message(group, ordinal)
                status = _pregnancy_status(group, ordinal)
                fallback = _assistant_question(group, group_flags, status)
                key = f"{group.id}:{action}:{ordinal + 1:03d}"
                generated = generator.generate(key, fallback, scenario.follow_up_candidates, ordinal)
                follow_up = scenario.follow_up_candidates[generated.follow_up_choice_index]
                label, _ = LABELS[action]
                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": initial},
                    {"role": "assistant", "content": generated.question},
                ]
                if action != "ask_followup":
                    assert scenario.final_reply is not None
                    messages.extend([
                        {"role": "user", "content": follow_up},
                        {"role": "assistant", "content": scenario.final_reply},
                    ])
                record = ConversationRecord(
                    conversation_id=key,
                    symptom_group=group.id,
                    action=action,
                    triage_label=label,
                    requires_followup=action == "ask_followup",
                    messages=messages,
                    expected_red_flags=group.red_flag_ids if action == "urgent_handoff" else [],
                    pregnancy_status=status,
                    red_flag_catalog_version=version,
                    evidence=evidence,
                )
                if action != "ask_followup":
                    record.csv_row_index = len(csv_rows)
                    csv_rows.append(_csv_row(group, record, follow_up))
                records.append(record)
    generator.save()

    csv_path = output_dir / "triage_5groups.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(row.model_dump() for row in csv_rows)
    conversation_path = output_dir / "triage_5groups_conversations.json"
    conversation_path.write_text(json.dumps({"schema_version": "1.0", "records": [r.model_dump() for r in records]}, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "source_catalog.json").write_text(json.dumps(_source_catalog(groups, flags), ensure_ascii=False, indent=2), encoding="utf-8")
    with (output_dir / "review_queue.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["conversation_id", "reason", "status"])
        writer.writeheader()
    (output_dir / "data_card.md").write_text(
        "# Agent triage 5 groups v1\n\n"
        "Demo-only candidate data for Vietnamese agent training. `symptom_probabilities` are scenario relevance "
        "scores, not clinical probabilities. No record is clinically approved.\n",
        encoding="utf-8",
    )
    return {"records": len(records), "csv_rows": len(csv_rows), "actions": Counter(record.action for record in records)}
