"""State machine cho phiên hỏi-đáp fever (Bước 6, `_guidance/fever-detect-agent-task.md`).

Nối 3 module đã có ở Bước 2-5 thành một luồng phiên hoàn chỉnh, theo đúng mẫu
`intake_session.py` (in-memory store, không auth, dùng cho demo):

- `fever_stage_machine` (Bước 2) quyết định cụm câu hỏi kế tiếp / stage / dừng - THUẦN rule.
- `fever_red_flag_engine` (Bước 3) là nguồn thật duy nhất cho `triage_level`/`reason_codes`.
- `fever_intake_agent.run_turn` (Bước 4-5) gọi LLM đúng kiến trúc hướng C/E theo stage.

Vòng đời một phiên:

    COLLECTING ──(RED_FLAG ở Stage 3A/3B)──────────────────> EMERGENCY
    COLLECTING ──(should_stop khác RED_FLAG, ở Stage 5)────> AWAITING_CONFIRMATION
        │                                                            │
        └────────────(người dùng xác nhận phiếu)────────────────────┴──> CONFIRMED
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from src.services.agents import fever_intake_agent as agent
from src.services.checklists.fever_checklist import QuestionCluster
from src.services.engines import fever_red_flag_engine
from src.services.engines import fever_stage_machine as fsm
from src.services.infra import console_log, fever_stage_log
from src.services.infra.provider_router import LLMCredential


class SessionState(str, Enum):
    COLLECTING = "collecting"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    CONFIRMED = "confirmed"
    EMERGENCY = "emergency"


@dataclass(slots=True)
class FeverSession:
    session_id: str = field(default_factory=lambda: str(uuid4()))
    state: SessionState = SessionState.COLLECTING
    stage: str = "0"
    answers: dict[str, object] = field(default_factory=dict)
    asked_ids: set[str] = field(default_factory=set)
    current_cluster: QuestionCluster | None = None
    conversation: list[dict[str, str]] = field(default_factory=list)
    turn_count: int = 0
    last_question: str = ""
    llm_used_last_turn: bool = False
    triage_level: str | None = None
    reason_codes: list[str] = field(default_factory=list)
    triggered_rules: list[str] = field(default_factory=list)
    stop_reason: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    credential: LLMCredential | None = None


class InMemoryFeverSessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, FeverSession] = {}

    def create(self, credential: LLMCredential | None = None) -> FeverSession:
        session = FeverSession(credential=credential)
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> FeverSession | None:
        return self._sessions.get(session_id)


session_store = InMemoryFeverSessionStore()


class SessionNotFoundError(ValueError):
    pass


class EmptyMessageError(ValueError):
    pass


def get_session(session_id: str) -> FeverSession:
    return _require_session(session_id)


def start_session(credential: LLMCredential | None = None) -> FeverSession:
    session = session_store.create(credential)
    fever_stage_log.start(session.session_id, route=None, budget=0)
    fever_stage_log.stage_enter(session.session_id, "0")

    cluster = fsm.next_cluster("0", {})
    session.current_cluster = cluster
    session.last_question = cluster.script_hint if cluster is not None else ""
    if session.last_question:
        session.conversation.append({"role": "assistant", "content": session.last_question})

    provider = (credential.provider if credential else None) or "server/fallback"
    console_log.session_start(session.session_id, label="Fever intake", llm=provider)
    console_log.agent_question(session.session_id, session.last_question, llm_used=False)
    return session


def submit_message(session_id: str, message: str) -> FeverSession:
    session = _require_session(session_id)
    if session.state != SessionState.COLLECTING:
        return session
    cleaned = (message or "").strip()
    if not cleaned:
        raise EmptyMessageError("Nội dung tin nhắn không được để trống.")
    if session.current_cluster is None:
        # Không còn cụm nào để hỏi (lẽ ra đã finish) - phòng vệ, không nên xảy ra trong luồng bình thường.
        return session

    session.turn_count += 1
    cluster = session.current_cluster
    stage = session.stage
    console_log.user_message(session.session_id, cleaned, turn=session.turn_count)

    next_hint: QuestionCluster | None = None
    if stage not in ("3A", "3B"):
        # Hướng E: cụm kế tiếp phải chọn TRƯỚC khi biết kết quả extract lượt này (mục 2 kiến trúc).
        next_hint, _stage, _stop = _walk_to_next_cluster(
            stage, session.answers, session.asked_ids | {cluster.id}, known_triage_level=session.triage_level,
        )

    result = agent.run_turn(
        session_id,
        turn=session.turn_count,
        stage=stage,
        cluster=cluster,
        message=cleaned,
        answers=session.answers,
        next_cluster=next_hint,
        asked_ids=frozenset(session.asked_ids),
        credential=session.credential,
    )

    session.answers = result.answers
    session.asked_ids.add(cluster.id)
    session.llm_used_last_turn = result.llm_used
    if result.agent_message:
        session.conversation.append({"role": "assistant", "content": result.agent_message})
    console_log.extraction(
        session.session_id, result.extracted,
        percent=round(100 * len(session.asked_ids) / max(len(session.asked_ids) + 1, 1)),
        filled=len(session.asked_ids), total=len(session.asked_ids) + 1,
    )

    if result.emergency:
        session.triage_level = result.triage_level
        session.reason_codes = list(result.reason_codes)
        session.triggered_rules = list(result.triggered_rules)
        session.state = SessionState.EMERGENCY
        session.current_cluster = None
        session.last_question = result.agent_message
        session.stop_reason = "RED_FLAG"
        fever_stage_log.finish(session_id, triage_level=result.triage_level, stop_reason="RED_FLAG", turns=session.turn_count)
        console_log.red_flag(session.session_id, list(result.reason_codes))
        console_log.session_end(session.session_id, state="emergency", turns=session.turn_count, percent=100)
        return session

    # Cập nhật kết luận triage MỚI NHẤT do rule engine tính ở lượt này (kể cả khi chưa EMERGENCY) -
    # cần thiết để should_stop chọn đúng hàng ngân sách §6.5 (vd EARLY_VISIT 8-12, không phải mặc
    # định SELF_CARE_CANDIDATE 12-16) ngay khi đã biết EARLY_VISIT, không phải đợi tới lúc finish.
    if result.triage_level is not None:
        session.triage_level = result.triage_level
        session.reason_codes = list(result.reason_codes)
        session.triggered_rules = list(result.triggered_rules)

    session.last_question = result.agent_message
    _progress(session, result.next_cluster)
    return session


def _walk_to_next_cluster(
    stage: str,
    answers: dict[str, object],
    asked_ids: set[str],
    *,
    known_triage_level: str | None = None,
) -> tuple[QuestionCluster | None, str, str | None]:
    """Đi tới cụm khả dụng kế tiếp, băng qua ranh giới stage nếu cần, dừng lại đúng lúc theo
    `should_stop`. Hàm THUẦN, không side-effect - dùng để "peek" (hướng E) lẫn "progress" thật sau
    lượt (mọi hướng)."""
    current_stage = stage
    while True:
        route = fsm.determine_route(answers)
        stop = fsm.should_stop(
            current_stage, answers, asked_count=len(asked_ids), route=route, known_triage_level=known_triage_level,
        )
        if stop is not None:
            return None, current_stage, stop
        cluster = fsm.next_cluster(current_stage, answers, asked_ids=frozenset(asked_ids))
        if cluster is not None:
            return cluster, current_stage, None
        following = fsm.next_stage(current_stage)
        if following is None:
            stop = "SUFFICIENT_EVIDENCE" if fsm.self_care_checklist_satisfied(answers) else "BUDGET_EXHAUSTED"
            return None, current_stage, stop
        current_stage = following


def _progress(session: FeverSession, immediate_next: QuestionCluster | None) -> None:
    """Cập nhật `session.stage`/`session.current_cluster` cho lượt kế tiếp, hoặc kết thúc phiên."""
    if immediate_next is not None:
        if immediate_next.stage != session.stage:
            fever_stage_log.stage_enter(session.session_id, immediate_next.stage)
        session.stage = immediate_next.stage
        session.current_cluster = immediate_next
        return

    following_stage = fsm.next_stage(session.stage)
    if following_stage is None:
        _finish(session, "SUFFICIENT_EVIDENCE" if fsm.self_care_checklist_satisfied(session.answers) else "BUDGET_EXHAUSTED")
        return

    fever_stage_log.stage_enter(session.session_id, following_stage)
    cluster, final_stage, stop = _walk_to_next_cluster(
        following_stage, session.answers, session.asked_ids, known_triage_level=session.triage_level,
    )
    if stop is not None:
        _finish(session, stop)
        return
    session.stage = final_stage
    session.current_cluster = cluster


def _finish(session: FeverSession, stop_reason: str) -> None:
    result = fever_red_flag_engine.evaluate(session.answers)
    session.triage_level = result.triage_level
    session.reason_codes = list(result.reason_codes)
    session.triggered_rules = list(result.triggered_rules)
    session.stop_reason = stop_reason
    session.state = SessionState.EMERGENCY if result.triage_level == "EMERGENCY" else SessionState.AWAITING_CONFIRMATION
    session.current_cluster = None
    session.last_question = ""
    fever_stage_log.finish(session.session_id, triage_level=result.triage_level, stop_reason=stop_reason, turns=session.turn_count)
    console_log.summary(session.session_id, "generated", percent=100)


def confirm_summary(session_id: str, is_correct: bool) -> FeverSession:
    session = _require_session(session_id)
    if session.state != SessionState.AWAITING_CONFIRMATION:
        raise ValueError("Phiên chưa có phiếu tóm tắt để xác nhận, hoặc đã ở nhánh cấp cứu.")
    if is_correct:
        session.state = SessionState.CONFIRMED
        console_log.session_end(session.session_id, state="confirmed", turns=session.turn_count, percent=100)
    return session


def _require_session(session_id: str) -> FeverSession:
    session = session_store.get(session_id)
    if session is None:
        raise SessionNotFoundError("Không tìm thấy phiên hỏi-đáp fever.")
    return session
