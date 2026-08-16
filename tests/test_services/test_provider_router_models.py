"""Test vòng xoay model free của OpenRouter và log provider/model.

Không gọi API thật: `make_provider` được thay bằng adapter giả ghi lại đúng thứ tự model đã thử,
vì thứ tự đó CHÍNH LÀ hành vi cần bảo vệ (429 -> model free kế tiếp, 401 -> bỏ luôn provider).
"""

from __future__ import annotations

import os

import pytest

from src.config import OPENROUTER_FREE_MODELS, Settings
from src.services.infra import provider_router


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _StatusError(Exception):
    """Giả lỗi SDK: chỉ mang `status_code`, đúng thứ `_status_code_of` đọc."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


class _FakeProvider:
    """Ghi lại model được yêu cầu; trả lỗi theo kịch bản `outcomes` (theo tên model)."""

    def __init__(self, attempts: list[str], outcomes: dict[str, int]) -> None:
        self._attempts = attempts
        self._outcomes = outcomes

    def complete(self, messages, tools=None, *, model=None, temperature=0.0, tool_choice=None):
        self._attempts.append(model)
        status = self._outcomes.get(model)
        if status is not None:
            raise _StatusError(status)
        return _FakeResponse(f"trả lời từ {model}")


@pytest.fixture
def openrouter_only(monkeypatch):
    """Cấu hình chỉ có OpenRouter và một key giả dùng được.

    `_env_file=None` là bắt buộc: không có nó, `Settings()` vẫn đọc `.env` thật của máy đang chạy
    test và provider thứ hai (gemini/deepseek...) sẽ nhận được key thật -> fallback đi tiếp thay vì
    dừng, làm test đo sai hành vi. Các field dùng `AliasChoices` cũng không nhận kwarg theo tên
    field, nên key phải đặt qua biến môi trường.
    """
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY",
                "ANTHROPIC_API_KEY", "OPEN_ROUTER_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-key-1234567890")

    settings = Settings(
        _env_file=None,
        llm_provider="auto",
        llm_provider_order="openrouter",
        openrouter_model_name="",
        deepseek_api_key="",
        openai_api_key="",
        anthropic_api_key="",
    )
    monkeypatch.setattr(provider_router, "get_settings", lambda: settings)
    monkeypatch.setattr("src.config.get_settings", lambda: settings)
    return settings


def _install_fake_provider(monkeypatch, outcomes: dict[str, int]) -> list[str]:
    attempts: list[str] = []
    monkeypatch.setattr(
        provider_router,
        "_build_provider",
        lambda spec, model=None: _FakeProvider(attempts, outcomes),
    )
    return attempts


# --- danh sách model ------------------------------------------------------------------------


def test_candidates_default_to_free_list(openrouter_only):
    candidates = provider_router.openrouter_model_candidates()

    assert candidates == list(OPENROUTER_FREE_MODELS)[: openrouter_only.openrouter_max_model_attempts]
    assert all(model.endswith(":free") for model in candidates)


def test_explicit_model_goes_first_and_free_list_stays_as_backup(openrouter_only, monkeypatch):
    openrouter_only.openrouter_model_name = "openai/gpt-4o-mini"

    candidates = provider_router.openrouter_model_candidates()

    assert candidates[0] == "openai/gpt-4o-mini"
    assert candidates[1] == OPENROUTER_FREE_MODELS[0]


def test_candidates_respect_max_attempts(openrouter_only):
    openrouter_only.openrouter_max_model_attempts = 2

    assert len(provider_router.openrouter_model_candidates()) == 2


def test_free_models_from_env_override_the_code_default(openrouter_only):
    openrouter_only.openrouter_free_models = " a/one:free , b/two:free , a/one:free "

    assert provider_router.openrouter_model_candidates() == ["a/one:free", "b/two:free"]


def test_other_providers_still_get_exactly_one_model(monkeypatch):
    settings = Settings(gemini_model_name="gemini-2.0-flash")
    monkeypatch.setattr(provider_router, "get_settings", lambda: settings)

    models = provider_router._candidate_models(provider_router.SPECS_BY_NAME["gemini"])

    assert models == ["gemini-2.0-flash"]


# --- xoay vòng khi gọi ----------------------------------------------------------------------


def test_rate_limited_model_rotates_to_next_free_model(openrouter_only, monkeypatch):
    first, second = OPENROUTER_FREE_MODELS[0], OPENROUTER_FREE_MODELS[1]
    attempts = _install_fake_provider(monkeypatch, {first: 429})

    result = provider_router.complete([{"role": "user", "content": "chào"}])

    assert attempts == [first, second]
    assert result.provider == "openrouter"
    assert result.model == second


def test_bad_key_stops_rotation_instead_of_burning_the_whole_list(openrouter_only, monkeypatch):
    attempts = _install_fake_provider(monkeypatch, dict.fromkeys(OPENROUTER_FREE_MODELS, 401))

    with pytest.raises(provider_router.NoProviderConfiguredError):
        provider_router.complete([{"role": "user", "content": "chào"}])

    # 401 là lỗi của KEY: thử model thứ hai với cùng key đó cũng hỏng y hệt.
    assert attempts == [OPENROUTER_FREE_MODELS[0]]


def test_error_message_names_the_model_that_failed(openrouter_only, monkeypatch):
    _install_fake_provider(monkeypatch, dict.fromkeys(OPENROUTER_FREE_MODELS, 429))

    with pytest.raises(provider_router.NoProviderConfiguredError) as excinfo:
        provider_router.complete([{"role": "user", "content": "chào"}])

    assert OPENROUTER_FREE_MODELS[0] in str(excinfo.value)


def test_user_credential_without_model_rotates_free_models(openrouter_only, monkeypatch):
    first, second = OPENROUTER_FREE_MODELS[0], OPENROUTER_FREE_MODELS[1]
    attempts: list[str] = []
    monkeypatch.setattr(
        "src.providers.make_provider",
        lambda name, **kwargs: _FakeProvider(attempts, {first: 429}),
    )
    credential = provider_router.LLMCredential(provider="openrouter", api_key="sk-user-1234567890")

    result = provider_router.complete([{"role": "user", "content": "chào"}], credential=credential)

    assert attempts == [first, second]
    assert result.model == second


def test_user_credential_with_model_is_respected_without_rotation(openrouter_only, monkeypatch):
    attempts: list[str] = []
    monkeypatch.setattr(
        "src.providers.make_provider",
        lambda name, **kwargs: _FakeProvider(attempts, {}),
    )
    credential = provider_router.LLMCredential(
        provider="openrouter", api_key="sk-user-1234567890", model="openai/gpt-4o-mini"
    )

    provider_router.complete([{"role": "user", "content": "chào"}], credential=credential)

    assert attempts == ["openai/gpt-4o-mini"]


# --- cô lập giữa các request ------------------------------------------------------------------


def test_building_a_provider_never_writes_to_os_environ(openrouter_only, monkeypatch):
    """os.environ là biến TOÀN PROCESS: ghi model vào đó thì hai request song song đè lên nhau."""
    monkeypatch.delenv("OPENROUTER_MODEL_NAME", raising=False)
    monkeypatch.delenv("OPENROUTER_BASE_URL", raising=False)

    provider = provider_router._build_provider(
        provider_router.SPECS_BY_NAME["openrouter"], "a/one:free"
    )

    assert "OPENROUTER_MODEL_NAME" not in os.environ
    assert "OPENROUTER_BASE_URL" not in os.environ
    # Cấu hình đi thẳng vào adapter thay vì qua môi trường chung.
    assert provider.default_model == "a/one:free"
    assert provider.base_url == openrouter_only.openrouter_base_url
    assert provider.api_key == "sk-test-key-1234567890"


def test_two_providers_built_in_sequence_keep_their_own_model(openrouter_only):
    """Adapter dựng trước KHÔNG được đổi model khi adapter sau được dựng - đó là race cũ."""
    spec = provider_router.SPECS_BY_NAME["openrouter"]

    first = provider_router._build_provider(spec, "a/one:free")
    second = provider_router._build_provider(spec, "b/two:free")

    assert (first.default_model, second.default_model) == ("a/one:free", "b/two:free")


# --- ngân sách của một request -----------------------------------------------------------------


def test_total_attempt_budget_stops_the_rotation_early(openrouter_only, monkeypatch):
    openrouter_only.openrouter_max_model_attempts = 8
    openrouter_only.llm_max_total_attempts = 2
    attempts = _install_fake_provider(monkeypatch, dict.fromkeys(OPENROUTER_FREE_MODELS, 429))

    with pytest.raises(provider_router.NoProviderConfiguredError) as excinfo:
        provider_router.complete([{"role": "user", "content": "chào"}])

    assert len(attempts) == 2
    assert "ngân sách" in str(excinfo.value)


def test_time_budget_stops_before_the_next_model(openrouter_only, monkeypatch):
    """Trần thời gian mới là cái cứu request: đếm lượt vô nghĩa khi mỗi model treo hàng chục giây."""
    openrouter_only.llm_total_budget_seconds = 5.0
    now = {"seconds": 0.0}
    monkeypatch.setattr(provider_router.time, "monotonic", lambda: now["seconds"])

    attempts: list[str] = []

    class _SlowProvider(_FakeProvider):
        """Mỗi lượt ngốn 99s trước khi lỗi - đúng kịch bản model treo tới lúc timeout."""

        def complete(self, *args, **kwargs):
            now["seconds"] += 99.0
            return super().complete(*args, **kwargs)

    monkeypatch.setattr(
        provider_router,
        "_build_provider",
        lambda spec, model=None: _SlowProvider(attempts, dict.fromkeys(OPENROUTER_FREE_MODELS, 429)),
    )

    with pytest.raises(provider_router.NoProviderConfiguredError):
        provider_router.complete([{"role": "user", "content": "chào"}])

    assert attempts == [OPENROUTER_FREE_MODELS[0]]


def test_user_credential_rotation_respects_the_same_budget(openrouter_only, monkeypatch):
    openrouter_only.llm_max_total_attempts = 1
    attempts: list[str] = []
    monkeypatch.setattr(
        "src.providers.make_provider",
        lambda name, **kwargs: _FakeProvider(attempts, dict.fromkeys(OPENROUTER_FREE_MODELS, 429)),
    )
    credential = provider_router.LLMCredential(provider="openrouter", api_key="sk-user-1234567890")

    with pytest.raises(provider_router.NoProviderConfiguredError):
        provider_router.complete([{"role": "user", "content": "chào"}], credential=credential)

    assert len(attempts) == 1


# --- log ------------------------------------------------------------------------------------


def test_successful_call_logs_provider_and_model(openrouter_only, monkeypatch, caplog):
    _install_fake_provider(monkeypatch, {})

    with caplog.at_level("INFO", logger="vmedtriage.provider"):
        provider_router.complete([{"role": "user", "content": "chào"}])

    assert any(
        "provider.selected" in record.message and OPENROUTER_FREE_MODELS[0] in record.getMessage()
        for record in caplog.records
    )


def test_skipped_model_is_logged_too(openrouter_only, monkeypatch, caplog):
    _install_fake_provider(monkeypatch, {OPENROUTER_FREE_MODELS[0]: 429})

    with caplog.at_level("WARNING", logger="vmedtriage.provider"):
        provider_router.complete([{"role": "user", "content": "chào"}])

    assert any(OPENROUTER_FREE_MODELS[0] in record.getMessage() for record in caplog.records)


def test_console_trace_prints_the_model_in_use(openrouter_only, monkeypatch, capsys):
    _install_fake_provider(monkeypatch, {})
    from src.services.infra import console_log

    console_log.set_enabled(True)
    try:
        provider_router.complete([{"role": "user", "content": "chào"}])
    finally:
        console_log.set_enabled(None)

    assert OPENROUTER_FREE_MODELS[0] in capsys.readouterr().out


def test_describe_selection_names_model_and_backups(openrouter_only):
    described = provider_router.describe_selection()

    assert "openrouter" in described
    assert OPENROUTER_FREE_MODELS[0] in described
    assert "dự phòng" in described


def test_describe_selection_never_leaks_the_user_key():
    credential = provider_router.LLMCredential(
        provider="openrouter", api_key="sk-super-secret-key-1234", model="a/b:free"
    )

    described = provider_router.describe_selection(credential)

    assert "sk-super-secret-key-1234" not in described
    assert "a/b:free" in described
