"""Xác nhận tracing Braintrust im lặng trở thành no-op khi thiếu BRAINTRUST_API_KEY - KHÔNG được
làm crash app hay bất kỳ script eval/ nào (xem eval/config.py, src/observability/braintrust_tracing.py).
"""

from __future__ import annotations

from src.config import get_settings
from src.observability.braintrust_tracing import braintrust_enabled, traced_root_span, traced_span


def test_braintrust_disabled_when_key_absent(monkeypatch):
    monkeypatch.setenv("BRAINTRUST_API_KEY", "")
    get_settings.cache_clear()
    try:
        assert braintrust_enabled() is False
    finally:
        get_settings.cache_clear()


def test_traced_root_span_is_noop_without_key(monkeypatch):
    """Không có key -> không network call, không raise, trace_link luôn None."""
    monkeypatch.setenv("BRAINTRUST_API_KEY", "")
    get_settings.cache_clear()
    try:
        with traced_root_span("test_root", case_id="abc") as (span, trace_link):
            assert trace_link is None
            with span.start_span(name="child") as child:
                child.log(output={"ok": True})
    finally:
        get_settings.cache_clear()


def test_traced_span_is_noop_without_key(monkeypatch):
    monkeypatch.setenv("BRAINTRUST_API_KEY", "")
    get_settings.cache_clear()
    try:
        with traced_span("unit_x", input={"a": 1}) as span:
            span.log(output={"b": 2})
    finally:
        get_settings.cache_clear()


def test_decide_for_case_does_not_crash_without_braintrust_key(monkeypatch):
    """Track 2 (`graph_triage_service.decide_for_case`) phải trả về giá trị an toàn (None hoặc dict)
    khi không có BRAINTRUST_API_KEY - tracing không được là điều kiện tiên quyết để pipeline chạy."""
    monkeypatch.setenv("BRAINTRUST_API_KEY", "")
    monkeypatch.setenv("ENABLE_GRAPH_TRIAGE_AGENT", "false")
    get_settings.cache_clear()
    try:
        from src.graph_triage import service as graph_triage_service
        from src.models.schemas import TriageCase

        result = graph_triage_service.decide_for_case(TriageCase())
        assert result is None  # agent tắt (ENABLE_GRAPH_TRIAGE_AGENT=false) -> None, không raise.
    finally:
        get_settings.cache_clear()
