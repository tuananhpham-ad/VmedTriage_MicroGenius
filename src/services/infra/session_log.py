"""Ghi log từng bước của phiên hỏi-đáp ra `logs/<session_id>.json` để tra cứu/kiểm toán.

Mỗi phiên một file, tên file là session_id (vd `logs/11566e1f-fb8d-440e-ad73-4bcb714778da.json`).

Nội dung lưu:

- `events`: trace tuần tự MỌI bước - câu hỏi của system, câu trả lời của user, kết quả trích xuất
  của LLM, tiến độ checklist sau mỗi lượt.
- `summaries`: TẤT CẢ phiên bản phiếu tóm tắt, gồm bản sinh lần đầu (`generated`), các bản sau khi
  người dùng đính chính (`revised`) và bản người dùng bấm xác nhận để gửi (`confirmed`). Giữ đủ các
  bản để tra được người dùng đã sửa gì, chứ không chỉ giữ bản cuối.
- `answers`: snapshot giá trị checklist tại thời điểm ghi cuối cùng.

Cách ghi: giữ toàn bộ log của phiên trong bộ nhớ rồi **ghi đè cả file** sau mỗi sự kiện. Đổi lại một
chút chi phí I/O, file luôn là JSON hợp lệ kể cả khi process bị kill giữa chừng (khác với cách append
từng dòng vào file JSON, dễ để lại file hỏng).

CẢNH BÁO PHI: file log chứa nguyên văn hội thoại của người bệnh. `logs/` đã nằm trong `.gitignore`;
trước khi dùng thật cần bổ sung mã hoá at-rest, phân quyền truy cập và chính sách xoá theo hạn.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("vmedtriage.session_log")

LOG_DIR = Path(__file__).resolve().parents[2] / "logs"

# Ghi log KHÔNG được làm hỏng phiên hỏi-đáp: mọi lỗi I/O đều nuốt và chỉ cảnh báo.
# Một lock đủ cho mọi phiên vì thao tác ghi rất ngắn.
_lock = threading.Lock()
_logs: dict[str, dict[str, Any]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_path(session_id: str) -> Path:
    return LOG_DIR / f"{session_id}.json"


def start(session_id: str, *, disease_id: str, disease_label: str, threshold: float, fields: list[dict]) -> None:
    """Khởi tạo log cho một phiên mới và ghi file lần đầu."""
    with _lock:
        _logs[session_id] = {
            "session_id": session_id,
            "disease_id": disease_id,
            "disease_label": disease_label,
            "completion_threshold": threshold,
            "checklist_fields": fields,
            "created_at": _now(),
            "updated_at": _now(),
            "final_state": "collecting",
            "answers": {},
            "summaries": [],
            "events": [],
        }
        _flush(session_id)


def event(session_id: str, event_type: str, **payload: Any) -> None:
    """Ghi một sự kiện vào trace. Bỏ qua nếu phiên chưa được `start` (vd phiên tạo trước khi bật log)."""
    with _lock:
        record = _logs.get(session_id)
        if record is None:
            return
        record["events"].append({"seq": len(record["events"]) + 1, "at": _now(), "type": event_type, **payload})
        record["updated_at"] = _now()
        _flush(session_id)


def summary(session_id: str, kind: str, *, text: str, rows: list[dict], answers: dict[str, str | None]) -> None:
    """Lưu một phiên bản phiếu tóm tắt.

    `kind`: "generated" (sinh lần đầu khi đủ ngưỡng) | "revised" (sau khi người dùng đính chính)
            | "confirmed" (người dùng bấm xác nhận để gửi).
    """
    with _lock:
        record = _logs.get(session_id)
        if record is None:
            return
        record["summaries"].append(
            {
                "seq": len(record["summaries"]) + 1,
                "at": _now(),
                "kind": kind,
                "text": text,
                "rows": rows,
                "answers": dict(answers),
            }
        )
        record["updated_at"] = _now()
        _flush(session_id)


def update_state(session_id: str, state: str, answers: dict[str, str | None]) -> None:
    with _lock:
        record = _logs.get(session_id)
        if record is None:
            return
        record["final_state"] = state
        record["answers"] = dict(answers)
        record["updated_at"] = _now()
        _flush(session_id)


def read(session_id: str) -> dict[str, Any] | None:
    """Đọc log của phiên - ưu tiên bản trong bộ nhớ, không có thì đọc từ file."""
    record = _logs.get(session_id)
    if record is not None:
        return record
    path = log_path(session_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("session_log.read_failed session=%s reason=%s", session_id, type(exc).__name__)
        return None


def _flush(session_id: str) -> None:
    """Ghi đè cả file. Gọi trong `_lock`."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = log_path(session_id)
        path.write_text(
            json.dumps(_logs[session_id], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("session_log.write_failed session=%s reason=%s", session_id, type(exc).__name__)
