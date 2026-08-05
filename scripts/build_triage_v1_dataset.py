"""Build a traceable, demo-only triage test set from the local medical corpus.

The script reads the source collections and writes only derived artifacts beneath
``data/triage_v1``.  It never edits a source HTML/TXT/CSV file.  Clinical labels
are explicitly draft labels for an internal demo, not diagnostic or production
triage decisions.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import sys
import time
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml
from audit_medical_dataset import (
    CORPUS_DIR,
    CSV_PATH,
    QUESTION_DIR,
    REDONE_DIR,
    ROOT,
    normalize_name,
    sha256,
    source_url,
)
from dotenv import load_dotenv
from gemini_turn_generator import (
    DEFAULT_MODEL,
    DEFAULT_REQUESTS_PER_MINUTE,
    GeminiTurnGenerator,
    GenerationRequest,
    TurnGenerationError,
)

TRIAGE_DIR = ROOT / "data" / "triage_v1"
MANIFEST_PATH = TRIAGE_DIR / "source_manifest.jsonl"
GEMINI_CACHE_PATH = TRIAGE_DIR / "gemini_turn_cache.jsonl"
LEVEL_ALLOCATION = {
    "emergency_now": 45,
    "same_day": 25,
    "soon_24_72h": 20,
    "home_monitoring": 15,
    "insufficient_information_or_handoff": 15,
}
SPEAKER_ROLES = {"self", "proxy"}
EXTERNAL_SOURCES = {
    "airway": "https://www.who.int/publications/i/item/basic-emergency-care-approach-to-the-acutely-ill-and-injured",
    "chest": "https://www.nhs.uk/conditions/chest-pain/",
    "neuro": "https://www.nhs.uk/conditions/stroke/symptoms/",
    "allergy": "https://www.nhs.uk/conditions/anaphylaxis/",
    "bleeding": "https://www.nhs.uk/tests-and-treatments/first-aid/",
    "infection": "https://www.nhs.uk/conditions/sepsis/",
    "mental": "https://www.londonambulance.nhs.uk/calling-us/calling-999/your-local-999-and-111-services-english-html-leaflet/",
}


def clean_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def text_lines(path: Path) -> list[str]:
    return [
        re.sub(r"\s+", " ", line).strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if re.sub(r"\s+", " ", line).strip()
    ]


def headings_and_title(html_path: Path) -> tuple[str, list[str]]:
    raw = html_path.read_text(encoding="utf-8")
    title_match = re.search(r"<h1[^>]*>(.*?)</h1>", raw, flags=re.I | re.S)
    title = clean_html(title_match.group(1)) if title_match else html_path.stem
    headings = [
        clean_html(match.group(2))
        for match in re.finditer(r"<(h[2-4])[^>]*>(.*?)</\1>", raw, flags=re.I | re.S)
        if clean_html(match.group(2))
    ]
    return title, (list(dict.fromkeys(headings))[:12] or [title])


def excerpt_from_redone(path: Path) -> str:
    lines = text_lines(path)
    candidates = [line for line in lines[1:] if len(line) >= 80]
    return (candidates[0] if candidates else " ".join(lines[:2]))[:700]


def question_file_index() -> dict[str, Path]:
    index: dict[str, Path] = {}
    for path in QUESTION_DIR.glob("*.txt"):
        key = normalize_name(path.stem)
        if key not in index:
            index[key] = path
    return index


def csv_question_index() -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            values.setdefault(normalize_name(row["Disease"]), []).append(
                re.sub(r"\s+", " ", row["Question"]).strip()
            )
    return values


def build_enriched_manifest() -> list[dict[str, Any]]:
    q_index = question_file_index()
    csv_index = csv_question_index()
    entries: list[dict[str, Any]] = []
    for html_path in sorted(CORPUS_DIR.glob("*.html")):
        stem = html_path.stem
        key = normalize_name(stem)
        redone_path = REDONE_DIR / f"{stem}.txt"
        question_path = q_index.get(key)
        title, headings = headings_and_title(html_path)
        question_lines = text_lines(question_path) if question_path else []
        csv_questions = csv_index.get(key, [])
        entries.append(
            {
                "source_id": f"corpus:{stem}",
                "source_type": "medical_reference",
                "corpus_html_path": html_path.relative_to(ROOT).as_posix(),
                "corpus_url": source_url(html_path),
                "corpus_sha256": sha256(html_path),
                "title": title,
                "headings": headings,
                "redone_text_path": redone_path.relative_to(ROOT).as_posix() if redone_path.exists() else None,
                "redone_sha256": sha256(redone_path) if redone_path.exists() else None,
                "evidence_excerpt": excerpt_from_redone(redone_path) if redone_path.exists() else None,
                "evidence_locator": "Corpus_Redone:first_substantive_paragraph",
                "question_seed_path": question_path.relative_to(ROOT).as_posix() if question_path else None,
                "question_seed_count": len(question_lines),
                "question_seed_sample": question_lines[0] if question_lines else None,
                "csv_question_count": len(csv_questions),
                "csv_question_seed_sample": csv_questions[0] if csv_questions else None,
                "usage_constraint": "Internal evidence/phrasing seed only; never a diagnostic or production triage label.",
                "quality_status": "eligible" if question_lines and redone_path.exists() and source_url(html_path) else "not_eligible",
            }
        )
    return entries


def normalized_record_text(record: dict[str, Any]) -> str:
    return normalize_name(" ".join([record["source_id"], record["title"], *record["headings"]]))


def contains_any(record: dict[str, Any], keywords: Iterable[str]) -> bool:
    haystack = normalized_record_text(record)
    return any(normalize_name(keyword) in haystack for keyword in keywords)


def emergency_score(record: dict[str, Any]) -> int:
    weighted = {
        7: ["dot quy", "tai bien mach mau nao", "nhoi mau", "suy ho hap", "kho tho", "thuyen tac", "tac mach", "xuat huyet", "ngo doc", "chan thuong", "dong kinh", "viem mang nao", "xoan tinh hoan"],
        5: ["dau that nguc", "sot xuat huyet", "viem ruot thua", "benh dai", "ran mu", "hon me", "ngat", "suy tim"],
        2: ["dau bung", "dau dau", "sot", "nhiem trung"],
    }
    return sum(weight for weight, keywords in weighted.items() if contains_any(record, keywords))


def same_day_score(record: dict[str, Any]) -> int:
    return sum(
        contains_any(record, group)
        for group in [
            ["viem", "nhiem trung", "sot", "dau bung", "dau tinh hoan"],
            ["tieu buot", "tieu ra mau", "dau mat", "dau tai", "dau khop"],
            ["ap xe", "sung", "phat ban"],
        ]
    )


def soon_score(record: dict[str, Any]) -> int:
    return sum(
        contains_any(record, group)
        for group in [
            ["man tinh", "thoai hoa", "roi loan", "polyp", "u nang"],
            ["gout", "viem xoang", "tuyen giap", "tieu duong", "mat ngu"],
        ]
    )


def home_score(record: dict[str, Any]) -> int:
    return sum(
        contains_any(record, group)
        for group in [
            ["mun", "nam da", "not ruoi", "hoi mieng", "ra mo hoi"],
            ["tat khuc xa", "vien thi", "can thi", "loan thi"],
        ]
    )


def select_records(
    records: list[dict[str, Any]], score_fn: Any, count: int, used: set[str]
) -> list[dict[str, Any]]:
    ranked = sorted(
        (record for record in records if record["source_id"] not in used),
        key=lambda record: (score_fn(record), record["source_id"]),
        reverse=True,
    )
    positive = [record for record in ranked if score_fn(record) > 0]
    chosen = positive[:count]
    if len(chosen) < count:
        chosen.extend(record for record in ranked if record not in chosen)  # deterministic fallback
        chosen = chosen[:count]
    used.update(record["source_id"] for record in chosen)
    return chosen


def red_flags_for(record: dict[str, Any]) -> list[str]:
    matching: list[tuple[list[str], str]] = [
        (["kho tho", "suy ho hap", "ngung tho"], "RF-AIRWAY-BREATHING-001"),
        (["dau that nguc", "nhoi mau", "mach vanh"], "RF-CHEST-PAIN-001"),
        (["dot quy", "tai bien mach mau nao", "tac mach mau nao", "xuat huyet nao"], "RF-NEURO-FAST-001"),
        (["me day", "di ung"], "RF-ALLERGY-001"),
        (["xuat huyet", "bang huyet"], "RF-BLEEDING-SHOCK-001"),
        (["sot xuat huyet", "viem mang nao", "nhiem trung"], "RF-SEVERE-INFECTION-001"),
        (["ngo doc", "chan thuong", "ran mu"], "RF-TRAUMA-POISONING-001"),
        (["tram cam", "tu sat", "tu hai"], "RF-SELF-HARM-001"),
        (["dau bung", "dau dau", "xoan tinh hoan", "viem ruot thua"], "RF-ACUTE-SEVERE-PAIN-001"),
    ]
    return [flag for keywords, flag in matching if contains_any(record, keywords)]


def seed_questions(record: dict[str, Any]) -> list[str]:
    path = ROOT / record["question_seed_path"]
    values = text_lines(path)
    return values or [record["question_seed_sample"]]


def detect_speaker_role(message: str) -> str:
    """Classify whether the source question is about its own sender or another person.

    The current source seeds are first-person questions ("tôi"), so they are
    self reports.  Keeping this explicit prevents agent prompts from assuming a
    caller is a caregiver when new source seeds are added later.
    """
    if re.search(r"\b(?:tôi|toi|mình|minh)\b", message, flags=re.I):
        return "self"
    return "proxy"


def agent_question(level: str, flags: list[str], variant: int, speaker_role: str) -> str:
    if speaker_role not in SPEAKER_ROLES:
        raise ValueError(f"Unsupported speaker role: {speaker_role}")
    if level == "insufficient_information_or_handoff":
        if speaker_role == "self":
            return "Hiện bạn có khó thở nặng, ngất, chảy máu nhiều, yếu/liệt, nói khó đột ngột hoặc thay đổi ý thức không? Bạn đang ở đâu và có ai ở cạnh bạn không?"
        return "Bạn có thể xác nhận người bệnh đang ở đâu, có người ở cạnh, và hiện có khó thở nặng, ngất, chảy máu nhiều, yếu/liệt/nói khó đột ngột hay không?"
    if flags:
        variants = [
            "Triệu chứng bắt đầu khi nào và có xuất hiện đột ngột, tăng nhanh, khó thở, ngất, lú lẫn, chảy máu hoặc yếu/tê mới không?",
            (
                "Bạn hiện có dấu hiệu nào khiến bạn không thể nói, khó tỉnh táo hoặc không thể hoạt động như bình thường không?"
                if speaker_role == "self"
                else "Bạn có đang ở cùng người bệnh không? Có dấu hiệu nào đang làm người bệnh không thể nói, tỉnh táo hoặc hoạt động như bình thường không?"
            ),
            "Ngoài triệu chứng bạn mô tả, có đau dữ dội, thở bất thường, tím tái, choáng/ngất hoặc thay đổi ý thức không?",
        ]
        return variants[variant % len(variants)]
    return "Triệu chứng bắt đầu khi nào, đang tăng hay giảm, và có khó thở nặng, ngất, chảy máu, lú lẫn hoặc đau đột ngột dữ dội không?"


def follow_up(level: str, seed: str, variant: int, speaker_role: str) -> str:
    if level == "insufficient_information_or_handoff":
        if speaker_role == "self":
            return [
                "Tôi chưa tự xác nhận được các dấu hiệu đó trên chính mình.",
                "Tôi chưa rõ triệu chứng của tôi bắt đầu từ khi nào và chưa tự kiểm tra được đầy đủ.",
                "Tôi mô tả triệu chứng của mình chưa nhất quán nên chưa chắc tình trạng hiện tại.",
            ][variant % 3]
        return [
            "Tôi không ở cạnh người bệnh nên không xác nhận được các dấu hiệu đó.",
            "Thông tin tôi nhận được không rõ thời điểm bắt đầu và không có ai kiểm tra trực tiếp.",
            "Người bệnh trả lời không nhất quán nên tôi không chắc tình trạng hiện tại.",
        ][variant % 3]
    if level in {"same_day", "soon_24_72h", "home_monitoring"}:
        return "Tôi chưa thấy các dấu hiệu nguy hiểm vừa nêu; đây là thông tin bổ sung: " + seed
    return "Thông tin bổ sung từ người gọi: " + seed


def fallback_follow_up_choice_index(initial: str, candidates: list[str]) -> int:
    """Deterministically choose the most related source candidate when Gemini is unavailable."""
    initial_tokens = token_set(initial)
    ranked = [
        (
            len(initial_tokens & token_set(candidate)),
            -index,
            index,
        )
        for index, candidate in enumerate(candidates)
    ]
    return max(ranked)[2]


def make_case(
    record: dict[str, Any],
    level: str,
    ordinal: int,
    turn_generator: GeminiTurnGenerator | None = None,
) -> dict[str, Any]:
    questions = seed_questions(record)
    first = questions[ordinal % len(questions)]
    fallback_choice_index = fallback_follow_up_choice_index(first, questions)
    second = questions[fallback_choice_index]
    speaker_role = detect_speaker_role(first)
    flags = red_flags_for(record) if level == "emergency_now" else []
    if level == "emergency_now" and not flags:
        flags = ["RF-ACUTE-SEVERE-PAIN-001"]
    required_questions = [
        "Thời điểm khởi phát và diễn tiến triệu chứng",
        "Sàng lọc dấu hiệu nguy hiểm phù hợp với nhóm triệu chứng",
        "Xác nhận khả năng chuyển điều dưỡng khi thông tin không đủ",
    ]
    agent_message = agent_question(level, flags, ordinal, speaker_role)
    follow_up_message = follow_up(level, second, ordinal, speaker_role)
    turn_generation: dict[str, Any] = {
        "provider": "rule_based",
        "model": None,
        "prompt_version": "rule_based_v1",
        "input_hash": None,
        "cache_status": "not_applicable",
        "generated_roles": [],
        "follow_up_choice_index": fallback_choice_index,
    }
    if turn_generator is not None:
        generated = turn_generator.generate(
            GenerationRequest(
                case_id=f"TC-V1-{ordinal:03d}",
                speaker_role=speaker_role,
                expected_triage=level,
                expected_red_flags=flags,
                required_questions=required_questions,
                source_evidence=record["evidence_excerpt"],
                initial_patient_message=first,
                follow_up_seed=second,
                follow_up_candidates=questions,
            )
        )
        agent_message = generated.agent_question
        second = questions[generated.follow_up_choice_index]
        follow_up_message = follow_up(level, second, ordinal, speaker_role)
        turn_generation = generated.metadata
        turn_generation["follow_up_choice_index"] = generated.follow_up_choice_index
    return {
        "case_id": f"TC-V1-{ordinal:03d}",
        "artifact_status": "pending_demo_only",
        "scenario_type": (
            "source_grounded_red_flag" if flags else "source_grounded_non_emergency"
            if level != "insufficient_information_or_handoff" else "source_grounded_insufficient_information"
        ),
        "scope": "adult_non_pregnant" if level != "insufficient_information_or_handoff" else "handoff_or_out_of_scope",
        "speaker_role": speaker_role,
        "source_id": record["source_id"],
        "source_url": record["corpus_url"],
        "source_sha256": record["corpus_sha256"],
        "source_evidence": {
            "locator": record["evidence_locator"],
            "excerpt": record["evidence_excerpt"],
        },
        "conversation": [
            {"role": "patient", "message": first},
            {"role": "agent_expected_question", "message": agent_message},
            {"role": "patient", "message": follow_up_message},
        ],
        "required_questions": required_questions,
        "turn_generation": turn_generation,
        "expected_red_flags": flags,
        "expected_triage": level,
        "expected_handoff": True,
        "rationale": "Nhãn demo nội bộ được gắn theo evidence nguồn và quy tắc sàng lọc draft; không phải chẩn đoán hoặc hướng xử trí tự động.",
        "review_status": "pending_demo_only",
        "reviewer": "unassigned",
        "reviewed_at": None,
    }


def find_record(records: list[dict[str, Any]], stem: str) -> dict[str, Any]:
    desired = f"corpus:{stem}"
    return next(record for record in records if record["source_id"] == desired)


def build_red_flags(records: list[dict[str, Any]]) -> dict[str, Any]:
    definitions = [
        ("RF-AIRWAY-BREATHING-001", "airway_breathing", "kho-tho", "Khó thở hoặc dấu hiệu đường thở/hô hấp đáng lo.", "emergency_now", ["Bạn có khó thở đến mức không nói được câu ngắn, thở rít, tím tái, hoặc không phản ứng bình thường không?"] , EXTERNAL_SOURCES["airway"]),
        ("RF-CHEST-PAIN-001", "chest_pain", "dau-that-nguc", "Đau/khó chịu ngực kèm dấu hiệu toàn thân đáng lo.", "emergency_now", ["Đau có kéo dài/tăng lên, lan, hoặc kèm khó thở, vã mồ hôi, buồn nôn, choáng/ngất không?"] , EXTERNAL_SOURCES["chest"]),
        ("RF-NEURO-FAST-001", "neurological", "dot-quy", "Dấu hiệu thần kinh đột ngột hoặc thay đổi ý thức.", "emergency_now", ["Có méo miệng, yếu/tê một bên, nói khó, lú lẫn, mất thị lực, ngất hoặc co giật khởi phát đột ngột không?"] , EXTERNAL_SOURCES["neuro"]),
        ("RF-ALLERGY-001", "allergy", "me-day", "Triệu chứng dị ứng cần sàng lọc đường thở/tuần hoàn.", "emergency_now", ["Có sưng nhanh môi/lưỡi/họng, khó thở, thở khò khè, choáng hoặc ngất không?"] , EXTERNAL_SOURCES["allergy"]),
        ("RF-BLEEDING-SHOCK-001", "bleeding_or_shock", "xuat-huyet-tieu-hoa", "Chảy máu hoặc dấu hiệu giảm tưới máu cần escalation.", "emergency_now", ["Có chảy máu nhiều/không cầm, nôn ra máu, đi ngoài ra máu/phân đen, choáng hoặc ngất không?"] , EXTERNAL_SOURCES["bleeding"]),
        ("RF-SEVERE-INFECTION-001", "infection", "sot-xuat-huyet", "Triệu chứng nhiễm trùng kèm thay đổi toàn trạng đáng lo.", "emergency_now", ["Có thở rất nhanh, lú lẫn, da/môi tái/xanh/lốm đốm, sốt/rét run rõ hoặc ban không mất màu khi ấn không?"] , EXTERNAL_SOURCES["infection"]),
        ("RF-TRAUMA-POISONING-001", "trauma_or_poisoning", "chan-thuong-so-nao", "Chấn thương hoặc phơi nhiễm chất/thuốc cần đánh giá khẩn.", "emergency_now", ["Có chấn thương mạnh, ngất, nôn, khó thở, co giật, hoặc đã uống/hít/tiếp xúc chất lạ không?"] , EXTERNAL_SOURCES["airway"]),
        ("RF-SELF-HARM-001", "mental_health_safety", "tram-cam", "Khủng hoảng tâm thần cần sàng lọc nguy cơ tự hại.", "emergency_now", ["Bạn có ý định tự làm hại bản thân, kế hoạch/phương tiện cụ thể, hoặc vừa tự hại không?"] , EXTERNAL_SOURCES["mental"]),
        ("RF-ACUTE-SEVERE-PAIN-001", "acute_severe_pain", "viem-ruot-thua-cap", "Đau mới xuất hiện đột ngột/dữ dội hoặc kèm dấu hiệu toàn thân.", "emergency_now", ["Cơn đau có đột ngột rất dữ dội, tăng nhanh, hoặc kèm ngất, lú lẫn, khó thở hay chảy máu không?"] , EXTERNAL_SOURCES["airway"]),
    ]
    flags = []
    for flag_id, group, stem, trigger, level, questions, external in definitions:
        record = find_record(records, stem)
        flags.append(
            {
                "id": flag_id,
                "symptom_group": group,
                "trigger_summary": trigger,
                "screening_questions": questions,
                "minimum_triage": level,
                "mandatory_handoff": True,
                "corpus_evidence": {
                    "source_id": record["source_id"],
                    "source_url": record["corpus_url"],
                    "source_sha256": record["corpus_sha256"],
                    "locator": record["evidence_locator"],
                    "excerpt": record["evidence_excerpt"],
                },
                "sources": [record["corpus_url"], external],
                "review_status": "pending_demo_only",
                "reviewer": "unassigned",
                "reviewed_at": None,
                "notes": "Evidence link for internal demo; external clinical reviewer must approve before any patient use.",
            }
        )
    return {
        "schema_version": "1.0",
        "artifact_status": "pending_demo_only",
        "scope": "Internal demo only; adult/non-pregnant default; no diagnosis or autonomous patient-facing action.",
        "red_flags": flags,
    }


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def token_set(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9à-ỹ]+", value.casefold()))


def duplicate_pairs(cases: list[dict[str, Any]]) -> list[list[str]]:
    pairs: list[list[str]] = []
    for index, left in enumerate(cases):
        left_tokens = token_set(left["conversation"][0]["message"])
        for right in cases[index + 1 :]:
            right_tokens = token_set(right["conversation"][0]["message"])
            similarity = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
            if similarity >= 0.92:
                pairs.append([left["case_id"], right["case_id"]])
    return pairs


def write_report(manifest: list[dict[str, Any]], cases: list[dict[str, Any]]) -> None:
    required_red_flags = [flag["id"] for flag in build_red_flags(manifest)["red_flags"]]
    red_flag_distribution = Counter(flag for case in cases for flag in case["expected_red_flags"])
    missing_red_flag_coverage = sorted(set(required_red_flags) - set(red_flag_distribution))
    report = {
        "schema_version": "1.0",
        "artifact_status": "pending_demo_only",
        "source_manifest_entries": len(manifest),
        "eligible_sources": sum(record["quality_status"] == "eligible" for record in manifest),
        "golden_case_count": len(cases),
        "unique_case_sources": len({case["source_id"] for case in cases}),
        "triage_distribution": dict(Counter(case["expected_triage"] for case in cases)),
        "speaker_role_distribution": dict(Counter(case["speaker_role"] for case in cases)),
        "turn_generation_provider_distribution": dict(
            Counter(case["turn_generation"]["provider"] for case in cases)
        ),
        "turn_generation_cache_status_distribution": dict(
            Counter(case["turn_generation"]["cache_status"] for case in cases)
        ),
        "red_flag_distribution": dict(red_flag_distribution),
        "missing_red_flag_coverage": missing_red_flag_coverage,
        "exact_or_near_duplicate_initial_turn_pairs": duplicate_pairs(cases),
        "cases_missing_evidence": [case["case_id"] for case in cases if not case["source_evidence"]["excerpt"]],
        "quality_gate": "pass" if len(cases) == 120 and len({case["source_id"] for case in cases}) == 120 and not missing_red_flag_coverage else "fail",
        "notes": "All triage labels are internal demo drafts pending clinical review.",
    }
    (TRIAGE_DIR / "quality_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_readme() -> None:
    (TRIAGE_DIR / "README.md").write_text(
        "# Triage test data v1\n\n"
        "Bộ này được dẫn xuất từ 603 nguồn trong `data/Corpus`/`Corpus_Redone` và các câu hỏi cùng nguồn. "
        "Mỗi case có `source_id`, URL, checksum và evidence excerpt để truy xuất.\n\n"
        "## Trạng thái an toàn\n\n"
        "Tất cả nhãn là `pending_demo_only`: không phải chẩn đoán, không phải protocol, và không được tự thông báo cho bệnh nhân. "
        "`expected_handoff` luôn là `true`.\n\n"
        "## Tái tạo\n\n"
        "```powershell\npython scripts/build_triage_v1_dataset.py\npython scripts/validate_triage_data.py\n```\n\n"
        "`source_manifest.jsonl` chứa 603 nguồn. `golden_cases_v1.jsonl` chứa 120 nguồn khác nhau, phân bổ 45/25/20/15/15 theo năm nhãn triage draft. "
        "`quality_report.json` là bằng chứng kiểm tra coverage và gần-trùng lặp.\n",
        encoding="utf-8",
    )


def format_duration(seconds: float) -> str:
    minutes, seconds = divmod(max(0, round(seconds)), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def render_progress(
    completed: int,
    total: int,
    case_id: str,
    cache_status: str,
    started_at: float,
    cache_counts: Counter[str],
) -> None:
    width = 24
    filled = round(width * completed / total)
    bar = "#" * filled + "-" * (width - filled)
    elapsed = time.monotonic() - started_at
    eta = elapsed * (total - completed) / completed if completed else 0
    cache_counts[cache_status] += 1
    cache_summary = ", ".join(f"{name}={count}" for name, count in sorted(cache_counts.items()))
    print(
        f"\r[{bar}] {completed:3d}/{total} ({completed / total:6.2%}) "
        f"{case_id} {cache_status}; elapsed {format_duration(elapsed)}, "
        f"ETA {format_duration(eta)}; {cache_summary}",
        end="",
        file=sys.stdout,
        flush=True,
    )
    if completed == total:
        print(file=sys.stdout, flush=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--turn-generator",
        choices=("rule_based", "gemini"),
        default="rule_based",
        help="Generator for the agent and follow-up turns (default: rule_based).",
    )
    parser.add_argument(
        "--refresh-gemini-cache",
        action="store_true",
        help="Call Gemini only for turn entries missing from the audit cache.",
    )
    parser.add_argument(
        "--force-refresh-gemini-cache",
        action="store_true",
        help="Regenerate cached Gemini entries as well as missing entries.",
    )
    parser.add_argument(
        "--gemini-cache-path",
        type=Path,
        default=GEMINI_CACHE_PATH,
        help="JSONL cache/audit path for Gemini turn responses.",
    )
    parser.add_argument(
        "--gemini-model",
        default=os.getenv("GEMINI_MODEL", DEFAULT_MODEL),
        help=f"Gemini model to use when refreshing (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--gemini-requests-per-minute",
        type=float,
        default=DEFAULT_REQUESTS_PER_MINUTE,
        help=f"Maximum Gemini requests per minute while refreshing (default: {DEFAULT_REQUESTS_PER_MINUTE:g}).",
    )
    args = parser.parse_args(argv)
    if (args.refresh_gemini_cache or args.force_refresh_gemini_cache) and args.turn_generator != "gemini":
        parser.error("Gemini cache refresh options require --turn-generator gemini")
    if args.force_refresh_gemini_cache:
        args.refresh_gemini_cache = True
    if args.gemini_requests_per_minute <= 0:
        parser.error("--gemini-requests-per-minute must be positive")
    return args


def main(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT / ".env")
    args = parse_args(argv)
    TRIAGE_DIR.mkdir(parents=True, exist_ok=True)
    turn_generator = (
        GeminiTurnGenerator(
            cache_path=args.gemini_cache_path,
            model=args.gemini_model,
            refresh=args.refresh_gemini_cache,
            force_refresh=args.force_refresh_gemini_cache,
            requests_per_minute=args.gemini_requests_per_minute,
        )
        if args.turn_generator == "gemini"
        else None
    )
    manifest = build_enriched_manifest()
    write_jsonl(MANIFEST_PATH, manifest)
    eligible = [record for record in manifest if record["quality_status"] == "eligible"]
    if len(eligible) < sum(LEVEL_ALLOCATION.values()):
        raise RuntimeError(f"Only {len(eligible)} eligible sources; need 120")

    used: set[str] = set()
    # Guarantee that every drafted red-flag has at least one source-grounded
    # regression case, before filling the remaining emergency allocation by score.
    mandatory_emergency_stems = [
        "kho-tho",
        "dau-that-nguc",
        "dot-quy",
        "me-day",
        "xuat-huyet-tieu-hoa",
        "sot-xuat-huyet",
        "chan-thuong-so-nao",
        "tram-cam",
        "viem-ruot-thua-cap",
    ]
    emergency_records = [find_record(eligible, stem) for stem in mandatory_emergency_stems]
    used.update(record["source_id"] for record in emergency_records)
    groups = {
        "emergency_now": emergency_records
        + select_records(
            eligible,
            emergency_score,
            LEVEL_ALLOCATION["emergency_now"] - len(emergency_records),
            used,
        ),
        "same_day": select_records(eligible, same_day_score, LEVEL_ALLOCATION["same_day"], used),
        "soon_24_72h": select_records(eligible, soon_score, LEVEL_ALLOCATION["soon_24_72h"], used),
        "home_monitoring": select_records(eligible, home_score, LEVEL_ALLOCATION["home_monitoring"], used),
        "insufficient_information_or_handoff": select_records(eligible, lambda _: 1, LEVEL_ALLOCATION["insufficient_information_or_handoff"], used),
    }
    case_specs = []
    offset = 0
    for level, records in groups.items():
        case_specs.extend((record, level, ordinal) for ordinal, record in enumerate(records, start=offset + 1))
        offset += len(records)
    cases = []
    started_at = time.monotonic()
    cache_counts: Counter[str] = Counter()
    try:
        for completed, (record, level, ordinal) in enumerate(case_specs, start=1):
            try:
                case = make_case(record, level, ordinal, turn_generator)
            except TurnGenerationError as exc:
                if turn_generator is None:
                    raise
                case = make_case(record, level, ordinal)
                case["turn_generation"] = {
                    "provider": "rule_based_fallback",
                    "model": turn_generator.model,
                    "prompt_version": "gemini_agent_question_and_follow_up_choice_v1",
                    "input_hash": None,
                    "cache_status": "fallback",
                    "generated_roles": [],
                    "follow_up_choice_index": case["turn_generation"]["follow_up_choice_index"],
                    "failure_reason": str(exc),
                }
            cases.append(case)
            render_progress(
                completed,
                len(case_specs),
                case["case_id"],
                case["turn_generation"]["cache_status"],
                started_at,
                cache_counts,
            )
    except TurnGenerationError as exc:
        if cases:
            print(file=sys.stdout, flush=True)
        print(f"BUILD FAILED\n- {exc}")
        return 1
    cases.sort(key=lambda case: case["case_id"])
    write_jsonl(TRIAGE_DIR / "golden_cases_v1.jsonl", cases)
    with (TRIAGE_DIR / "red_flags_draft.yaml").open("w", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(build_red_flags(manifest), handle, allow_unicode=True, sort_keys=False)
    write_report(manifest, cases)
    write_readme()
    print(json.dumps({"manifest_entries": len(manifest), "golden_cases": len(cases), "unique_sources": len(used)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
