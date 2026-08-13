"""Vòng đời phiên hỏi-đáp DÙNG CHUNG cho mọi symptom_group - in-memory store, không auth, theo đúng
mẫu `intake_session.py` (demo). Nối 3 tầng cơ chế đã có thành 1 luồng phiên hoàn chỉnh:

- `stage_machine` quyết định cụm câu hỏi kế tiếp / stage / dừng - THUẦN rule.
- `rule_engine` là nguồn thật duy nhất cho `triage_level`/`reason_codes`/`triggered_rules`.
- `intake_agent.run_turn` gọi LLM đúng kiến trúc hướng C/E theo stage.

Vòng đời một phiên:

    COLLECTING ──(RED_FLAG ở gate stage)───────────────────> EMERGENCY
    COLLECTING ──(should_stop khác RED_FLAG, ở stage cuối)──> AWAITING_CONFIRMATION
        │                                                            │
        └────────────(người dùng xác nhận phiếu)────────────────────┴──> CONFIRMED

Mỗi symptom_group tạo MỘT `ProtocolSessionStore(protocol)` của riêng mình (session của các bệnh khác
nhau không lẫn vào nhau) - xem `fever_session.py` để biết cách "bind" cho fever.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from src.services.infra import console_log
from src.services.infra import fever_stage_log as stage_log
from src.services.infra.provider_router import LLMCredential
from src.services.symptom_protocol import intake_agent as agent
from src.services.symptom_protocol import rule_engine, stage_machine
from src.services.symptom_protocol.models import QuestionCluster
from src.services.symptom_protocol.protocol import SymptomProtocol


class SessionState(str, Enum):
    COLLECTING = "collecting"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    CONFIRMED = "confirmed"
    EMERGENCY = "emergency"


@dataclass(slots=True)
class Session:
    session_id: str = field(default_factory=lambda: str(uuid4()))
    state: SessionState = SessionState.COLLECTING
    stage: str = ""
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


class SessionNotFoundError(ValueError):
    pass


class EmptyMessageError(ValueError):
    pass


class ProtocolSessionStore:
    """Store + toàn bộ vòng đời phiên cho MỘT `SymptomProtocol`. Mỗi symptom_group giữ một instance
    riêng (không dùng chung 1 store giữa các bệnh, để `Session` của bệnh này không lẫn với bệnh kia)."""

    def __init__(self, protocol: SymptomProtocol) -> None:
        self.protocol = protocol
        self._sessions: dict[str, Session] = {}

    def create(self, credential: LLMCredential | None = None) -> Session:
        session = Session(credential=credential)
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def _require(self, session_id: str) -> Session:
        session = self.get(session_id)
        if session is None:
            raise SessionNotFoundError(f"Không tìm thấy phiên hỏi-đáp {self.protocol.name}.")
        return session

    def start_session(self, credential: LLMCredential | None = None) -> Session:
        protocol = self.protocol
        session = self.create(credential or protocol.default_credential)
        first_stage = protocol.stage_order[0]
        session.stage = first_stage
        stage_log.start(session.session_id, route=None, budget=0, namespace=protocol.name)
        stage_log.stage_enter(session.session_id, first_stage)

        cluster = stage_machine.next_cluster(protocol, first_stage, {})
        session.current_cluster = cluster
        session.last_question = cluster.script_hint if cluster is not None else ""
        if session.last_question:
            session.conversation.append({"role": "assistant", "content": session.last_question})

        provider = (session.credential.provider if session.credential else None) or "server/fallback"
        console_log.session_start(session.session_id, label=f"{protocol.name} intake", llm=provider)
        console_log.agent_question(session.session_id, session.last_question, llm_used=False)
        return session

    def submit_message(self, session_id: str, message: str) -> Session:
        protocol = self.protocol
        session = self._require(session_id)
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
        session.conversation.append({"role": "user", "content": cleaned})

        next_hint: QuestionCluster | None = None
        if stage not in protocol.gate_stages:
            # Hướng E: cụm kế tiếp phải chọn TRƯỚC khi biết kết quả extract lượt này (mục 2 kiến trúc).
            next_hint, _stage, _stop = self._walk_to_next_cluster(
                stage, session.answers, session.asked_ids | {cluster.id}, known_triage_level=session.triage_level,
            )

        result = agent.run_turn(
            protocol,
            session_id,
            turn=session.turn_count,
            stage=stage,
            cluster=cluster,
            message=cleaned,
            answers=session.answers,
            next_cluster=next_hint,
            asked_ids=frozenset(session.asked_ids),
            conversation=list(session.conversation),
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
            stage_log.finish(session_id, triage_level=result.triage_level, stop_reason="RED_FLAG", turns=session.turn_count)
            console_log.red_flag(session.session_id, list(result.reason_codes))
            console_log.session_end(session.session_id, state="emergency", turns=session.turn_count, percent=100)
            return session

        # Cập nhật kết luận triage MỚI NHẤT do rule engine tính ở lượt này (kể cả khi chưa EMERGENCY)
        # - cần thiết để should_stop chọn đúng hàng ngân sách (vd EARLY_VISIT khác SELF_CARE_CANDIDATE)
        # ngay khi đã biết, không phải đợi tới lúc finish.
        if result.triage_level is not None:
            session.triage_level = result.triage_level
            session.reason_codes = list(result.reason_codes)
            session.triggered_rules = list(result.triggered_rules)

        session.last_question = result.agent_message
        self._progress(session, result.next_cluster)
        return session

    def _walk_to_next_cluster(
        self,
        stage: str,
        answers: dict[str, object],
        asked_ids: set[str],
        *,
        known_triage_level: str | None = None,
    ) -> tuple[QuestionCluster | None, str, str | None]:
        """Đi tới cụm khả dụng kế tiếp, băng qua ranh giới stage nếu cần, dừng lại đúng lúc theo
        `should_stop`. Hàm THUẦN, không side-effect - dùng để "peek" (hướng E) lẫn "progress" thật
        sau lượt (mọi hướng)."""
        protocol = self.protocol
        current_stage = stage
        while True:
            route = protocol.determine_route(answers)
            stop = stage_machine.should_stop(
                protocol, current_stage, answers, asked_count=len(asked_ids), route=route,
                known_triage_level=known_triage_level,
            )
            if stop is not None:
                return None, current_stage, stop
            cluster = stage_machine.next_cluster(protocol, current_stage, answers, asked_ids=frozenset(asked_ids))
            if cluster is not None:
                return cluster, current_stage, None
            following = stage_machine.next_stage(protocol, current_stage)
            if following is None:
                stop = "SUFFICIENT_EVIDENCE" if protocol.self_care_checklist_satisfied(answers) else "BUDGET_EXHAUSTED"
                return None, current_stage, stop
            current_stage = following

    def _progress(self, session: Session, immediate_next: QuestionCluster | None) -> None:
        """Cập nhật `session.stage`/`session.current_cluster` cho lượt kế tiếp, hoặc kết thúc phiên."""
        protocol = self.protocol
        if immediate_next is not None:
            if immediate_next.stage != session.stage:
                stage_log.stage_enter(session.session_id, immediate_next.stage)
            session.stage = immediate_next.stage
            session.current_cluster = immediate_next
            return

        following_stage = stage_machine.next_stage(protocol, session.stage)
        if following_stage is None:
            self._finish(session, "SUFFICIENT_EVIDENCE" if protocol.self_care_checklist_satisfied(session.answers) else "BUDGET_EXHAUSTED")
            return

        stage_log.stage_enter(session.session_id, following_stage)
        cluster, final_stage, stop = self._walk_to_next_cluster(
            following_stage, session.answers, session.asked_ids, known_triage_level=session.triage_level,
        )
        if stop is not None:
            self._finish(session, stop)
            return
        session.stage = final_stage
        session.current_cluster = cluster

    def _finish(self, session: Session, stop_reason: str) -> None:
        result = rule_engine.evaluate(self.protocol, session.answers)
        session.triage_level = result.triage_level
        session.reason_codes = list(result.reason_codes)
        session.triggered_rules = list(result.triggered_rules)
        session.stop_reason = stop_reason
        session.state = SessionState.EMERGENCY if result.triage_level == "EMERGENCY" else SessionState.AWAITING_CONFIRMATION
        session.current_cluster = None
        session.last_question = ""
        stage_log.finish(session.session_id, triage_level=result.triage_level, stop_reason=stop_reason, turns=session.turn_count)
        console_log.summary(session.session_id, "generated", percent=100)

    def confirm_summary(self, session_id: str, is_correct: bool) -> Session:
        session = self._require(session_id)
        if session.state != SessionState.AWAITING_CONFIRMATION:
            raise ValueError("Phiên chưa có phiếu tóm tắt để xác nhận, hoặc đã ở nhánh cấp cứu.")
        if is_correct:
            session.state = SessionState.CONFIRMED
            console_log.session_end(session.session_id, state="confirmed", turns=session.turn_count, percent=100)
        return session
