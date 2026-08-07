"""Chọn và gọi LLM provider theo API key thực sự có trong cấu hình.

Vì sao cần module này (thay vì dùng thẳng `src/services/llm.py`):

1. `src/services/llm.py` chạy trên LangChain và chỉ hỗ trợ 3 provider (openai/deepseek/gemini),
   trong khi `src/providers/` đã có sẵn 5 adapter với interface thống nhất `complete() -> ModelResponse`.
2. `src/providers/*` đọc API key bằng `os.getenv(...)`, NHƯNG dự án nạp `.env` qua pydantic-settings
   (`src/config.py`) - thứ không ghi vào `os.environ`. Không có `load_dotenv()` nào trong `src/`,
   nên toàn bộ `src/providers/` trước đây KHÔNG THỂ chạy được trong app. Module này đồng bộ key từ
   `Settings` sang `os.environ` ngay trước khi gọi provider để vá đúng khoảng trống đó.
3. Cần fallback: nếu provider đầu tiên lỗi (hết quota, mạng, model sai tên) thì tự chuyển sang
   provider tiếp theo còn key, thay vì hỏng cả tính năng.

Thứ tự ưu tiên đọc từ `Settings.llm_provider_order`; đặt `Settings.llm_provider` khác `"auto"` để ép
dùng đúng một provider.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass

from src.config import get_settings

logger = logging.getLogger("vmedtriage.provider")

# Giá trị mẫu trong .env.example - coi như CHƯA cấu hình để không gọi API với key rác.
PLACEHOLDER_KEYS = frozenset(
    {
        "sk-your-key-here",
        "your-langsmith-key-here",
        "your-api-key-here",
        "changeme",
    }
)


@dataclass(frozen=True, slots=True)
class ProviderSpec:
    name: str
    api_key_attr: str
    """Tên thuộc tính chứa API key trong Settings."""
    env_var: str
    """Biến môi trường mà adapter trong src/providers/ sẽ đọc bằng os.getenv."""
    model_attr: str
    """Tên thuộc tính chứa tên model mặc định trong Settings."""


PROVIDER_SPECS: tuple[ProviderSpec, ...] = (
    ProviderSpec("gemini", "gemini_api_key", "GEMINI_API_KEY", "gemini_model_name"),
    ProviderSpec("deepseek", "deepseek_api_key", "DEEPSEEK_API_KEY", "deepseek_model_name"),
    ProviderSpec("openai", "openai_api_key", "OPENAI_API_KEY", "openai_model_name"),
    ProviderSpec("anthropic", "anthropic_api_key", "ANTHROPIC_API_KEY", "anthropic_model_name"),
    ProviderSpec("openrouter", "openrouter_api_key", "OPENROUTER_API_KEY", "openrouter_model_name"),
)

SPECS_BY_NAME: dict[str, ProviderSpec] = {spec.name: spec for spec in PROVIDER_SPECS}


def has_usable_key(value: str) -> bool:
    normalized = (value or "").strip().strip('"').strip("'")
    return bool(normalized) and normalized not in PLACEHOLDER_KEYS


def available_providers() -> list[str]:
    """Các provider đã có API key dùng được, theo thứ tự ưu tiên đã cấu hình."""
    settings = get_settings()
    return [
        spec.name
        for spec in _ordered_specs(settings.llm_provider, settings.llm_provider_order)
        if has_usable_key(getattr(settings, spec.api_key_attr, ""))
    ]


def _ordered_specs(configured_provider: str, configured_order: str) -> list[ProviderSpec]:
    if configured_provider != "auto":
        spec = SPECS_BY_NAME.get(configured_provider)
        return [spec] if spec else []

    ordered: list[ProviderSpec] = []
    for raw_name in configured_order.split(","):
        spec = SPECS_BY_NAME.get(raw_name.strip().lower())
        if spec and spec not in ordered:
            ordered.append(spec)
    # Provider không được liệt kê vẫn dùng được nếu có key - xếp sau các provider đã liệt kê.
    ordered.extend(spec for spec in PROVIDER_SPECS if spec not in ordered)
    return ordered


def _build_provider(spec: ProviderSpec):
    """Khởi tạo adapter và đồng bộ API key sang os.environ (xem lý do ở docstring module)."""
    settings = get_settings()
    api_key = getattr(settings, spec.api_key_attr, "").strip().strip('"').strip("'")
    os.environ[spec.env_var] = api_key

    if spec.name == "openrouter":
        # OpenRouterProvider đọc base_url/model từ os.environ chứ không qua Settings.
        os.environ.setdefault("OPENROUTER_BASE_URL", settings.openrouter_base_url)
        os.environ.setdefault("OPENROUTER_MODEL_NAME", settings.openrouter_model_name)

    from src.providers import make_provider

    return make_provider(spec.name)


class NoProviderConfiguredError(RuntimeError):
    pass


@dataclass(slots=True)
class CompletionResult:
    text: str
    provider: str
    model: str


def complete(
    messages: Sequence[dict[str, str]],
    *,
    temperature: float | None = None,
    max_attempts: int = 3,
) -> CompletionResult:
    """Gọi LLM qua provider đầu tiên khả dụng, tự chuyển provider khác nếu lỗi.

    Raise `NoProviderConfiguredError` khi không có provider nào có key, hoặc mọi provider đều lỗi -
    người gọi tự quyết định fallback (intake_agent dùng nhánh deterministic).
    """
    settings = get_settings()
    resolved_temperature = settings.llm_temperature if temperature is None else temperature
    specs = [
        spec
        for spec in _ordered_specs(settings.llm_provider, settings.llm_provider_order)
        if has_usable_key(getattr(settings, spec.api_key_attr, ""))
    ]
    if not specs:
        raise NoProviderConfiguredError(
            "Chưa cấu hình API key cho provider nào. Đặt một trong: "
            + ", ".join(spec.env_var for spec in PROVIDER_SPECS)
        )

    errors: list[str] = []
    for spec in specs[:max_attempts]:
        model = getattr(settings, spec.model_attr, "") or None
        try:
            provider = _build_provider(spec)
            response = provider.complete(
                list(messages),
                model=model,
                temperature=resolved_temperature,
            )
        except Exception as exc:
            errors.append(f"{spec.name}: {type(exc).__name__}: {exc}")
            logger.warning("provider.failed name=%s reason=%s", spec.name, type(exc).__name__)
            continue

        text = (response.text or "").strip()
        if not text:
            errors.append(f"{spec.name}: trả về nội dung rỗng")
            logger.warning("provider.empty_response name=%s", spec.name)
            continue

        return CompletionResult(text=text, provider=spec.name, model=model or "(mặc định của adapter)")

    raise NoProviderConfiguredError("Mọi provider đều lỗi -> " + " | ".join(errors))
