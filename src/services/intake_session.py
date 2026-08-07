"""State machine cho phiên hỏi-đáp intake (demo).

Vòng đời một phiên:

    collecting ──(đủ >= COMPLETION_THRESHOLD trường bắt buộc)──> awaiting_confirmation
        ▲                                                                │
        └──────────(người bệnh bấm "Chưa đúng" + nêu chỗ cần sửa)────────┘
                                                                         │
                                       (người bệnh bấm "Đúng rồi")───────┴──> confirmed

Ghi chú phạm vi: phiên intake này CHỈ thu thập + tóm tắt + xin xác nhận của người bệnh. Nó KHÔNG
sinh mức độ ưu tiên, KHÔNG gửi cho điều dưỡng - phần đó thuộc luồng Gen2 (case_flow/case_approval)
và nằm ngoài phạm vi demo hiện tại theo yêu cầu.

Red-flag: được quét mỗi lượt bằng rule thuần (`intake_agent.scan_red_flags`) và tích luỹ vào phiên.
Khi có red-flag, phiên KHÔNG bị dừng - vẫn hỏi tiếp - nhưng cờ được trả về ngay để UI hiện cảnh báo
cấp cứu tức thì, đúng nguyên tắc "cảnh báo không chờ duyệt" ở đặc tả #4.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from src.services.intake_agent import RedFlagHit, intake_agent, scan_red_flags
from src.services.intake_checklist import (
    FIELDS_BY_KEY,
    INTAKE_CHECKLIST,
    REQUIRED_KEYS,
    completion_ratio,
    is_complete_enough,
    missing_required_keys,
)

# Chặn hỏi vô hạn khi người bệnh liên tục không cung cấp được trường còn thiếu: sau ngưỡng này,
# phiên chuyển sang xác nhận với các trường đã có và đánh dấu phần còn thiếu là "Chưa cung cấp".
MAX_TURNS_BEFORE_FORCE_SUMMARY = 12


class SessionState(str, Enum):
    COLLECTING = "collecting"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    CONFIRMED = "confirmed"


@dataclass(slots=True)
class IntakeSession:
    session_id: str = field(default_factory=lambda: str(uuid4()))
    state: SessionState = SessionState.COLLECTING
    answers: dict[str, str | None] = field(default_factory=dict)
    conversation: list[dict[str, str]] = field(default_factory=list)
    red_flags: list[RedFlagHit] = field(default_factory=list)
    turn_count: int = 0
    last_question: str = ""
    llm_used_last_turn: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def red_flag_codes(self) -> list[str]:
        return sorted({hit.code for hit in self.red_flags})

    def red_flag_labels(self) -> list[str]:
        seen: dict[str, None] = {}
        for hit in self.red_flags:
            seen.setdefault(hit.label, None)
        return list(seen)


class InMemoryIntakeSessionStore:
    """In-memory, mất khi restart process - đủ cho demo, giống InMemoryCaseStore hiện có."""

    def __init__(self) -> None:
        self._sessions: dict[str, IntakeSession] = {}

    def create(self) -> IntakeSession:
        session = IntakeSession()
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> IntakeSession | None:
        return self._sessions.get(session_id)


session_store = InMemoryIntakeSessionStore()


class SessionNotFoundError(ValueError):
    pass


class EmptyMessageError(ValueError):
    pass


OPENING_QUESTION = (
    "Chào bạn, mình là trợ lý thu thập thông tin ban đầu. "
    "Bạn cho mình biết tên người bệnh, tuổi và triệu chứng đang gặp phải nhé?"
)


def get_session(session_id: str) -> IntakeSession:
    """Đọc phiên theo id, raise SessionNotFoundError nếu không tồn tại."""
    return _require_session(session_id)


def start_session() -> IntakeSession:
    session = session_store.create()
    session.last_question = OPENING_QUESTION
    session.conversation.append({"role": "assistant", "content": OPENING_QUESTION})
    return session


def submit_message(session_id: str, message: str) -> IntakeSession:
    """Xử lý một lượt trả lời của người bệnh: quét red-flag -> trích xuất -> quyết định hỏi tiếp hay tóm tắt."""
    session = _require_session(session_id)
    cleaned = (message or "").strip()
    if not cleaned:
        raise EmptyMessageError("Nội dung tin nhắn không được để trống.")

    session.conversation.append({"role": "user", "content": cleaned})
    session.turn_count += 1

    # 1. Red-flag TRƯỚC trên text thô: rule thuần, chạy mọi lượt, không phụ thuộc LLM
    #    và không đợi checklist đủ. Chạy trước để nếu LLM lỗi thì red-flag vẫn được ghi nhận.
    session.red_flags.extend(scan_red_flags(cleaned))

    # 2. Trích xuất checklist bằng LLM (không ghi đè trường đã có).
    extracted, llm_used = intake_agent.extract(cleaned, session.answers)
    session.answers.update(extracted)
    session.llm_used_last_turn = llm_used

    # 3. Quét lại trên các field vừa trích xuất: LLM có thể chuẩn hoá cách viết
    #    (vd "li bi" -> "li bì", "met lam" -> "lơ mơ") khiến bản quét text thô ở bước 1 bỏ sót.
    if extracted:
        session.red_flags.extend(scan_red_flags(*extracted.values()))

    # 4. Đủ ngưỡng (hoặc đã hỏi quá nhiều lượt) -> chuyển sang xin xác nhận.
    if is_complete_enough(session.answers) or session.turn_count >= MAX_TURNS_BEFORE_FORCE_SUMMARY:
        session.state = SessionState.AWAITING_CONFIRMATION
        session.last_question = ""
        return session

    # 5. Chưa đủ -> sinh câu hỏi tiếp theo tự nhiên.
    question, _targets, question_llm_used = intake_agent.next_question(session.conversation, session.answers)
    session.llm_used_last_turn = llm_used or question_llm_used
    session.last_question = question
    if question:
        session.conversation.append({"role": "assistant", "content": question})
    return session


def confirm_summary(session_id: str, is_correct: bool, correction: str | None = None) -> IntakeSession:
    """Người bệnh xác nhận phiếu tóm tắt.

    is_correct=True  -> chốt phiên (CONFIRMED).
    is_correct=False -> quay lại thu thập; phần `correction` được xử lý như một lượt trả lời mới
                        (vẫn quét red-flag và trích xuất bình thường).
    """
    session = _require_session(session_id)
    if session.state == SessionState.COLLECTING:
        raise ValueError("Phiên chưa có phiếu tóm tắt để xác nhận.")

    if is_correct:
        session.state = SessionState.CONFIRMED
        session.last_question = ""
        session.conversation.append({"role": "user", "content": "[Người bệnh xác nhận phiếu tóm tắt là ĐÚNG]"})
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
    session.red_flags.extend(scan_red_flags(cleaned))

    # Ở bước sửa, người bệnh ĐANG chủ động đính chính -> dùng prompt riêng cho phép ghi đè,
    # nhưng chỉ với đúng những trường họ nhắc tới (xem IntakeAgent.extract_correction).
    extracted, llm_used = intake_agent.extract_correction(cleaned, session.answers)
    session.answers.update(extracted)
    session.llm_used_last_turn = llm_used
    if extracted:
        session.red_flags.extend(scan_red_flags(*extracted.values()))

    if is_complete_enough(session.answers):
        session.state = SessionState.AWAITING_CONFIRMATION
        session.last_question = ""
        return session

    question, _targets, question_llm_used = intake_agent.next_question(session.conversation, session.answers)
    session.llm_used_last_turn = llm_used or question_llm_used
    session.last_question = question
    if question:
        session.conversation.append({"role": "assistant", "content": question})
    return session


def build_summary_rows(session: IntakeSession) -> list[dict[str, object]]:
    """Phiếu tóm tắt dạng field-value. Trường chưa có -> is_missing=True, KHÔNG bịa giá trị."""
    rows: list[dict[str, object]] = []
    for item in INTAKE_CHECKLIST:
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


def progress_of(session: IntakeSession) -> dict[str, object]:
    missing = missing_required_keys(session.answers)
    return {
        "ratio": round(completion_ratio(session.answers), 4),
        "percent": round(completion_ratio(session.answers) * 100),
        "filled_required": len(REQUIRED_KEYS) - len(missing),
        "total_required": len(REQUIRED_KEYS),
        "missing_required_labels": [FIELDS_BY_KEY[key].label for key in missing],
    }


def _require_session(session_id: str) -> IntakeSession:
    session = session_store.get(session_id)
    if session is None:
        raise SessionNotFoundError("Không tìm thấy phiên hỏi-đáp.")
    return session
