"""In trace từng bước hỏi-đáp ra terminal cho dễ quan sát khi chạy server.

Khác `session_log.py` (ghi JSON xuống `logs/` để tra cứu sau), module này chỉ phục vụ QUAN SÁT
TRỰC TIẾP lúc dev: mỗi lượt một dòng, có màu, căn lề, đọc được ngay trong cửa sổ uvicorn.

Bật/tắt bằng `CONSOLE_TRACE` trong `.env`:

- `auto` (mặc định) - bật khi `APP_ENV` khác `production`
- `on` / `off` - ép bật hoặc tắt

⚠️ Trace in NGUYÊN VĂN hội thoại người bệnh (PHI). Không bật ở môi trường có dữ liệu thật.
API key thì không bao giờ được in - chỉ in tên provider/model và bản đã che.

Hai chi tiết môi trường phải xử lý, nếu không trace sẽ làm hỏng cả tiến trình trên Windows:

1. Console Windows mặc định cp1252, không encode được tiếng Việt lẫn ký tự khung `┌│└`. Ghi thẳng
   sẽ ném `UnicodeEncodeError` giữa request. Ta thử reconfigure stdout sang UTF-8; nếu không được
   thì tự chuyển sang bộ ký tự ASCII.
2. Khi output bị pipe/redirect (không phải TTY) thì bỏ màu, tránh rác escape code trong file log.
"""

from __future__ import annotations

import logging
import os
import sys

from src.config import get_settings

logger = logging.getLogger("vmedtriage.console")


def _stdout_supports_unicode() -> bool:
    """Thử ép stdout sang UTF-8; trả về False nếu console không nhận."""
    stream = sys.stdout
    encoding = (getattr(stream, "encoding", None) or "").lower()
    if "utf" in encoding:
        return True
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return False
    try:
        reconfigure(encoding="utf-8")
    except (ValueError, OSError):
        return False
    return True


_UNICODE_OK = _stdout_supports_unicode()
_COLOR_OK = sys.stdout.isatty() and os.getenv("NO_COLOR") is None

# Bộ ký tự khung: bản ASCII dùng khi console không hiển thị được Unicode.
if _UNICODE_OK:
    _TOP, _MID, _END, _ARROW, _DOT = "┌─", "│ ", "└─", "↳", "·"
    _MARK_OK, _MARK_WARN = "✓", "⚠"
else:
    _TOP, _MID, _END, _ARROW, _DOT = "+-", "| ", "+-", "->", "-"
    _MARK_OK, _MARK_WARN = "[OK]", "[!]"


class _Color:
    RESET = "\033[0m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    MAGENTA = "\033[35m"


def _paint(text: str, color: str) -> str:
    return f"{color}{text}{_Color.RESET}" if _COLOR_OK else text


# Ghi đè cấu hình theo tiến trình. CLI dùng cái này để tắt trace vì nó đã tự in giao diện riêng,
# bật cả hai sẽ ra hai bản của cùng một nội dung.
_override: bool | None = None


def set_enabled(value: bool | None) -> None:
    """Ép bật/tắt trace, `None` = quay lại theo cấu hình trong `.env`."""
    global _override
    _override = value


def enabled() -> bool:
    if _override is not None:
        return _override
    mode = get_settings().console_trace
    if mode == "on":
        return True
    if mode == "off":
        return False
    return get_settings().app_env != "production"


def _emit(line: str) -> None:
    """Ghi ra stdout. Nuốt mọi lỗi - trace hỏng KHÔNG được làm hỏng request."""
    try:
        print(line, flush=True)
    except Exception as exc:  # pragma: no cover - phụ thuộc console cụ thể
        logger.debug("console_trace.write_failed reason=%s", type(exc).__name__)


def _short(session_id: str) -> str:
    return session_id.split("-")[0]


def _clip(text: str, limit: int = 96) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def session_start(session_id: str, *, label: str, llm: str) -> None:
    if not enabled():
        return
    header = f"{_TOP} phiên {_short(session_id)} {_DOT} {label} {_DOT} {llm}"
    _emit("")
    _emit(_paint(header, _Color.BOLD + _Color.CYAN))


def llm_attempt(
    *,
    provider: str,
    model: str,
    ok: bool,
    latency_ms: int | None = None,
    note: str = "",
) -> None:
    """In provider + MODEL của từng lần gọi LLM, cả lần thành công lẫn lần bị bỏ qua.

    Không nhận `session_id` vì `provider_router` không biết phiên nào đang gọi - đổi lại, dòng này
    nằm ngay giữa các dòng của phiên đang chạy nên vẫn đọc được theo thứ tự thời gian.

    Vì sao phải in cả lần THẤT BẠI: router xoay vòng qua nhiều model free, nếu chỉ in lần cuối thì
    không thấy được model đầu danh sách đang hết quota - triệu chứng duy nhất là latency tăng.
    """
    if not enabled():
        return
    if ok:
        detail = f"{latency_ms}ms" if latency_ms is not None else ""
        body = f"{provider} {_DOT} {model}" + (f" {_DOT} {detail}" if detail else "")
        _emit(f"{_MID}   {_ARROW} {_paint('LLM  ' + body, _Color.DIM)}")
        return
    reason = note or "lỗi"
    _emit(f"{_MID}   {_ARROW} {_paint(f'LLM  {provider} {_DOT} {model} {_DOT} bỏ qua: {reason}', _Color.YELLOW)}")


def agent_question(session_id: str, question: str, *, llm_used: bool) -> None:
    if not enabled():
        return
    tag = "AGENT" if llm_used else "AGENT(mẫu)"
    _emit(f"{_MID}{_paint(tag.ljust(11), _Color.CYAN)} {_clip(question)}")


def user_message(session_id: str, message: str, *, turn: int) -> None:
    if not enabled():
        return
    _emit(f"{_MID}{_paint(f'USER #{turn}'.ljust(11), _Color.MAGENTA)} {_clip(message)}")


def extraction(session_id: str, extracted: dict, *, percent: int, filled: int, total: int) -> None:
    if not enabled():
        return
    fields = ", ".join(f"{key}={_clip(str(value), 32)!r}" for key, value in extracted.items()) or "(không trích được gì)"
    progress = _paint(f"[{percent}% {_DOT} {filled}/{total}]", _Color.DIM)
    _emit(f"{_MID}   {_ARROW} {fields}  {progress}")


def red_flag(session_id: str, labels: list[str]) -> None:
    if not enabled() or not labels:
        return
    _emit(f"{_MID}   {_paint(f'{_MARK_WARN} RED-FLAG: ' + ' / '.join(labels), _Color.RED + _Color.BOLD)}")


def summary(session_id: str, kind: str, *, percent: int) -> None:
    if not enabled():
        return
    _emit(f"{_MID}   {_paint(f'phiếu tóm tắt [{kind}] {_DOT} {percent}%', _Color.YELLOW)}")


def session_end(session_id: str, *, state: str, turns: int, percent: int) -> None:
    if not enabled():
        return
    mark = _MARK_OK if state == "confirmed" else _MARK_WARN
    color = _Color.GREEN if state == "confirmed" else _Color.YELLOW
    _emit(_paint(f"{_END} {mark} {state} {_DOT} {percent}% {_DOT} {turns} lượt", color))
    _emit("")
