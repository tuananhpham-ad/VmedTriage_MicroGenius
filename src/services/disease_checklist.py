"""Checklist theo TỪNG BỆNH, nạp từ JSON trong `src/domain/` (mục 10 solution design:
`_guidance/vmedtriage_solution_design_review.md`).

Khác `intake_checklist.py` (bộ trường chung, hardcode cho demo Luồng B), checklist ở đây là
DATA-DRIVEN: mỗi bệnh là một file JSON riêng trong `src/domain/`, cho phép thêm bệnh mới bằng cách
thêm file JSON, không phải sửa code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DOMAIN_DIR = Path(__file__).resolve().parent.parent / "domain"


@dataclass(frozen=True, slots=True)
class ChecklistField:
    key: str
    label: str
    required: bool
    hint: str
    """Gợi ý ngữ nghĩa cho LLM biết trường này cần trích xuất cái gì (đưa vào prompt extraction)."""


@dataclass(frozen=True, slots=True)
class DiseaseChecklist:
    disease_id: str
    disease_label: str
    fields: tuple[ChecklistField, ...]
    completion_threshold: float

    @property
    def fields_by_key(self) -> dict[str, ChecklistField]:
        return {item.key: item for item in self.fields}

    @property
    def required_keys(self) -> tuple[str, ...]:
        return tuple(item.key for item in self.fields if item.required)


class ChecklistNotFoundError(FileNotFoundError):
    pass


def load_checklist(disease_id: str) -> DiseaseChecklist:
    """Nạp checklist từ `src/domain/_<disease_id>.json` (hoặc `<disease_id>.json`)."""
    for filename in (f"_{disease_id}.json", f"{disease_id}.json"):
        path = DOMAIN_DIR / filename
        if path.exists():
            return _parse(path)
    raise ChecklistNotFoundError(f"Không tìm thấy checklist cho bệnh '{disease_id}' trong {DOMAIN_DIR}")


def _parse(path: Path) -> DiseaseChecklist:
    raw = json.loads(path.read_text(encoding="utf-8"))
    fields = tuple(
        ChecklistField(
            key=item["key"],
            label=item["label"],
            required=bool(item.get("required", True)),
            hint=item.get("hint", ""),
        )
        for item in raw["fields"]
    )
    disease_id = raw.get("disease_id") or path.stem.lstrip("_")
    return DiseaseChecklist(
        disease_id=disease_id,
        disease_label=raw.get("disease_label", disease_id),
        fields=fields,
        completion_threshold=float(raw.get("completion_threshold", 0.85)),
    )


def completion_ratio(checklist: DiseaseChecklist, answers: dict[str, str | None]) -> float:
    """Tỉ lệ trường BẮT BUỘC đã có giá trị (không tính trường optional)."""
    required = checklist.required_keys
    if not required:
        return 1.0
    filled = sum(1 for key in required if _is_filled(answers.get(key)))
    return filled / len(required)


def missing_required_keys(checklist: DiseaseChecklist, answers: dict[str, str | None]) -> list[str]:
    return [key for key in checklist.required_keys if not _is_filled(answers.get(key))]


def missing_optional_keys(checklist: DiseaseChecklist, answers: dict[str, str | None]) -> list[str]:
    return [
        item.key
        for item in checklist.fields
        if not item.required and not _is_filled(answers.get(item.key))
    ]


def is_complete_enough(checklist: DiseaseChecklist, answers: dict[str, str | None]) -> bool:
    return completion_ratio(checklist, answers) >= checklist.completion_threshold


def _is_filled(value: str | None) -> bool:
    return bool(value and value.strip())
