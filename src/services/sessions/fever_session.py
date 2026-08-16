"""Lớp mỏng: fever "cắm" vào vòng đời phiên dùng chung (`src/services/symptom_protocol/session.py`)
qua `FEVER_PROTOCOL` (`src/services/engines/fever_protocol.py`).

Toàn bộ chữ ký hàm/tên module-level GIỮ NGUYÊN như bản fever-riêng trước khi tách generic engine
(xem `_guidance/fever-detect-agent-task.md`, mục "kế thừa được") - `src/api/routers/fever_intake.py`
và toàn bộ test Checkpoint 6 không cần sửa gì.

Muốn thêm symptom_group mới (vd chest_pain): viết `chest_pain_protocol.py` theo mẫu
`fever_protocol.py`, rồi tạo file session tương tự file này với
`store = ProtocolSessionStore(CHEST_PAIN_PROTOCOL)` - không cần viết lại vòng đời phiên.
"""

from __future__ import annotations

from src.services.engines.fever_protocol import FEVER_PROTOCOL
from src.services.sessions.symptom_session import session_store
from src.services.symptom_protocol.protocol import SymptomProtocol  # noqa: F401 - re-export cho type hint
from src.services.symptom_protocol.session import (
    EmptyMessageError,
    ProtocolSessionStore,  # noqa: F401 - re-export, caller cũ vẫn import từ đây
    SessionNotFoundError,
    SessionState,
)
from src.services.symptom_protocol.session import (
    Session as FeverSession,
)

__all__ = [
    "EmptyMessageError",
    "FeverSession",
    "SessionNotFoundError",
    "SessionState",
    "confirm_summary",
    "get_session",
    "session_store",
    "start_session",
    "submit_message",
]

def start_session(credential=None) -> FeverSession:
    """Mở phiên GHIM sẵn protocol sốt - endpoint này là lối vào chuyên biệt, caller đã tuyên bố đây
    là ca sốt nên không có lượt mở (không phải đoán protocol). Ô chat tự do đi đường khác, xem
    `symptom_session.py`."""
    return session_store.start_session(credential, protocol_name=FEVER_PROTOCOL.name)


def get_session(session_id: str) -> FeverSession:
    session = session_store.get(session_id)
    if session is None:
        raise SessionNotFoundError("Không tìm thấy phiên hỏi-đáp fever.")
    return session


def submit_message(session_id: str, message: str) -> FeverSession:
    return session_store.submit_message(session_id, message)


def confirm_summary(session_id: str, is_correct: bool) -> FeverSession:
    return session_store.confirm_summary(session_id, is_correct)
