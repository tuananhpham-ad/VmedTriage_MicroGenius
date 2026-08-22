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


@contextlib.contextmanager
def traced_root_span(name: str, project: str | None = None, **metadata: Any):
    """Context manager mở một root span cho `name`. Nếu không có BRAINTRUST_API_KEY, trả về
    `_NoOpSpan` — không gọi network, không raise, để mọi runner/route gọi qua đây được an toàn
    trong mọi môi trường (kể cả CI không có key).

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
