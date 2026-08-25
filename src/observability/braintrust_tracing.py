"""Wrapper an toàn quanh `braintrust.init_logger`/`start_span`, dùng để instrument cả 2 track
(`src/services/triage_pipeline.py` - Track 1, `src/graph_triage/service.py` + `src/source_support/`
- Track 2). Sống trong `src/` (không phải `eval/`) có chủ đích: code production (`TriagePipeline`,
`graph_triage_service`) không được phụ thuộc ngược vào package `eval/` - `eval/config.py` import
lại module này thay vì làm chiều ngược lại.

RÀNG BUỘC: BRAINTRUST_API_KEY là TUỲ CHỌN. Không có key thì mọi hàm dưới đây trả về no-op
context manager (không network call, không raise) để app/script chạy y hệt như không có
instrumentation nào — xem CLAUDE.md "HITL bắt buộc"/"best-effort" style của repo này, và
`docs/eval/00_PLAN.md`.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from src.config import get_settings

logger = logging.getLogger("vmedtriage.observability")

_auto_instrumented = False


def _ensure_auto_instrumented() -> None:
    """Bật `braintrust.auto_instrument()` một lần duy nhất (idempotent) để tự động tạo span cho
    các LLM call (OpenAI, LangChain, Gemini...) lồng bên trong root span hiện tại — thay cho việc
    tự tay wrap từng client trong `src/providers/`, `src/services/infra/llm.py`.
    """
    global _auto_instrumented
    if _auto_instrumented:
        return
    _auto_instrumented = True
    try:
        import braintrust

        braintrust.auto_instrument()
    except Exception as error:  # pragma: no cover - best-effort, không được làm sập luồng chính
        logger.warning("braintrust.auto_instrument_failed reason=%s: %s", type(error).__name__, error)


def braintrust_enabled() -> bool:
    """True nếu có BRAINTRUST_API_KEY. Dùng để quyết định nhánh log/no-op ở runner."""
    return bool(get_settings().braintrust_api_key.strip())


class _NoOpSpan:
    """Span giả — mọi method là no-op, dùng khi Braintrust chưa cấu hình."""

    def log(self, **_kwargs: Any) -> None:
        return None

    def start_span(self, *_args: Any, **_kwargs: Any) -> _NoOpSpan:
        return self

    def end(self) -> None:
        return None

    def __enter__(self) -> _NoOpSpan:
        return self

    def __exit__(self, *_exc: Any) -> None:
        return None

    @property
    def id(self) -> str:  # noqa: A003 - matches braintrust Span API surface
        return "noop"


@contextlib.contextmanager
def traced_span(name: str, **event: Any):
    """Context manager mở một span CON của span đang active trong context hiện tại (dùng
    `braintrust.start_span`, tự động parent theo contextvar - không cần truyền span object qua
    nhiều lớp hàm). Dùng bên trong `src/graph_triage/service.py` và `src/source_support/pipeline.py`
    để đánh dấu từng unit (A-E, xem docs/eval/01_evaluation_units.md) mà không phải sửa chữ ký hàm.

    No-op an toàn khi không có BRAINTRUST_API_KEY hoặc chưa có root span nào đang mở (ví dụ khi
    `decide_for_case` được gọi trực tiếp ngoài `traced_root_span`, như trong test) - `braintrust`
    tự trả về NOOP_SPAN trong trường hợp đó, nhưng ta còn kiểm tra riêng để tránh cả import khi
    chưa cấu hình key.
    """
    if not braintrust_enabled():
        yield _NoOpSpan()
        return
    try:
        import braintrust
    except ImportError:
        yield _NoOpSpan()
        return
    try:
        span = braintrust.start_span(name=name, **event)
    except Exception as error:
        # Chỉ bắt lỗi TẠO span ở đây. KHÔNG được bọc `yield` trong try/except Exception rộng: nếu
        # code bên trong `with traced_span(...) as span:` raise (vd DeepSeek 402), contextlib sẽ
        # throw() exception đó vào đúng dòng yield - bắt nó rồi yield lần nữa là vi phạm giao thức
        # generator ("RuntimeError: generator didn't stop after throw()"), nuốt mất lỗi gốc.
        logger.warning("braintrust.span_failed name=%s reason=%s: %s", name, type(error).__name__, error)
        yield _NoOpSpan()
        return
    with span:
        yield span


def traced_event(name: str, **event: Any) -> None:
    """Ghi một span TỨC THỜI (mở rồi đóng ngay) cho một sự kiện ĐIỂM - thứ không có khoảng thời gian
    để bọc, ví dụ `route_decided`, `rule_gate`, `agent_message` trong `fever_stage_log.step()`.

    Dùng span thay vì `current_span().log()` vì `log()` gộp dữ liệu vào ĐÚNG MỘT dòng của span cha:
    ghi 40 step của một lượt bằng `log()` thì 39 cái đầu bị đè mất. Mỗi step một span con là cách
    duy nhất giữ được đủ thứ tự lẫn nội dung của cả chuỗi.

    No-op an toàn khi chưa cấu hình key hoặc chưa có span cha nào đang mở (braintrust trả
    `NOOP_SPAN`). Không bao giờ raise - log hỏng không được làm hỏng lượt hỏi-đáp.
    """
    if not braintrust_enabled():
        return
    try:
        import braintrust

        braintrust.start_span(name=name, **event).end()
    except Exception as error:  # pragma: no cover - best-effort
        logger.warning("braintrust.event_failed name=%s reason=%s: %s", name, type(error).__name__, error)


def _has_active_span() -> bool:
    """True nếu đang có span thật đang mở trong context hiện tại.

    Dùng để `traced_root_span` tự biết nên mở ROOT hay nên lồng làm CON. `braintrust.current_span()`
    trả về `NOOP_SPAN` khi chưa có span nào - đó là dấu hiệu duy nhất phân biệt được hai trường hợp.
    """
    try:
        import braintrust

        return braintrust.current_span() is not braintrust.NOOP_SPAN
    except Exception:  # pragma: no cover - thiếu package/API đổi thì coi như không có cha
        return False


@contextlib.contextmanager
def traced_root_span(name: str, project: str | None = None, **metadata: Any):
    """Context manager mở một span cho `name`, TỰ CHỌN root hay con:

    - chưa có span nào đang mở  -> mở ROOT span mới qua `init_logger(...).start_span()`;
    - đã có span đang mở        -> lồng làm CON qua `braintrust.start_span()`.

    Vì sao phải tự chọn: `decide_for_case` (`src/graph_triage/service.py`) chạy ở HAI hoàn cảnh -
    trong một lượt `/chat` (đã có root `chat_turn` bọc ngoài) và trong background safety-gate task
    (đứng một mình). Nếu luôn gọi `init_logger().start_span()` thì ở hoàn cảnh thứ nhất phần graph
    bị TÁCH thành một trace riêng, xem trên Braintrust là hai trace rời không nối được với nhau,
    đúng thứ làm luồng E2E không đọc được. Còn nếu luôn `start_span()` thì ở hoàn cảnh thứ hai
    không có cha nào, braintrust trả `NOOP_SPAN` và toàn bộ nhánh im lặng biến mất.

    Nếu không có BRAINTRUST_API_KEY, trả về `_NoOpSpan` — không gọi network, không raise, để mọi
    runner/route gọi qua đây được an toàn trong mọi môi trường (kể cả CI không có key).

    Trả về `(span, trace_link)` — `trace_link` là `None` khi no-op.
    """
    settings = get_settings()
    project_name = project or settings.braintrust_project

    if not settings.braintrust_api_key.strip():
        logger.info("braintrust.disabled reason=no_api_key span=%s", name)
        yield _NoOpSpan(), None
        return

    try:
        import braintrust
    except ImportError:
        logger.warning("braintrust.disabled reason=package_not_installed span=%s", name)
        yield _NoOpSpan(), None
        return

    if _has_active_span():
        with traced_span(name, metadata=metadata) as child:
            link = None
            try:
                link = child.link()
            except Exception:  # pragma: no cover - link() có thể chưa sẵn tuỳ SDK version
                link = None
            yield child, link
        return

    try:
        # `braintrust.login()` PHẢI gọi tường minh trước `init_logger`: nếu không, `span.link()`
        # trả về URL lỗi "error-generating-link?msg=login-or-provide-org-name" vì org_name chưa kịp
        # resolve (login xảy ra lazy/async bên trong SDK, có thể chưa xong khi link() được gọi ngay
        # sau start_span). Xác nhận bằng test trực tiếp: cùng project/key, KHÔNG gọi login() trước
        # thì link lỗi; gọi login() trước thì ra đúng URL app.
        braintrust.login(api_key=settings.braintrust_api_key)
        logger_instance = braintrust.init_logger(
            project=project_name, api_key=settings.braintrust_api_key
        )
        _ensure_auto_instrumented()
        span = logger_instance.start_span(name=name, metadata=metadata)
    except Exception as error:  # Best-effort đúng tinh thần repo: tracing hỏng KHÔNG được làm
        # sập luồng chính (patient/nurse-facing). Log rồi rơi về no-op. Chỉ bắt lỗi TẠO span/logger
        # ở đây - xem ghi chú trong `traced_span` vì sao KHÔNG được bọc `yield` trong try/except này.
        logger.warning("braintrust.failed reason=%s: %s span=%s", type(error).__name__, error, name)
        yield _NoOpSpan(), None
        return
    trace_link = None
    try:
        trace_link = span.link()
    except Exception:  # pragma: no cover - link() có thể chưa sẵn tuỳ SDK version
        trace_link = None
    with span:
        yield span, trace_link
