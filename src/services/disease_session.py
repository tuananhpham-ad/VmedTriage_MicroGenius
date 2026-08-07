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

from src.services.disease_agent import DiseaseQAAgent
from src.services.disease_checklist import (
    DiseaseChecklist,
    completion_ratio,
    is_complete_enough,
    load_checklist,
    missing_required_keys,
)

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


class InMemoryDiseaseSessionStore:
    """In-memory, mất khi restart process - đủ cho demo, giống InMemoryIntakeSessionStore."""

    def __init__(self) -> None:
        self._sessions: dict[str, DiseaseSession] = {}

    def create(self, checklist: DiseaseChecklist) -> DiseaseSession:
        session = DiseaseSession(checklist=checklist)
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


def _agent_for(checklist: DiseaseChecklist) -> DiseaseQAAgent:
    agent = _agents_by_disease.get(checklist.disease_id)
    if agent is None:
        agent = DiseaseQAAgent(checklist)
        _agents_by_disease[checklist.disease_id] = agent
    return agent


def start_session(disease_id: str) -> DiseaseSession:
    checklist = load_checklist(disease_id)
    session = session_store.create(checklist)
    first_field_label = checklist.fields[0].label.lower() if checklist.fields else "thông tin"
    opening = (
        f'Chào bạn, mình cần thu thập một vài thông tin về "{checklist.disease_label}". '
        f"Bạn cho mình biết {first_field_label} nhé?"
    )
    session.last_question = opening
    session.conversation.append({"role": "assistant", "content": opening})
    return session


def submit_message(session_id: str, message: str) -> DiseaseSession:
    """Xử lý một lượt trả lời: trích xuất -> quyết định hỏi tiếp hay chuyển sang tóm tắt."""
    session = _require_session(session_id)
    cleaned = (message or "").strip()
    if not cleaned:
        raise EmptyMessageError("Nội dung tin nhắn không được để trống.")

    session.conversation.append({"role": "user", "content": cleaned})
    session.turn_count += 1

    agent = _agent_for(session.checklist)
    extracted, llm_used = agent.extract(cleaned, session.answers)
    session.answers.update(extracted)
    session.llm_used_last_turn = llm_used

    if is_complete_enough(session.checklist, session.answers) or session.turn_count >= MAX_TURNS_BEFORE_FORCE_SUMMARY:
        session.state = SessionState.AWAITING_CONFIRMATION
        session.last_question = ""
        return session

    question, _targets, question_llm_used = agent.next_question(session.conversation, session.answers)
    session.llm_used_last_turn = llm_used or question_llm_used
    session.last_question = question
    if question:
        session.conversation.append({"role": "assistant", "content": question})
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
        return session

    session.state = SessionState.COLLECTING
    cleaned = (correction or "").strip()
    if not cleaned:
        # Không nêu rõ chỗ sai -> hỏi lại cho rõ thay vì đoán bừa chỗ cần sửa.
        question = "Bạn cho mình biết thông tin nào chưa đúng và cần sửa lại thành gì nhé?"
        session.last_question = question
        session.conversation.append({"role": "assistant", "content": question})
        return session

    session.conversation.append({"role": "user", "content": cleaned})
    agent = _agent_for(session.checklist)
    extracted, llm_used = agent.extract_correction(cleaned, session.answers)
    session.answers.update(extracted)
    session.llm_used_last_turn = llm_used

    if is_complete_enough(session.checklist, session.answers):
        session.state = SessionState.AWAITING_CONFIRMATION
        session.last_question = ""
        return session

    question, _targets, question_llm_used = agent.next_question(session.conversation, session.answers)
    session.llm_used_last_turn = llm_used or question_llm_used
    session.last_question = question
    if question:
        session.conversation.append({"role": "assistant", "content": question})
    return session


def build_summary_text(session: DiseaseSession) -> str:
    return _agent_for(session.checklist).build_summary_text(session.answers)


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


def _require_session(session_id: str) -> DiseaseSession:
    session = session_store.get(session_id)
    if session is None:
        raise SessionNotFoundError("Không tìm thấy phiên hỏi-đáp.")
    return session
