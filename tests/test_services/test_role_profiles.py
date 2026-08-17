"""Định tuyến provider theo VAI TRÒ (`provider_router.RoleProfile`, §7.3).

Điều quan trọng nhất ở phase này KHÔNG phải là "đổi được thứ tự" mà là "cài vào không đổi hành vi
gì": mọi vai trò chưa cấu hình đều kế thừa `llm_provider_order` toàn cục. Hạ tầng định tuyến phải
đứng sẵn trước khi có số liệu latency/chi phí, chứ không được tự nó thay đổi provider nào đang chạy.

Ràng buộc thứ hai, dễ làm sai nhất: `LLMCredential` (key người dùng, CỐ Ý tắt fallback) không được
tái dụng để ghim model theo vai trò - làm vậy sẽ khiến mọi vai trò mất khả năng fallback.
"""

from __future__ import annotations

import pytest

from src.config import Settings
from src.services.infra import provider_router


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeProvider:
    def __init__(self, calls: list[str], name: str) -> None:
        self._calls = calls
        self._name = name

    def complete(self, messages, tools=None, *, model=None, temperature=0.0, tool_choice=None):
        self._calls.append(self._name)
        return _FakeResponse(f"trả lời từ {self._name}")


@pytest.fixture
def two_providers(monkeypatch):
    """Hai provider đều có key dùng được ⇒ thứ tự là thứ QUYẾT ĐỊNH provider nào được gọi."""
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPEN_ROUTER_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-deepseek-1234567890")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai-1234567890")

    settings = Settings(
        _env_file=None,
        llm_provider="auto",
        llm_provider_order="deepseek,openai",
        deepseek_api_key="sk-test-deepseek-1234567890",
        openai_api_key="sk-test-openai-1234567890",
        anthropic_api_key="",
        openrouter_api_key="",
    )
    monkeypatch.setattr(provider_router, "get_settings", lambda: settings)
    monkeypatch.setattr("src.config.get_settings", lambda: settings)
    provider_router.reset_role_usage()
    return settings


@pytest.fixture
def calls(monkeypatch) -> list[str]:
    recorded: list[str] = []
    monkeypatch.setattr(
        provider_router, "_build_provider",
        lambda spec, model=None: _FakeProvider(recorded, spec.name),
    )
    return recorded


_MESSAGES = [{"role": "user", "content": "xin chào"}]


# --- mặc định: không đổi hành vi ------------------------------------------------------------------


def test_an_unconfigured_role_inherits_the_global_provider_order(two_providers, calls) -> None:
    provider_router.complete(_MESSAGES, role=provider_router.ROLE_FACT_EXTRACTOR)
    provider_router.complete(_MESSAGES)

    assert calls == ["deepseek", "deepseek"]


def test_an_unconfigured_profile_reports_that_it_inherits(two_providers) -> None:
    profile = provider_router.role_profile(provider_router.ROLE_SYNTHESIS)

    assert profile is not None
    assert profile.inherits_global_order is True


def test_an_unknown_role_is_rejected_instead_of_silently_ignored(two_providers) -> None:
    """Gõ sai tên vai trò phải vỡ ngay, không được âm thầm rơi về thứ tự toàn cục - nếu không, một
    lỗi chính tả sẽ biến thành "vai trò này chưa bao giờ được định tuyến riêng" mà không ai thấy."""
    with pytest.raises(provider_router.UnknownProviderError):
        provider_router.role_profile("fact_extracter")


# --- định tuyến riêng theo vai trò ----------------------------------------------------------------


def test_a_configured_role_uses_its_own_provider_order(two_providers, calls) -> None:
    two_providers.role_order_synthesis = "openai,deepseek"

    provider_router.complete(_MESSAGES, role=provider_router.ROLE_SYNTHESIS)
    provider_router.complete(_MESSAGES, role=provider_router.ROLE_FACT_EXTRACTOR)

    # Diễn đạt đi openai, trích xuất vẫn theo thứ tự toàn cục - đây chính là thứ `RoleProfile` mở ra.
    assert calls == ["openai", "deepseek"]


def test_a_user_credential_ignores_the_role_order(two_providers, calls, monkeypatch) -> None:
    """Key người dùng: đúng provider họ đưa, KHÔNG fallback, và vai trò không được chen vào."""
    two_providers.role_order_synthesis = "openai"
    monkeypatch.setattr(
        provider_router, "make_provider_for_credential",
        lambda credential: _FakeProvider(calls, credential.provider),
    )
    credential = provider_router.LLMCredential(provider="deepseek", api_key="sk-user-key-123456")

    provider_router.complete(_MESSAGES, role=provider_router.ROLE_SYNTHESIS, credential=credential)

    assert calls == ["deepseek"]


# --- số liệu theo vai trò (P1.4) ------------------------------------------------------------------


def test_usage_is_recorded_per_role_not_as_one_number(two_providers, calls) -> None:
    """Gộp một con số cho cả hệ thống thì không trả lời được câu hỏi của §7.2 - trích xuất và diễn
    đạt có hình dạng chi phí khác hẳn nhau."""
    provider_router.complete(_MESSAGES, role=provider_router.ROLE_FACT_EXTRACTOR)
    provider_router.complete(_MESSAGES, role=provider_router.ROLE_FACT_EXTRACTOR)
    provider_router.complete(_MESSAGES, role=provider_router.ROLE_SYNTHESIS)

    snapshot = provider_router.role_usage_snapshot()

    assert snapshot[provider_router.ROLE_FACT_EXTRACTOR]["calls"] == 2
    assert snapshot[provider_router.ROLE_SYNTHESIS]["calls"] == 1
    assert snapshot[provider_router.ROLE_FACT_EXTRACTOR]["by_provider"] == {"deepseek": 2}
    assert snapshot[provider_router.ROLE_FACT_EXTRACTOR]["p95_ms"] is not None


def test_a_call_without_a_role_is_not_recorded(two_providers, calls) -> None:
    provider_router.complete(_MESSAGES)

    assert provider_router.role_usage_snapshot() == {}


def test_percentiles_use_nearest_rank_without_interpolation() -> None:
    assert provider_router._percentile([], 50) is None
    assert provider_router._percentile([10, 20, 30, 40], 50) == 20
    assert provider_router._percentile([10, 20, 30, 40], 95) == 40
    assert provider_router._percentile([7], 95) == 7
