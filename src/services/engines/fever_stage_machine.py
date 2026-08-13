"""Lớp mỏng: fever "cắm" vào state machine dùng chung (`src/services/symptom_protocol/stage_machine.py`)
qua `FEVER_PROTOCOL` (`fever_protocol.py`).

Toàn bộ chữ ký hàm/tên module-level GIỮ NGUYÊN như bản fever-riêng trước khi tách generic engine
(xem `_guidance/fever-detect-agent-task.md`, mục "kế thừa được") - test/caller cũ (`fever_intake_agent`,
`fever_session`, `fever_red_flag_engine`, toàn bộ test Checkpoint 2) không cần sửa gì.

Muốn thêm symptom_group mới: viết một `<disease>_protocol.py` theo mẫu `fever_protocol.py` (field
registry + rule catalog + hook lâm sàng), KHÔNG cần đụng tới file này hay
`src/services/symptom_protocol/`.
"""

from __future__ import annotations

from typing import Literal

from src.services.checklists.fever_checklist import Stage, clusters_for_stage
from src.services.engines.fever_protocol import (
    BUDGET,
    EMERGENCY_TRI_STATE_FIELDS,
    FEVER_PROTOCOL,
    age_in_months,
    budget_key,
    determine_route,
    has_provisional_emergency_signal,
    self_care_checklist_satisfied,
)
from src.services.symptom_protocol import stage_machine as _engine
from src.services.symptom_protocol.models import QuestionCluster

Route = Literal[
    "ROUTE_INFANT_HIGH",
    "ROUTE_HIGH_RISK",
    "ROUTE_STANDARD",
    "ROUTE_DENGUE_CONTEXT",
    "ROUTE_LOCALIZED_SOURCE",
]
StopReason = _engine.StopReason

STAGE_ORDER: tuple[Stage, ...] = FEVER_PROTOCOL.stage_order

__all__ = [
    "BUDGET",
    "EMERGENCY_TRI_STATE_FIELDS",
    "Route",
    "STAGE_ORDER",
    "Stage",
    "StopReason",
    "age_in_months",
    "budget_key",
    "clusters_for_stage",
    "determine_route",
    "has_provisional_emergency_signal",
    "next_cluster",
    "next_stage",
    "self_care_checklist_satisfied",
    "should_stop",
]


def next_cluster(
    stage: Stage,
    answers: dict[str, object],
    *,
    asked_ids: frozenset[str] = frozenset(),
) -> QuestionCluster | None:
    return _engine.next_cluster(FEVER_PROTOCOL, stage, answers, asked_ids=asked_ids)


def next_stage(stage: Stage) -> Stage | None:
    return _engine.next_stage(FEVER_PROTOCOL, stage)


def should_stop(
    stage: Stage,
    answers: dict[str, object],
    *,
    asked_count: int,
    route: Route | None = None,
    known_triage_level: str | None = None,
    user_can_continue: bool = True,
) -> StopReason | None:
    return _engine.should_stop(
        FEVER_PROTOCOL, stage, answers,
        asked_count=asked_count, route=route, known_triage_level=known_triage_level,
        user_can_continue=user_can_continue,
    )
