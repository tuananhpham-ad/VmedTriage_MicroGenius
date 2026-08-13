"""Lớp mỏng: fever "cắm" vào intake agent dùng chung
(`src/services/symptom_protocol/intake_agent.py`) qua `FEVER_PROTOCOL` (`fever_protocol.py`).

Toàn bộ chữ ký hàm/tên module-level GIỮ NGUYÊN như bản fever-riêng trước khi tách generic engine
(xem `_guidance/fever-detect-agent-task.md`, mục "kế thừa được") - caller cũ (`fever_session`, toàn
bộ test Checkpoint 4-5) không cần sửa gì.

LLM ở đây CHỈ làm một việc: trích field từ free text vào đúng schema của MỘT cụm câu hỏi, ghép đúng
hướng C/E theo stage. Quyết định next_cluster/route/dừng KHÔNG nằm ở đây - đó là việc của
`fever_stage_machine.py` + `fever_red_flag_engine.py`, đúng `coding_convention.md` rule 1-2.
"""

from __future__ import annotations

from src.services.checklists.fever_checklist import QuestionCluster
from src.services.engines.fever_protocol import EMERGENCY_MESSAGE, FEVER_PROTOCOL
from src.services.infra import provider_router
from src.services.symptom_protocol import intake_agent as _engine
from src.services.symptom_protocol.intake_agent import TriState, _collect_fields
from src.services.symptom_protocol.intake_agent import TurnResult as FeverTurnResult

__all__ = [
    "EMERGENCY_MESSAGE",
    "FeverTurnResult",
    "TriState",
    "extract_cluster",
    "run_turn",
    "scan_opportunistic_fields",
]

# Truy cập qua attribute (không phải import trực tiếp) để ruff không coi là "unused import" - vẫn
# giữ nguyên đường dẫn `agent._tri_state_value(...)`/`agent._repair_bareword_unknown(...)` mà test
# Checkpoint 4 cũ đang dùng (module cơ chế chung nằm ở `symptom_protocol.intake_agent`).
_tri_state_value = _engine._tri_state_value
_repair_bareword_unknown = _engine._repair_bareword_unknown


def extract_cluster(
    cluster: QuestionCluster,
    message: str,
    *,
    session_id: str | None = None,
    turn: int = 0,
    stage: str | None = None,
    credential: provider_router.LLMCredential | None = None,
) -> dict[str, TriState]:
    return _engine.extract_cluster(
        FEVER_PROTOCOL, cluster, message,
        session_id=session_id, turn=turn, stage=stage, credential=credential,
    )


def _collect(cluster: QuestionCluster, parsed: dict) -> dict[str, TriState]:
    return _collect_fields(FEVER_PROTOCOL, cluster.fields, parsed, batch_negation=cluster.batch_negation)


def run_turn(
    session_id: str,
    *,
    turn: int,
    stage: str,
    cluster: QuestionCluster,
    message: str,
    answers: dict[str, TriState],
    next_cluster: QuestionCluster | None = None,
    asked_ids: frozenset[str] = frozenset(),
    credential: provider_router.LLMCredential | None = None,
) -> FeverTurnResult:
    return _engine.run_turn(
        FEVER_PROTOCOL, session_id,
        turn=turn, stage=stage, cluster=cluster, message=message, answers=answers,
        next_cluster=next_cluster, asked_ids=asked_ids, credential=credential,
    )


def scan_opportunistic_fields(message: str) -> dict[str, TriState]:
    return _engine.scan_opportunistic_fields(FEVER_PROTOCOL, message)
