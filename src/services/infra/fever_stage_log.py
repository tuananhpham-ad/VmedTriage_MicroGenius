"""Trace toàn bộ inference của agent hội thoại triệu chứng (`symptom_protocol`), tách theo stage, ra
`logs/<namespace>/<session_id>/` - `namespace` mặc định `"fever"` nhưng bất kỳ symptom_group nào cắm
vào engine chung đều tự có thư mục log riêng (truyền `namespace=` cho `start()`).

Module này phục vụ các agent hội thoại theo cụm câu hỏi (xem `_guidance/fever-detect-agent-task.md`
§5 - lúc đầu viết riêng cho fever, sau tách chung khi thêm symptom_group thứ 2): mỗi lượt người dùng
nhắn sinh ra một chuỗi
step - user nói gì, hệ thống `retrieve` cụm/field nào, gọi tool nào với input/output gì, gọi LLM với
prompt/response gì, rule engine quyết định gì, agent trả lời gì. Ghi APPEND (JSONL) thay vì ghi đè cả
file, vì log ở đây được đọc theo kiểu "đếm dòng / grep một stage / xem đúng thứ
tự step" ngay cả khi phiên đang chạy dở, và mỗi dòng là JSON độc lập nên process chết giữa chừng chỉ
mất đúng dòng cuối.

Bố cục `logs/<namespace>/<session_id>/`:
    session.json        - snapshot phiên (ghi đè cả file mỗi lần cập nhật)
    stage-<STAGE>.jsonl  - mọi step của mọi lượt diễn ra khi đang ở stage đó
    llm-io.jsonl         - nguyên văn prompt gửi LLM + nguyên văn response (tách khỏi file stage vì
                           quá dài, dòng stage chỉ giữ `io_ref` trỏ sang)
    rule-engine.jsonl    - phụ dòng `tool_call` của rule engine (xem `_RULE_ENGINE_TOOLS`) từ file
                           stage, để dễ grep riêng kết quả rule engine qua mọi stage

CẢNH BÁO PHI: `user_message`/`agent_message`/nội dung `llm-io.jsonl` chứa nguyên văn hội thoại người
bệnh. `logs/` đã nằm trong `.gitignore`. Đặt `FEVER_LOG_REDACT=1` để thay các trường văn bản tự do
bằng `{"len": ..., "sha256_8": ...}` khi demo/chạy trên dữ liệu thật.

Ghi log KHÔNG được làm hỏng phiên hỏi-đáp: mọi lỗi I/O đều nuốt và chỉ `logger.warning`.

BRAINTRUST: mỗi step/llm_io/tool ghi xuống JSONL cũng được PHẢN CHIẾU thành một span con của span
đang mở (`chat_turn`, mở ở `src/api/routes.py`). Đặt mirror ở đây thay vì rắc `traced_span` vào
`symptom_protocol/session.py` + `intake_agent.py` vì hai lý do: ~40 điểm log của một lượt nằm rải ở
hai module đó, và hai hệ thống log MÔ TẢ CÙNG những cột mốc - tách ra là tự tạo chỗ cho chúng lệch
nhau. Mọi protocol cắm vào engine chung tự có trace mà không phải sửa gì thêm. Không có
BRAINTRUST_API_KEY thì toàn bộ phần mirror là no-op. Payload mirror dùng lại bản ĐÃ REDACT, nên
`FEVER_LOG_REDACT=1` che PHI ở cả hai đích.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from src import paths
from src.observability.braintrust_tracing import traced_event, traced_span

logger = logging.getLogger("vmedtriage.fever_stage_log")

_DEFAULT_NAMESPACE = "fever"
_session_namespace: dict[str, str] = {}


def _namespace_log_dir(namespace: str) -> Path:
    """Tính lại mỗi lần gọi (không cache ở module scope) để test monkeypatch `paths.LOGS_DIR` được."""
    return paths.LOGS_DIR / namespace

EventType = Literal[
    "stage_enter",
    "user_message",
    "retrieve",
    "tool_call",
    "llm_request",
    "llm_response",
    "extract",
    "screen",
    "screen_reject",
    "rule_gate",
    "route_decided",
    "agent_message",
    "stop",
    "stage_exit",
]

EVENT_TYPES: frozenset[str] = frozenset(
    (
        "stage_enter",
        "user_message",
        "retrieve",
        "tool_call",
        "llm_request",
        "llm_response",
        "extract",
        # Lượt sàng lọc theo nhóm cơ quan (`symptom_protocol/screening.py`): `screen` ghi verdict của
        # từng nhóm, `screen_reject` ghi nhóm bị TỪ CHỐI phủ định vì model không trích được câu nào
        # trong tin nhắn. Tách khỏi `extract` vì đây là lớp quyết định "đóng cả nhóm cụm hay không" -
        # khi cần lần lại "vì sao ca này không bị hỏi về xuất huyết", đó là dòng phải grep đầu tiên.
        "screen",
        "screen_reject",
        "rule_gate",
        "route_decided",
        "agent_message",
        "stop",
        "stage_exit",
    )
)

ToolName = str

# Tool nào được PHỤ thêm vào `rule-engine.jsonl`. Phải liệt kê cả hai tên vì có HAI engine cùng tồn
# tại: `red_flag_engine.evaluate` (engine fever cũ, `fever_red_flag_engine.py`) và
# `rule_engine.evaluate` (engine dùng chung của `symptom_protocol/`, đường mà `/chat` đang chạy).
# Trước đây điều kiện chỉ khớp tên cũ nên `rule-engine.jsonl` KHÔNG BAO GIỜ được ghi cho đường agent
# mới - file luôn rỗng dù rule engine chạy mỗi lượt.
_RULE_ENGINE_TOOLS: frozenset[str] = frozenset({"red_flag_engine.evaluate", "rule_engine.evaluate"})
"""Tên tool dạng `"<module>.<method>"` (vd `"rule_engine.evaluate"`, `"stage_machine.next_cluster"`).
Không còn là enum đóng theo từng symptom_group cụ thể - `_validate_tool_name` chỉ kiểm ĐỊNH DẠNG,
không kiểm danh sách cứng, để mọi protocol cắm vào engine chung (`symptom_protocol/`) đều dùng được
mà không phải sửa module log này."""

_TOOL_NAME_RE = re.compile(r"^[a-zA-Z_][\w]*\.[a-zA-Z_][\w]*$")


def _validate_tool_name(tool: str) -> bool:
    return bool(_TOOL_NAME_RE.match(tool))

_REDACT_ENV_VAR = "FEVER_LOG_REDACT"

# Trường được coi là "văn bản tự do có thể chứa PHI" - bị redact khi FEVER_LOG_REDACT=1.
_FREE_TEXT_KEYS = frozenset({"user_message", "agent_message", "text", "response_text", "content"})

_lock = threading.Lock()
_seq_counters: dict[str, int] = {}
_session_meta: dict[str, dict[str, Any]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact_enabled() -> bool:
    """Biến môi trường THẬT trước, rồi mới tới `Settings` (đọc được cả `.env`).

    Thứ tự này để `FEVER_LOG_REDACT=1 python -m scripts.xxx` bật được cho đúng một lần chạy mà
    không phải sửa file. Nhánh `Settings` là nhánh vá lỗi hỏng câm: pydantic-settings KHÔNG ghi
    `.env` vào `os.environ`, nên bản chỉ-`os.getenv` khiến cờ đặt trong `.env` im lặng không có tác
    dụng - xem `Settings.fever_log_redact`.
    """
    raw = os.getenv(_REDACT_ENV_VAR, "").strip()
    if raw:
        return raw == "1"
    from src.config import get_settings

    return bool(get_settings().fever_log_redact)


def _redact_value(value: str) -> dict[str, Any]:
    return {"len": len(value), "sha256_8": hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]}


def _redact_payload(payload: Any) -> Any:
    """Duyệt đệ quy, thay các khoá văn bản tự do bằng bản redact khi bật cờ."""
    if isinstance(payload, dict):
        result: dict[str, Any] = {}
        for key, value in payload.items():
            if key in _FREE_TEXT_KEYS and isinstance(value, str):
                result[key] = _redact_value(value)
            else:
                result[key] = _redact_payload(value)
        return result
    if isinstance(payload, list):
        return [_redact_payload(item) for item in payload]
    return payload


def session_dir(session_id: str) -> Path:
    namespace = _session_namespace.get(session_id, _DEFAULT_NAMESPACE)
    return _namespace_log_dir(namespace) / session_id


def _stage_path(session_id: str, stage: str) -> Path:
    return session_dir(session_id) / f"stage-{stage}.jsonl"


def _llm_io_path(session_id: str) -> Path:
    return session_dir(session_id) / "llm-io.jsonl"


def _rule_engine_path(session_id: str) -> Path:
    return session_dir(session_id) / "rule-engine.jsonl"


def _session_json_path(session_id: str) -> Path:
    return session_dir(session_id) / "session.json"


def _next_seq(session_id: str) -> int:
    _seq_counters[session_id] = _seq_counters.get(session_id, 0) + 1
    return _seq_counters[session_id]


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    """Ghi thêm 1 dòng JSON. Mọi lỗi I/O nuốt và chỉ cảnh báo - log hỏng không được hỏng phiên."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("fever_stage_log.write_failed path=%s reason=%s", path, type(exc).__name__)


def _write_json(path: Path, record: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("fever_stage_log.write_failed path=%s reason=%s", path, type(exc).__name__)


def start(session_id: str, *, route: str | None, budget: int, namespace: str = _DEFAULT_NAMESPACE) -> None:
    """Khởi tạo snapshot phiên. Gọi 1 lần khi phiên bắt đầu. `namespace` quyết định thư mục
    `logs/<namespace>/` - mỗi symptom_group (fever, chest_pain, ...) nên dùng namespace riêng."""
    with _lock:
        _session_namespace[session_id] = namespace
        _seq_counters[session_id] = 0
        meta = {
            "session_id": session_id,
            "route": route,
            "budget": budget,
            "created_at": _now(),
            "updated_at": _now(),
            "stages_seen": [],
            "turns": 0,
            "triage_level": None,
            "stop_reason": None,
        }
        _session_meta[session_id] = meta
        _write_json(_session_json_path(session_id), meta)


def adopt(session_id: str, *, fallback_namespace: str = _DEFAULT_NAMESPACE) -> None:
    """Nhận lại một phiên đã có log trên đĩa nhưng KHÔNG có trong tiến trình này.

    `_session_namespace`/`_session_meta` là dict trong RAM, chỉ được điền bởi `start()` - tức chỉ ở
    lượt phiên được TẠO. Nhưng từ M1 một phiên đang dở sống được qua restart: tiến trình mới khôi
    phục nó từ kho bền rồi ghi tiếp, lúc đó không dict nào biết gì về nó nữa. Hệ quả đã quan sát
    được trong `logs/`: các step còn lại của phiên rơi vào namespace mặc định (`logs/fever/<sid>/`
    chỉ có mỗi `stage-SUMMARY.jsonl`, không `session.json`) trong khi nửa đầu nằm ở
    `logs/general/<sid>/` - một luồng hội thoại bị chẻ đôi thành hai thư mục không nối được.

    Tìm namespace bằng cách soi đĩa chứ không đoán: thư mục nào chứa `<sid>/session.json` thì đó là
    namespace phiên đã dùng lúc `start()`. Không tìm thấy (log đã bị xoá) thì dùng `fallback` và mở
    sổ mới - mất nửa đầu vẫn hơn ghi nhầm chỗ.

    Idempotent: đã biết phiên rồi thì không làm gì, nên gọi ở mọi lượt `get()` cũng không tốn I/O.
    """
    with _lock:
        if session_id in _session_namespace:
            return
        namespace = fallback_namespace
        meta: dict[str, Any] | None = None
        try:
            for candidate in sorted(paths.LOGS_DIR.glob(f"*/{session_id}/session.json")):
                namespace = candidate.parent.parent.name
                meta = json.loads(candidate.read_text(encoding="utf-8"))
                break
        except (OSError, ValueError) as error:  # log hỏng KHÔNG được chặn lượt người bệnh
            logger.warning("fever_stage_log.adopt_failed session_id=%s: %s", session_id, error)
            meta = None
        _session_namespace[session_id] = namespace
        if meta is not None:
            _session_meta[session_id] = meta
            # `seq` phải tiếp tục từ số cũ, không quay về 0: đọc log theo `seq` mà có hai lần số 1
            # thì thứ tự các bước sau restart không dựng lại được.
            _seq_counters[session_id] = max(_seq_counters.get(session_id, 0), _max_seq_on_disk(session_id))


def _max_seq_on_disk(session_id: str) -> int:
    """`seq` lớn nhất đã ghi cho phiên, để `adopt` nối tiếp đúng chỗ. 0 nếu chưa có gì đọc được."""
    highest = 0
    try:
        for path in session_dir(session_id).glob("*.jsonl"):
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    highest = max(highest, int(json.loads(line).get("seq", 0)))
                except (ValueError, AttributeError):
                    continue
    except OSError:
        return highest
    return highest


def _span_name(stage: str, event: str) -> str:
    """`"<stage>.<event>"` để cây span trên Braintrust đọc được theo đúng thứ tự stage của phiên.
    Stage rỗng (lượt mở, chưa chọn protocol) thì rơi về mỗi tên event."""
    return f"{stage}.{event}" if stage else event


def _span_metadata(record: dict[str, Any]) -> dict[str, Any]:
    """Những trường dùng để LỌC trên Braintrust. Không nhét cả `record` vào metadata: `input`/`output`
    đã là cột riêng của span, lặp lại chỉ làm dòng nặng gấp đôi."""
    return {
        key: record.get(key)
        for key in ("seq", "session_id", "turn", "step", "stage", "cluster_id", "event", "tool", "io_ref")
        if record.get(key) is not None
    }


def stage_enter(session_id: str, stage: str) -> None:
    with _lock:
        meta = _session_meta.get(session_id)
        if meta is not None and stage not in meta["stages_seen"]:
            meta["stages_seen"].append(stage)
            meta["updated_at"] = _now()
            _write_json(_session_json_path(session_id), meta)
    step(session_id, turn=0, stage=stage, cluster_id=None, event="stage_enter")


def step(
    session_id: str,
    *,
    turn: int,
    stage: str,
    cluster_id: str | None,
    event: EventType,
    tool: ToolName | None = None,
    input: Any = None,  # noqa: A002 - tên khớp API §5.5 của spec
    output: Any = None,
    duration_ms: int | None = None,
    error: str | None = None,
    **extra: Any,
) -> None:
    """Ghi một step vào `stage-<stage>.jsonl` và phản chiếu thành một span con trên Braintrust.

    `_braintrust_mirror=False`: bỏ qua phần span, dành cho những chỗ ĐÃ tự mở span giàu dữ liệu hơn
    cho đúng sự kiện đó (`llm_io`, `tool`) - nếu không sẽ có hai span cho một lời gọi.
    """
    mirror = extra.pop("_braintrust_mirror", True)
    if event not in EVENT_TYPES:
        raise ValueError(f"event không hợp lệ: {event!r}")
    if tool is not None and not _validate_tool_name(tool):
        raise ValueError(f"tool không hợp lệ (cần dạng 'module.method'): {tool!r}")

    with _lock:
        seq = _next_seq(session_id)
        record: dict[str, Any] = {
            "seq": seq,
            "at": _now(),
            "session_id": session_id,
            "turn": turn,
            "step": extra.pop("step", None),
            "stage": stage,
            "cluster_id": cluster_id,
            "event": event,
            "tool": tool,
            "input": input,
            "output": output,
            "duration_ms": duration_ms,
            "error": error,
            "io_ref": extra.pop("io_ref", None),
        }
        record.update(extra)
        if _redact_enabled():
            record = _redact_payload(record)
        _append_jsonl(_stage_path(session_id, stage), record)
        if tool in _RULE_ENGINE_TOOLS:
            _append_jsonl(_rule_engine_path(session_id), record)

    # NGOÀI `_lock`: `traced_event` chỉ đụng contextvar + buffer của braintrust, giữ khoá qua nó là
    # bắt mọi lượt song song xếp hàng sau một việc chẳng liên quan gì tới file.
    if mirror:
        traced_event(
            _span_name(stage, event),
            input=record.get("input"),
            output=record.get("output"),
            metadata=_span_metadata(record),
        )


def llm_io(
    session_id: str,
    *,
    turn: int,
    stage: str,
    cluster_id: str,
    purpose: str,
    provider: str,
    model: str,
    messages: list[dict[str, str]],
    response_text: str,
    parsed: dict[str, Any] | None,
    tokens: int | None,
    latency_ms: int,
    retry_count: int = 0,
    parse_error: str | None = None,
) -> str:
    """Ghi nguyên văn prompt/response vào `llm-io.jsonl`, và cặp `llm_request`/`llm_response` tóm tắt
    vào file stage. Trả về `io_ref` để tra ngược nguyên văn từ dòng stage."""
    io_ref = f"{session_id}:{_next_seq(session_id)}"
    with _lock:
        io_record: dict[str, Any] = {
            "io_ref": io_ref,
            "at": _now(),
            "session_id": session_id,
            "turn": turn,
            "stage": stage,
            "cluster_id": cluster_id,
            "purpose": purpose,
            "provider": provider,
            "model": model,
            "messages": messages,
            "response_text": response_text,
        }
        if _redact_enabled():
            io_record = _redact_payload(io_record)
        _append_jsonl(_llm_io_path(session_id), io_record)

    # Một span DUY NHẤT cho cả lời gọi, mang nguyên văn prompt + response. Cặp `llm_request`/
    # `llm_response` bên dưới bị tắt mirror: trên JSONL chúng là hai dòng tóm tắt trỏ sang
    # `llm-io.jsonl`, còn trên Braintrust input/output đã nằm ngay trong span này nên hai dòng đó
    # chỉ còn là nhiễu.
    traced_event(
        f"{stage}.llm.{purpose}" if stage else f"llm.{purpose}",
        input=io_record.get("messages"),
        output=io_record.get("response_text"),
        metadata={
            "io_ref": io_ref,
            "session_id": session_id,
            "turn": turn,
            "stage": stage,
            "cluster_id": cluster_id,
            "purpose": purpose,
            "provider": provider,
            "model": model,
            "tokens": tokens,
            "latency_ms": latency_ms,
            "retry_count": retry_count,
            "parse_error": parse_error,
            "parsed": parsed,
        },
    )

    step(
        session_id,
        turn=turn,
        stage=stage,
        cluster_id=cluster_id,
        event="llm_request",
        input={"purpose": purpose, "provider": provider, "model": model},
        output=None,
        io_ref=io_ref,
        _braintrust_mirror=False,
    )
    step(
        session_id,
        turn=turn,
        stage=stage,
        cluster_id=cluster_id,
        event="llm_response",
        input=None,
        output={"parsed": parsed, "tokens": tokens},
        duration_ms=latency_ms,
        error=parse_error,
        io_ref=io_ref,
        retry_count=retry_count,
        _braintrust_mirror=False,
    )
    return io_ref


def finish(
    session_id: str, *, triage_level: str, stop_reason: str, turns: int,
    metrics: dict[str, Any] | None = None,
) -> None:
    """`metrics`: bản chụp §12 của phiên (`ProtocolSessionStore.metrics_summary`).

    Ghi vào chính file meta của phiên thay vì một kho riêng: dashboard của §9 P4.4 dựng được bằng
    cách đọc thư mục log, không cần thêm hạ tầng. Tuỳ chọn vì `finish` còn được gọi từ nhánh cấp cứu
    ở `intake_agent`, nơi chưa có `Session` trong tay - thiếu số liệu tốt hơn là chặn đường escalate."""
    with _lock:
        meta = _session_meta.get(session_id)
        if meta is None:
            return
        meta["triage_level"] = triage_level
        meta["stop_reason"] = stop_reason
        meta["turns"] = turns
        if metrics is not None:
            meta["metrics"] = metrics
        meta["updated_at"] = _now()
        _write_json(_session_json_path(session_id), meta)


@dataclass(slots=True)
class _ToolRecord:
    output: Any = None
    error: str | None = None


@contextmanager
def tool(
    session_id: str,
    *,
    turn: int,
    stage: str,
    cluster_id: str | None,
    tool: ToolName,  # noqa: A002
    input: Any = None,  # noqa: A002
):
    """Context manager cho 1 tool call: đo giờ tự động, ghi `tool_call` kể cả khi tool ném lỗi.

    Usage::

        with fever_stage_log.tool(sid, turn=t, stage=s, cluster_id=c,
                                   tool="red_flag_engine.evaluate", input=answers) as rec:
            result = red_flag_engine.evaluate(answers)
            rec.output = result.model_dump()
    """
    rec = _ToolRecord()
    started = time.monotonic()
    # Span THẬT bọc trọn lời gọi (không phải span tức thời như `step`) để trên Braintrust tool call
    # có thanh thời gian đúng bằng thời gian nó thực sự chạy - đó là thứ chỉ ra được nhánh nào đang
    # làm chậm một lượt. Vì vậy `step` bên dưới tắt mirror, tránh hai span cho một lời gọi.
    span_metadata = {"session_id": session_id, "turn": turn, "stage": stage, "cluster_id": cluster_id}
    try:
        with traced_span(f"tool.{tool}", input=input, metadata=span_metadata) as span:
            try:
                yield rec
            except Exception as exc:
                rec.error = f"{type(exc).__name__}: {exc}"
                raise
            finally:
                span.log(output=rec.output, error=rec.error)
    finally:
        duration_ms = int((time.monotonic() - started) * 1000)
        step(
            session_id,
            turn=turn,
            stage=stage,
            cluster_id=cluster_id,
            event="tool_call",
            tool=tool,
            input=input,
            output=rec.output,
            duration_ms=duration_ms,
            error=rec.error,
            _braintrust_mirror=False,
        )


def read_stage(session_id: str, stage: str) -> list[dict[str, Any]]:
    """Đọc mọi dòng của 1 stage. Dành cho test/debug, không dùng trong luồng chạy thật."""
    path = _stage_path(session_id, stage)
    if not path.exists():
        return []
    return _read_jsonl(path)


def read_llm_io(session_id: str) -> list[dict[str, Any]]:
    return _read_jsonl(_llm_io_path(session_id))


def read_turn(session_id: str, turn: int) -> list[dict[str, Any]]:
    """Gộp mọi stage, lọc đúng 1 lượt. `seq` là thứ tự ghi thật, luôn tăng dần - dùng nó để sort
    thay vì `step` vì không phải mọi event đều được caller gán `step` tường minh (vd cặp
    llm_request/llm_response do `llm_io()` tự sinh)."""
    records = [record for record in read_all(session_id) if record.get("turn") == turn]
    records.sort(key=lambda record: record["seq"])
    return records


def read_all(session_id: str) -> list[dict[str, Any]]:
    """Gộp mọi file `stage-*.jsonl` của phiên, sort theo `seq`."""
    directory = session_dir(session_id)
    if not directory.exists():
        return []
    records: list[dict[str, Any]] = []
    for path in directory.glob("stage-*.jsonl"):
        records.extend(_read_jsonl(path))
    records.sort(key=lambda record: record["seq"])
    return records


def read_session(session_id: str) -> dict[str, Any] | None:
    path = _session_json_path(session_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("fever_stage_log.read_failed session=%s reason=%s", session_id, type(exc).__name__)
        return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        logger.warning("fever_stage_log.read_failed path=%s reason=%s", path, type(exc).__name__)
        return []
    records: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            logger.warning("fever_stage_log.parse_failed path=%s reason=%s", path, type(exc).__name__)
    return records
