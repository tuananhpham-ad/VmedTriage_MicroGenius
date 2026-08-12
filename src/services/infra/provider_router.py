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

# Model gợi ý cho UI. KHÔNG phải danh sách đóng - người dùng vẫn gõ tay được tên model khác, vì
# nhà cung cấp ra model mới liên tục và hardcode cứng sẽ nhanh lỗi thời.
SUGGESTED_MODELS: dict[str, tuple[str, ...]] = {
    "gemini": ("gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-flash", "gemini-1.5-pro"),
    "deepseek": ("deepseek-chat", "deepseek-reasoner"),
    "openai": ("gpt-4o-mini", "gpt-4o"),
    "anthropic": ("claude-haiku-4-5-20251001", "claude-sonnet-5", "claude-opus-5"),
    "openrouter": ("openai/gpt-4o-mini", "anthropic/claude-sonnet-5", "google/gemini-2.0-flash"),
}


@dataclass(frozen=True, slots=True)
class LLMCredential:
    """API key + model do NGƯỜI DÙNG cung cấp cho một phiên cụ thể.

    Tồn tại để mỗi người test dùng key của chính họ thay vì key trong `.env` của dự án.

    Ràng buộc bảo mật: object này chỉ được giữ in-memory theo phiên. TUYỆT ĐỐI không ghi vào
    `logs/*.json`, không log ra console, không trả lại trong API response - dùng `masked()` khi cần
    hiển thị.
    """

    provider: str
    api_key: str
    model: str | None = None

    def masked(self) -> str:
        """Dạng che để hiển thị/ghi log an toàn, vd `sk-••••1f13`."""
        key = self.api_key.strip()
        if len(key) <= 8:
            return "••••"
        return f"{key[:3]}••••{key[-4:]}"

    def __repr__(self) -> str:  # chặn key lọt ra qua repr khi debug/log vô ý
        return f"LLMCredential(provider={self.provider!r}, model={self.model!r}, api_key={self.masked()!r})"


class UnknownProviderError(ValueError):
    pass


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


# Vì sao cần map này: thông báo lỗi nguyên văn của SDK CÓ THỂ chứa lại API key
# (vd DeepSeek: "Your api key: sk-xxx is invalid") nên không được đưa ra ngoài. Nhưng chỉ báo tên
# exception thì vô dụng - "ClientError" không phân biệt được key sai với hết quota. Lấy mã HTTP ra
# và diễn giải là đủ thông tin để xử lý mà không rò key.
_STATUS_HINTS: dict[int, str] = {
    401: "API key sai hoặc đã bị thu hồi",
    402: "tài khoản hết số dư - cần nạp thêm tiền",
    403: "key không có quyền dùng model này",
    404: "không tìm thấy model - kiểm tra lại tên model",
    429: "hết quota hoặc bị giới hạn tốc độ - chờ hoặc nâng gói",
}


def _status_code_of(exc: Exception) -> int | None:
    """Lấy mã HTTP từ exception của nhiều SDK khác nhau (openai: status_code, google: code)."""
    for attr in ("status_code", "code", "http_status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    return None


def describe_provider_error(provider: str, exc: Exception) -> str:
    """Mô tả lỗi gọi LLM đủ để người dùng biết phải làm gì, KHÔNG kèm nguyên văn từ SDK."""
    status = _status_code_of(exc)
    hint = _STATUS_HINTS.get(status or 0)
    if hint:
        return f"{provider}: {hint} (HTTP {status})"
    if status:
        return f"{provider}: lỗi HTTP {status} ({type(exc).__name__})"
    return f"{provider}: {type(exc).__name__}"


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
    credential: LLMCredential | None = None,
) -> CompletionResult:
    """Gọi LLM qua provider đầu tiên khả dụng, tự chuyển provider khác nếu lỗi.

    `credential` != None: dùng ĐÚNG provider + key người dùng đưa, KHÔNG fallback sang provider khác
    (key của họ, không tự ý chuyển sang provider khác thay họ) và KHÔNG đụng `os.environ`.

    Raise `NoProviderConfiguredError` khi không có provider nào có key, hoặc mọi provider đều lỗi -
    người gọi tự quyết định fallback (intake_agent dùng nhánh deterministic).
    """
    settings = get_settings()
    resolved_temperature = settings.llm_temperature if temperature is None else temperature

    if credential is not None:
        return _complete_with_credential(credential, messages, resolved_temperature)

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
            described = describe_provider_error(spec.name, exc)
            errors.append(described)
            logger.warning("provider.failed %s", described)
            continue

        text = (response.text or "").strip()
        if not text:
            errors.append(f"{spec.name}: trả về nội dung rỗng")
            logger.warning("provider.empty_response name=%s", spec.name)
            continue

        return CompletionResult(text=text, provider=spec.name, model=model or "(mặc định của adapter)")

    raise NoProviderConfiguredError("Mọi provider đều lỗi -> " + " | ".join(errors))


def _complete_with_credential(
    credential: LLMCredential,
    messages: Sequence[dict[str, str]],
    temperature: float,
) -> CompletionResult:
    """Gọi LLM bằng key người dùng đưa. Không fallback provider, không ghi os.environ."""
    if credential.provider not in SPECS_BY_NAME:
        raise UnknownProviderError(
            f"Provider không hợp lệ: {credential.provider}. Chọn một trong: "
            + ", ".join(SPECS_BY_NAME)
        )
    if not has_usable_key(credential.api_key):
        raise NoProviderConfiguredError("API key trống hoặc là giá trị mẫu.")

    from src.providers import make_provider

    provider = make_provider(credential.provider, api_key=credential.api_key.strip())
    try:
        response = provider.complete(list(messages), model=credential.model, temperature=temperature)
    except Exception as exc:
        # Thông báo lỗi của SDK có thể chứa lại API key -> chỉ đưa ra mã HTTP đã được diễn giải.
        described = describe_provider_error(credential.provider, exc)
        logger.warning("provider.user_credential_failed %s", described)
        raise NoProviderConfiguredError(f"Gọi thất bại -> {described}") from exc

    text = (response.text or "").strip()
    if not text:
        raise NoProviderConfiguredError(f"{credential.provider} trả về nội dung rỗng.")
    return CompletionResult(text=text, provider=credential.provider, model=credential.model or "(mặc định)")
