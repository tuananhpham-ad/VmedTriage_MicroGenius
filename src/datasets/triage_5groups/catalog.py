"""Load and validate versioned red-flag and scenario catalogs."""

from __future__ import annotations

from pathlib import Path

import yaml

from .schemas import RedFlag, SymptomGroup


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Catalog {path} must contain a mapping")
    return payload


def load_catalogs(red_flag_path: Path, scenario_path: Path) -> tuple[str, dict[str, RedFlag], list[SymptomGroup]]:
    red_payload = load_yaml(red_flag_path)
    scenario_payload = load_yaml(scenario_path)
    version = str(red_payload.get("version", ""))
    if not version:
        raise ValueError("red flag catalog needs a version")

    flags = {item.id: item for item in (RedFlag.model_validate(raw) for raw in red_payload.get("red_flags", []))}
    if len(flags) != len(red_payload.get("red_flags", [])):
        raise ValueError("red flag IDs must be unique")

    groups = [SymptomGroup.model_validate(raw) for raw in scenario_payload.get("groups", [])]
    if len(groups) != 5 or len({group.id for group in groups}) != 5:
        raise ValueError("scenario catalog must contain exactly five unique groups")
    for group in groups:
        unknown = set(group.red_flag_ids).difference(flags)
        if unknown:
            raise ValueError(f"{group.id} references unknown red flags: {sorted(unknown)}")
    return version, flags, groups
