"""Chữ ký cũ của bộ `fever_*`, curry sẵn `FEVER_PROTOCOL` — CHỈ dùng cho test.

Ba module `src/services/engines/fever_stage_machine.py`, `fever_red_flag_engine.py` và
`src/services/agents/fever_intake_agent.py` từng tồn tại để giữ nguyên public API của bản fever
tiền-refactor, nhờ đó ~450 dòng test vàng chạy lại KHÔNG SỬA GÌ sau khi cơ chế được tách sang
`symptom_protocol/`. Đó là bằng chứng "hành vi không đổi", và nó đã hoàn thành nhiệm vụ.

Sau khi refactor chốt, ba module đó thành 192 dòng uỷ nhiệm thuần trong `src/` mà KHÔNG code sản
phẩm nào gọi tới — chỉ test gọi. Việc curry một protocol vào chữ ký hàm là nhu cầu của test, nên nó
thuộc về `tests/`. Giữ ở `src/` thì mỗi người đọc `engines/` lại phải tự xác minh xem còn ai dùng
không (và ARCHITECTURE.md §17.3 từng kết luận nhầm chúng "chỉ còn test dùng, xoá được ngay" — xoá
được, nhưng không phải xoá không).

Test MỚI nên gọi thẳng `symptom_protocol.*` với protocol tường minh. File này chỉ để bộ test vàng
fever không phải viết lại, vì viết lại một bộ test đang xanh là cách nhanh nhất làm mất chính thứ nó
đang canh.
"""

from __future__ import annotations

from src.services.checklists.fever_checklist import QuestionCluster, Stage, clusters_for_stage
from src.services.engines.fever_protocol import (
    BUDGET,
    EMERGENCY_MESSAGE,
    FEVER_PROTOCOL,
    STAGE_ORDER,
    Route,
    determine_route,
    has_provisional_emergency_signal,
    self_care_checklist_satisfied,
)
from src.services.infra import provider_router
from src.services.symptom_protocol import intake_agent as _agent
from src.services.symptom_protocol import rule_engine as _rules
from src.services.symptom_protocol import stage_machine as _fsm
from src.services.symptom_protocol.intake_agent import TriState, TurnResult, _collect_fields
from src.services.symptom_protocol.models import RuleMatch, TimeTarget, TriageLevel
from src.services.symptom_protocol.rule_engine import RuleEngineResult
from src.services.symptom_protocol.stage_machine import StopReason

__all__ = [
    "BUDGET",
    "EMERGENCY_MESSAGE",
    "FEVER_PROTOCOL",
    "Route",
    "RuleEngineResult",
    "RuleMatch",
    "STAGE_ORDER",
    "Stage",
    "StopReason",
    "TimeTarget",
    "TriState",
    "TriageLevel",
    "TurnResult",
    "clusters_for_stage",
    "determine_route",
    "evaluate",
    "extract_cluster",
    "has_provisional_emergency_signal",
    "next_cluster",
    "next_stage",
    "run_turn",
    "scan_opportunistic_fields",
    "self_care_checklist_satisfied",
    "should_stop",
]

# Test Checkpoint 4 gọi qua attribute (`agent._tri_state_value(...)`), giữ nguyên đường dẫn đó.
_tri_state_value = _agent._tri_state_value
_repair_bareword_unknown = _agent._repair_bareword_unknown


# --- rule engine ---------------------------------------------------------------------------------


def evaluate(answers: dict[str, object]) -> RuleEngineResult:
    return _rules.evaluate(FEVER_PROTOCOL, answers)


# --- state machine -------------------------------------------------------------------------------


def next_cluster(
    stage: Stage,
    answers: dict[str, object],
    *,
    asked_ids: frozenset[str] = frozenset(),
) -> QuestionCluster | None:
    return _fsm.next_cluster(FEVER_PROTOCOL, stage, answers, asked_ids=asked_ids)


def next_stage(stage: Stage) -> Stage | None:
    return _fsm.next_stage(FEVER_PROTOCOL, stage)


def should_stop(
    stage: Stage,
    answers: dict[str, object],
    *,
    asked_count: int,
    route: Route | None = None,
    known_triage_level: str | None = None,
    user_can_continue: bool = True,
) -> StopReason | None:
    return _fsm.should_stop(
        FEVER_PROTOCOL, stage, answers,
        asked_count=asked_count, route=route, known_triage_level=known_triage_level,
        user_can_continue=user_can_continue,
    )


# --- intake agent --------------------------------------------------------------------------------


def extract_cluster(
    cluster: QuestionCluster,
    message: str,
    *,
    session_id: str | None = None,
    turn: int = 0,
    stage: str | None = None,
    credential: provider_router.LLMCredential | None = None,
) -> dict[str, TriState]:
    return _agent.extract_cluster(
        FEVER_PROTOCOL, cluster, message,
        session_id=session_id, turn=turn, stage=stage, credential=credential,
    )


def _collect(cluster: QuestionCluster, parsed: dict, message: str = "") -> dict[str, TriState]:
    return _collect_fields(
        FEVER_PROTOCOL, cluster.fields, parsed, batch_negation=cluster.batch_negation, message=message,
    )


def run_turn(
    session_id: str,
    *,
    turn: int,
    stage: str,
    cluster: QuestionCluster,
    message: str,
    answers: dict[str, TriState],
    asked_ids: frozenset[str] = frozenset(),
    retry_count: int = 0,
    credential: provider_router.LLMCredential | None = None,
) -> TurnResult:
    return _agent.run_turn(
        FEVER_PROTOCOL, session_id,
        turn=turn, stage=stage, cluster=cluster, message=message, answers=answers,
        asked_ids=asked_ids, retry_count=retry_count, credential=credential,
    )


def scan_opportunistic_fields(message: str) -> dict[str, TriState]:
    return _agent.scan_opportunistic_fields(FEVER_PROTOCOL, message)
