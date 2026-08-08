"""State machine cho phiên hỏi-đáp theo checklist TỪNG BỆNH (mục 10 solution design:
`_guidance/vmedtriage_solution_design_review.md`).

Vòng đời một phiên (giống `intake_session.py`, khác ở chỗ checklist nạp theo bệnh từ
`src/domain/*.json` thay vì bộ trường chung hardcode):

    collecting ──(đủ >= completion_threshold trường bắt buộc)──> awaiting_confirmation
        ▲                                                                │
        └──────────(người dùng chọn "Chưa đúng" + nêu chỗ cần sửa)───────┘
                                                                         │
                                       (người dùng chọn "Đúng rồi")──────┴──> confirmed

Ghi chú phạm vi: phiên này CHỈ thu thập + tóm tắt + xin xác nhận của người dùng. Nó KHÔNG sinh mức độ
ưu tiên, KHÔNG gửi cho điều dưỡng - phần nối vào `TriagePipeline`/GNN advisory (mục 10.3, còn ở dạng
việc-cần-làm) nằm ngoài phạm vi của module này.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from src.services.agents.disease_agent import DiseaseQAAgent
from src.services.checklists.disease_checklist import (
    DiseaseChecklist,
    completion_ratio,
    is_complete_enough,
    load_checklist,
    missing_required_keys,
)
from src.services.infra import console_log, session_log
from src.services.infra.provider_router import LLMCredential

# Chặn hỏi vô hạn khi người dùng liên tục không cung cấp được trường còn thiếu: sau ngưỡng này,
# phiên chuyển sang xác nhận với các trường đã có, phần còn thiếu hiển thị "(chưa cung cấp)".
MAX_TURNS_BEFORE_FORCE_SUMMARY = 12


class SessionState(str, Enum):
    COLLECTING = "collecting"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    CONFIRMED = "confirmed"


@dataclass(slots=True)
class DiseaseSession:
    checklist: DiseaseChecklist
    session_id: str = field(default_factory=lambda: str(uuid4()))
    state: SessionState = SessionState.COLLECTING
    answers: dict[str, str | None] = field(default_factory=dict)
    conversation: list[dict[str, str]] = field(default_factory=list)
    turn_count: int = 0
    last_question: str = ""
    llm_used_last_turn: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # API key riêng của người test. CHỈ in-memory: không ghi ra logs/, không in ra console.
    credential: LLMCredential | None = None


class InMemoryDiseaseSessionStore:
    """In-memory, mất khi restart process - đủ cho demo, giống InMemoryIntakeSessionStore."""

    def __init__(self) -> None:
        self._sessions: dict[str, DiseaseSession] = {}

    def create(self, checklist: DiseaseChecklist, credential: LLMCredential | None = None) -> DiseaseSession:
        session = DiseaseSession(checklist=checklist, credential=credential)
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> DiseaseSession | None:
        return self._sessions.get(session_id)


session_store = InMemoryDiseaseSessionStore()

# Một DiseaseQAAgent mỗi bệnh là đủ (agent không giữ state của phiên, chỉ cần checklist) - cache lại
# để không phải build lại field_specs/prompt template mỗi lượt.
_agents_by_disease: dict[str, DiseaseQAAgent] = {}


class SessionNotFoundError(ValueError):
    pass


class EmptyMessageError(ValueError):
    pass


def _agent_for(checklist: DiseaseChecklist, credential: LLMCredential | None = None) -> DiseaseQAAgent:
    # Có credential riêng -> agent riêng, KHÔNG cache: cache theo disease_id sẽ khiến phiên của
    # người này dùng nhầm key của người khác.
    if credential is not None:
        return DiseaseQAAgent(checklist, credential)
    agent = _agents_by_disease.get(checklist.disease_id)
    if agent is None:
        agent = DiseaseQAAgent(checklist)
        _agents_by_disease[checklist.disease_id] = agent
    return agent


def _session_agent(session: DiseaseSession) -> DiseaseQAAgent:
    return _agent_for(session.checklist, session.credential)


def start_session(disease_id: str, credential: LLMCredential | None = None) -> DiseaseSession:
    checklist = load_checklist(disease_id)
    session = session_store.create(checklist, credential)
    first_field_label = checklist.fields[0].label.lower() if checklist.fields else "thông tin"
    opening = (
        f'Chào bạn, mình cần thu thập một vài thông tin về "{checklist.disease_label}". '
        f"Bạn cho mình biết {first_field_label} nhé?"
    )
    session.last_question = opening
    session.conversation.append({"role": "assistant", "content": opening})

    session_log.start(
        session.session_id,
        disease_id=checklist.disease_id,
        disease_label=checklist.disease_label,
        threshold=checklist.completion_threshold,
        fields=[
            {"key": item.key, "label": item.label, "required": item.required} for item in checklist.fields
        ],
    )
    session_log.event(session.session_id, "agent_question", question=opening, llm_used=False, source="opening")

    agent = _session_agent(session)
    provider = agent.active_provider or "fallback deterministic"
    model = (credential.model if credential else None) or "model mặc định"
    source = "key của bạn" if credential else "key server"
    console_log.session_start(
        session.session_id,
        label=checklist.disease_label,
        llm=f"{provider}/{model} ({source})",  # KHÔNG in api_key, chỉ tên provider/model
    )
    console_log.agent_question(session.session_id, opening, llm_used=False)
    return session


def submit_message(session_id: str, message: str) -> DiseaseSession:
    """Xử lý một lượt trả lời: trích xuất -> quyết định hỏi tiếp hay chuyển sang tóm tắt."""
    session = _require_session(session_id)
    cleaned = (message or "").strip()
    if not cleaned:
        raise EmptyMessageError("Nội dung tin nhắn không được để trống.")

    session.conversation.append({"role": "user", "content": cleaned})
    session.turn_count += 1
    session_log.event(session.session_id, "user_message", message=cleaned, turn=session.turn_count)
    console_log.user_message(session.session_id, cleaned, turn=session.turn_count)

    agent = _session_agent(session)
    extracted, llm_used = agent.extract(cleaned, session.answers)
    session.answers.update(extracted)
    session.llm_used_last_turn = llm_used
    _log_extraction(session, extracted, llm_used)

    forced = session.turn_count >= MAX_TURNS_BEFORE_FORCE_SUMMARY
    if is_complete_enough(session.checklist, session.answers) or forced:
        session.state = SessionState.AWAITING_CONFIRMATION
        session.last_question = ""
        _log_summary(session, "generated", forced=forced)
        return session

    question, _targets, question_llm_used = agent.next_question(session.conversation, session.answers)
    session.llm_used_last_turn = llm_used or question_llm_used
    session.last_question = question
    if question:
        session.conversation.append({"role": "assistant", "content": question})
        session_log.event(
            session.session_id,
            "agent_question",
            question=question,
            llm_used=question_llm_used,
            targets=_targets,
            source="follow_up",
        )
        console_log.agent_question(session.session_id, question, llm_used=question_llm_used)
    return session


def confirm_summary(session_id: str, is_correct: bool, correction: str | None = None) -> DiseaseSession:
    """Người dùng xác nhận phiếu tóm tắt.

    is_correct=True  -> chốt phiên (CONFIRMED).
    is_correct=False -> quay lại thu thập; `correction` được xử lý như một lượt đính chính.
    """
    session = _require_session(session_id)
    if session.state == SessionState.COLLECTING:
        raise ValueError("Phiên chưa có phiếu tóm tắt để xác nhận.")

    if is_correct:
        session.state = SessionState.CONFIRMED
        session.last_question = ""
        session.conversation.append({"role": "user", "content": "[Người dùng xác nhận phiếu tóm tắt là ĐÚNG]"})
        # Bản "confirmed" = đúng nội dung người dùng đã bấm gửi đi, lưu tách khỏi các bản nháp trước.
        _log_summary(session, "confirmed")
        return session

    session.state = SessionState.COLLECTING
    cleaned = (correction or "").strip()
    if not cleaned:
        # Không nêu rõ chỗ sai -> hỏi lại cho rõ thay vì đoán bừa chỗ cần sửa.
        question = "Bạn cho mình biết thông tin nào chưa đúng và cần sửa lại thành gì nhé?"
        session.last_question = question
        session.conversation.append({"role": "assistant", "content": question})
        session_log.event(session.session_id, "summary_rejected", correction=None)
        session_log.event(
            session.session_id, "agent_question", question=question, llm_used=False, source="ask_what_to_fix"
        )
        return session

    session.conversation.append({"role": "user", "content": cleaned})
    session_log.event(session.session_id, "summary_rejected", correction=cleaned)

    agent = _session_agent(session)
    before = dict(session.answers)
    extracted, llm_used = agent.extract_correction(cleaned, session.answers)
    session.answers.update(extracted)
    session.llm_used_last_turn = llm_used
    _log_extraction(session, extracted, llm_used, previous=before, kind="correction")

    if is_complete_enough(session.checklist, session.answers):
        session.state = SessionState.AWAITING_CONFIRMATION
        session.last_question = ""
        _log_summary(session, "revised")
        return session

    question, _targets, question_llm_used = agent.next_question(session.conversation, session.answers)
    session.llm_used_last_turn = llm_used or question_llm_used
    session.last_question = question
    if question:
        session.conversation.append({"role": "assistant", "content": question})
        session_log.event(
            session.session_id,
            "agent_question",
            question=question,
            llm_used=question_llm_used,
            targets=_targets,
            source="follow_up",
        )
        console_log.agent_question(session.session_id, question, llm_used=question_llm_used)
    return session


def build_summary_text(session: DiseaseSession) -> str:
    return _session_agent(session).build_summary_text(session.answers)


def build_summary_rows(session: DiseaseSession) -> list[dict[str, object]]:
    """Phiếu tóm tắt dạng field-value. Trường chưa có -> is_missing=True, KHÔNG bịa giá trị."""
    rows: list[dict[str, object]] = []
    for item in session.checklist.fields:
        value = session.answers.get(item.key)
        filled = bool(value and str(value).strip())
        rows.append(
            {
                "key": item.key,
                "label": item.label,
                "value": value if filled else None,
                "is_missing": not filled,
                "required": item.required,
            }
        )
    return rows


def progress_of(session: DiseaseSession) -> dict[str, object]:
    missing = missing_required_keys(session.checklist, session.answers)
    required = session.checklist.required_keys
    return {
        "ratio": round(completion_ratio(session.checklist, session.answers), 4),
        "percent": round(completion_ratio(session.checklist, session.answers) * 100),
        "filled_required": len(required) - len(missing),
        "total_required": len(required),
        "missing_required_labels": [session.checklist.fields_by_key[key].label for key in missing],
    }


def _log_extraction(
    session: DiseaseSession,
    extracted: dict[str, str],
    llm_used: bool,
    *,
    previous: dict[str, str | None] | None = None,
    kind: str = "extraction",
) -> None:
    """Ghi kết quả trích xuất + tiến độ sau lượt đó.

    Với lượt đính chính, `previous` cho phép log cả giá trị CŨ bị ghi đè - cần cho việc tra sau này
    xem người dùng đã sửa từ gì thành gì.
    """
    payload: dict[str, object] = {
        "extracted": extracted,
        "llm_used": llm_used,
        "answers": dict(session.answers),
        "progress": progress_of(session),
    }
    if previous is not None:
        payload["overwritten"] = {key: previous.get(key) for key in extracted if previous.get(key) is not None}
    session_log.event(session.session_id, kind, **payload)
    session_log.update_state(session.session_id, session.state.value, session.answers)

    progress = payload["progress"]
    console_log.extraction(
        session.session_id,
        extracted,
        percent=progress["percent"],
        filled=progress["filled_required"],
        total=progress["total_required"],
    )


def _log_summary(session: DiseaseSession, kind: str, *, forced: bool = False) -> None:
    session_log.summary(
        session.session_id,
        kind,
        text=build_summary_text(session),
        rows=build_summary_rows(session),
        answers=session.answers,
    )
    session_log.event(
        session.session_id,
        f"summary_{kind}",
        progress=progress_of(session),
        # forced=True nghĩa là tóm tắt vì chạm MAX_TURNS chứ KHÔNG phải vì đã đủ trường.
        forced_by_max_turns=forced,
    )
    session_log.update_state(session.session_id, session.state.value, session.answers)

    progress = progress_of(session)
    console_log.summary(session.session_id, kind, percent=progress["percent"])
    if kind == "confirmed":
        console_log.session_end(
            session.session_id,
            state=session.state.value,
            turns=session.turn_count,
            percent=progress["percent"],
        )


def _require_session(session_id: str) -> DiseaseSession:
    session = session_store.get(session_id)
    if session is None:
        raise SessionNotFoundError("Không tìm thấy phiên hỏi-đáp.")
    return session
