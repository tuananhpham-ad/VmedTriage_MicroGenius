"""Test vòng xoay model free của OpenRouter và log provider/model.

Không gọi API thật: `make_provider` được thay bằng adapter giả ghi lại đúng thứ tự model đã thử,
vì thứ tự đó CHÍNH LÀ hành vi cần bảo vệ (429 -> model free kế tiếp, 401 -> bỏ luôn provider).
"""

from __future__ import annotations

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
        lambda name, *, api_key=None: _FakeProvider(attempts, {first: 429}),
    )
    credential = provider_router.LLMCredential(provider="openrouter", api_key="sk-user-1234567890")

    result = provider_router.complete([{"role": "user", "content": "chào"}], credential=credential)

    assert attempts == [first, second]
    assert result.model == second


def test_user_credential_with_model_is_respected_without_rotation(openrouter_only, monkeypatch):
    attempts: list[str] = []
    monkeypatch.setattr(
        "src.providers.make_provider",
        lambda name, *, api_key=None: _FakeProvider(attempts, {}),
    )
    credential = provider_router.LLMCredential(
        provider="openrouter", api_key="sk-user-1234567890", model="openai/gpt-4o-mini"
    )

    provider_router.complete([{"role": "user", "content": "chào"}], credential=credential)

    assert attempts == ["openai/gpt-4o-mini"]


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
