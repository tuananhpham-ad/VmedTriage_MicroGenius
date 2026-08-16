"""Chọn và gọi LLM provider theo API key thực sự có trong cấu hình.

Vì sao cần module này (thay vì dùng thẳng `src/services/llm.py`):

1. `src/services/llm.py` chạy trên LangChain và chỉ hỗ trợ 3 provider (openai/deepseek/gemini),
   trong khi `src/providers/` đã có sẵn 5 adapter với interface thống nhất `complete() -> ModelResponse`.
2. `src/providers/*` mặc định đọc API key bằng `os.getenv(...)`, NHƯNG dự án nạp `.env` qua
   pydantic-settings (`src/config.py`) - thứ không ghi vào `os.environ`. Không có `load_dotenv()` nào
   trong `src/`, nên toàn bộ `src/providers/` trước đây KHÔNG THỂ chạy được trong app. Module này vá
   khoảng trống đó bằng cách TRUYỀN THẲNG key/base_url/model từ `Settings` vào adapter (xem
   `_build_provider`), thay vì ghi vào `os.environ` - lý do ở ngay dưới.
3. Cần fallback: nếu provider đầu tiên lỗi (hết quota, mạng, model sai tên) thì tự chuyển sang
   provider tiếp theo còn key, thay vì hỏng cả tính năng.

Có HAI cấp fallback, đừng nhầm:

- **Cấp provider** - thứ tự đọc từ `Settings.llm_provider_order`; đặt `Settings.llm_provider` khác
  `"auto"` để ép dùng đúng một provider.
- **Cấp model, chỉ áp dụng cho OpenRouter** - một API key OpenRouter gọi được rất nhiều model, trong
  đó có các model `:free` bị rate-limit rất sớm. Hết quota một model KHÔNG có nghĩa là hết quota cả
  key, nên chuyển provider ngay là phí: ta xoay vòng sang model free kế tiếp trong
  `config.OPENROUTER_FREE_MODELS` trước, chỉ khi cạn danh sách mới đổi provider.

Ngoại lệ của cấp model: lỗi 401/403 là lỗi CỦA KEY chứ không phải của model - đổi model cũng vô ích
nên bỏ luôn phần còn lại của danh sách và sang provider khác.

Fallback hai cấp nhân với nhau ra rất nhiều vòng HTTP nối tiếp, nên MỖI lần `complete()` có một
ngân sách chung (`_AttemptBudget`): tối đa `llm_max_total_attempts` lượt gọi VÀ
`llm_total_budget_seconds` giây. Hết ngân sách thì dừng ngay và báo lỗi, thay vì để một request treo
hàng phút chỉ vì danh sách model dài.

Không có state toàn cục ở đây: `os.environ` là biến TOÀN PROCESS, hai request song song ghi đè nhau
nên module này KHÔNG ghi gì vào đó - mọi thứ đi qua tham số của `make_provider`.

Mọi lần gọi đều log ra provider + model thực sự dùng (`logger.info` + trace console), vì khi có
fallback hai cấp thì "model nào vừa trả lời" không còn suy ra được từ `.env`.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass

from src.config import OPENROUTER_FREE_MODELS, get_settings
from src.services.infra import console_log

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
    """Biến môi trường chứa key của provider này.

    Router KHÔNG ghi vào biến này (xem `_build_provider`); nó dùng để chỉ cho người dùng đúng tên
    biến cần đặt trong `.env`, và là chỗ adapter tự đọc khi được dựng ngoài router.
    """
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
    # Model free lên đầu vì đó là mặc định của router; các model trả phí vẫn gõ tay được.
    "openrouter": OPENROUTER_FREE_MODELS + ("openai/gpt-4o-mini", "anthropic/claude-sonnet-5"),
}

# 401/403 = key sai hoặc không có quyền. Đổi model với cùng cái key đó thì vẫn hỏng y hệt, nên dừng
# xoay vòng model ngay để không đốt thêm vòng HTTP.
_KEY_LEVEL_STATUSES = frozenset({401, 403})


def openrouter_model_candidates() -> list[str]:
    """Các model OpenRouter sẽ thử lần lượt trong một lần gọi.

    `OPENROUTER_MODEL_NAME` (nếu đặt) đứng đầu, sau đó là danh sách free trong
    `OPENROUTER_FREE_MODELS` / `OPENROUTER_FREE_MODELS` của `.env`. Cắt theo
    `openrouter_max_model_attempts`.
    """
    settings = get_settings()
    candidates: list[str] = []
    for raw in [settings.openrouter_model_name, *settings.openrouter_free_models.split(",")]:
        model = raw.strip().strip('"').strip("'")
        if model and model not in candidates:
            candidates.append(model)
    return candidates[: settings.openrouter_max_model_attempts]


def _candidate_models(spec: ProviderSpec) -> list[str | None]:
    """Model sẽ thử cho một provider. Chỉ OpenRouter có nhiều hơn một.

    LUÔN trả về ít nhất một phần tử (`[None]` = để adapter tự chọn), kể cả khi danh sách free rỗng.
    Người gọi dựa vào bất biến này: danh sách rỗng sẽ làm vòng lặp trong `complete()` bỏ qua provider
    mà không ghi lỗi nào, và `describe_selection` sẽ `IndexError`.
    """
    if spec.name == "openrouter":
        candidates = openrouter_model_candidates()
        if candidates:
            return list(candidates)
    # `None` = để adapter tự dùng model mặc định của nó.
    return [getattr(get_settings(), spec.model_attr, "").strip() or None]


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


def describe_selection(credential: LLMCredential | None = None) -> str:
    """Provider + model sẽ được dùng cho lượt gọi kế tiếp, dạng in được ra log/console.

    KHÔNG chứa API key. Dùng cho dòng mở phiên và log khởi động server: biết trước "sẽ gọi model nào"
    quan trọng ngang biết "vừa gọi model nào", nhất là khi model đầu danh sách hay hết quota.
    """
    if credential is not None:
        return f"{credential.provider} · {credential.model or 'model mặc định'} (key người dùng)"

    providers = available_providers()
    if not providers:
        return "chưa cấu hình provider nào · dùng nhánh deterministic"

    spec = SPECS_BY_NAME[providers[0]]
    models = _candidate_models(spec)
    head = models[0] or "model mặc định của adapter"
    backup = f" (+{len(models) - 1} model dự phòng)" if len(models) > 1 else ""
    rest = f", sau đó: {', '.join(providers[1:])}" if len(providers) > 1 else ""
    return f"{spec.name} · {head}{backup}{rest}"


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


def _build_provider(spec: ProviderSpec, model: str | None = None):
    """Khởi tạo adapter với key/base_url/model của ĐÚNG lượt gọi này, truyền qua tham số.

    Trước đây hàm này ghi `spec.env_var`, `OPENROUTER_BASE_URL`, `OPENROUTER_MODEL_NAME` vào
    `os.environ` rồi để adapter tự `os.getenv` lúc khởi tạo. `os.environ` là biến TOÀN PROCESS còn
    `complete()` là hàm sync được FastAPI chạy trong threadpool: hai request song song chen vào khe
    giữa "ghi env" và "adapter đọc env" là request này gọi bằng model/base URL của request kia. Đưa
    thẳng vào constructor thì mỗi adapter mang cấu hình riêng, không còn trạng thái dùng chung.
    """
    settings = get_settings()
    api_key = getattr(settings, spec.api_key_attr, "").strip().strip('"').strip("'")

    from src.providers import make_provider

    return make_provider(
        spec.name,
        api_key=api_key,
        # Chỉ OpenRouter cần base URL từ Settings; các adapter khác tự biết endpoint của mình.
        base_url=settings.openrouter_base_url if spec.name == "openrouter" else None,
        default_model=model,
    )


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


def describe_provider_error(provider: str, exc: Exception, *, model: str | None = None) -> str:
    """Mô tả lỗi gọi LLM đủ để người dùng biết phải làm gì, KHÔNG kèm nguyên văn từ SDK.

    Có `model` thì kèm luôn tên model: với OpenRouter, "429" của model free này không nói gì về
    model free kế tiếp - thiếu tên model thì đọc log không biết cái nào vừa hỏng.
    """
    label = f"{provider}/{model}" if model else provider
    status = _status_code_of(exc)
    hint = _STATUS_HINTS.get(status or 0)
    if hint:
        return f"{label}: {hint} (HTTP {status})"
    if status:
        return f"{label}: lỗi HTTP {status} ({type(exc).__name__})"
    return f"{label}: {type(exc).__name__}"


@dataclass(slots=True)
class CompletionResult:
    text: str
    provider: str
    model: str


@dataclass(slots=True)
class _AttemptBudget:
    """Trần cứng cho MỘT lần `complete()`: bao nhiêu lượt gọi LLM và bao nhiêu giây.

    Vì sao cần: fallback cấp provider và cấp model nhân với nhau. Với `max_attempts=3` provider và
    `openrouter_max_model_attempts=4` model, một request lỗi hết có thể ngốn 12 vòng HTTP NỐI TIẾP -
    mỗi vòng có thể chạm timeout của SDK. Không có trần chung thì người dùng ngồi chờ hàng phút mới
    nhận được thông báo lỗi, tệ hơn nhiều so với việc báo lỗi sớm để họ thử lại.

    Trần thời gian mới là cái quyết định: đếm số lượt không cứu được khi một model treo 30s.
    """

    max_attempts: int
    budget_seconds: float
    deadline: float
    used: int = 0

    @classmethod
    def from_settings(cls, settings) -> _AttemptBudget:
        return cls(
            max_attempts=settings.llm_max_total_attempts,
            budget_seconds=settings.llm_total_budget_seconds,
            deadline=time.monotonic() + settings.llm_total_budget_seconds,
        )

    def exhausted_reason(self) -> str | None:
        """Lý do phải dừng, hoặc None nếu còn được gọi tiếp. Gọi TRƯỚC mỗi lượt gọi LLM."""
        if self.used >= self.max_attempts:
            return f"đã dùng hết {self.max_attempts} lượt gọi LLM cho phép trong một request"
        if time.monotonic() >= self.deadline:
            return f"quá {self.budget_seconds:.0f}s ngân sách chờ LLM của một request"
        return None

    def consume(self) -> None:
        self.used += 1


def complete(
    messages: Sequence[dict[str, str]],
    *,
    temperature: float | None = None,
    max_attempts: int = 3,
    credential: LLMCredential | None = None,
) -> CompletionResult:
    """Gọi LLM qua provider đầu tiên khả dụng, tự chuyển model rồi chuyển provider nếu lỗi.

    Với OpenRouter, mỗi provider còn có vòng trong xoay qua các model free (xem docstring module).

    `credential` != None: dùng ĐÚNG provider + key người dùng đưa, KHÔNG fallback sang provider khác
    (key của họ, không tự ý chuyển sang provider khác thay họ).

    `max_attempts` chỉ giới hạn số PROVIDER. Tổng số lượt gọi và tổng thời gian còn bị chặn thêm bởi
    `_AttemptBudget` (`llm_max_total_attempts` / `llm_total_budget_seconds`), nếu không thì
    provider × model nhân ra hàng chục vòng HTTP nối tiếp cho một request.

    Raise `NoProviderConfiguredError` khi không có provider nào có key, khi mọi provider đều lỗi, hoặc
    khi hết ngân sách - người gọi tự quyết định fallback (intake_agent dùng nhánh deterministic).
    """
    settings = get_settings()
    resolved_temperature = settings.llm_temperature if temperature is None else temperature

    budget = _AttemptBudget.from_settings(settings)

    if credential is not None:
        return _complete_with_credential(credential, messages, resolved_temperature, budget)

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
    out_of_budget: str | None = None
    for spec in specs[:max_attempts]:
        for model in _candidate_models(spec):
            out_of_budget = budget.exhausted_reason()
            if out_of_budget:
                break

            budget.consume()
            label = model or "(mặc định của adapter)"
            started = time.monotonic()
            try:
                provider = _build_provider(spec, model)
                response = provider.complete(
                    list(messages),
                    model=model,
                    temperature=resolved_temperature,
                )
            except Exception as exc:
                described = describe_provider_error(spec.name, exc, model=model)
                errors.append(described)
                logger.warning("provider.failed %s", described)
                console_log.llm_attempt(provider=spec.name, model=label, ok=False, note=described)
                if _status_code_of(exc) in _KEY_LEVEL_STATUSES:
                    break  # lỗi của key, không phải của model -> sang provider khác luôn
                continue

            latency_ms = int((time.monotonic() - started) * 1000)
            text = (response.text or "").strip()
            if not text:
                errors.append(f"{spec.name}/{label}: trả về nội dung rỗng")
                logger.warning("provider.empty_response name=%s model=%s", spec.name, label)
                console_log.llm_attempt(provider=spec.name, model=label, ok=False, note="nội dung rỗng")
                continue

            logger.info(
                "provider.selected provider=%s model=%s latency_ms=%d", spec.name, label, latency_ms
            )
            console_log.llm_attempt(provider=spec.name, model=label, ok=True, latency_ms=latency_ms)
            return CompletionResult(text=text, provider=spec.name, model=label)

        if out_of_budget:
            break

    if out_of_budget:
        logger.warning("provider.budget_exhausted %s", out_of_budget)
        errors.append(f"dừng sớm: {out_of_budget}")
        raise NoProviderConfiguredError("Hết ngân sách gọi LLM -> " + " | ".join(errors))

    raise NoProviderConfiguredError("Mọi provider đều lỗi -> " + " | ".join(errors))


def _complete_with_credential(
    credential: LLMCredential,
    messages: Sequence[dict[str, str]],
    temperature: float,
    budget: _AttemptBudget,
) -> CompletionResult:
    """Gọi LLM bằng key người dùng đưa. Không fallback provider, không đụng trạng thái toàn process.

    Vẫn xoay vòng MODEL khi người dùng đưa key OpenRouter mà không chỉ định model: đó vẫn là key của
    họ, chỉ là không có tên model nào để tôn trọng. Vòng xoay đó cũng chịu chung `budget` với nhánh
    key server - key của ai thì cũng là request của cùng một người đang chờ.
    """
    if credential.provider not in SPECS_BY_NAME:
        raise UnknownProviderError(
            f"Provider không hợp lệ: {credential.provider}. Chọn một trong: "
            + ", ".join(SPECS_BY_NAME)
        )
    if not has_usable_key(credential.api_key):
        raise NoProviderConfiguredError("API key trống hoặc là giá trị mẫu.")

    from src.providers import make_provider

    if credential.model:
        candidates: list[str | None] = [credential.model]
    elif credential.provider == "openrouter":
        candidates = list(openrouter_model_candidates()) or [None]
    else:
        candidates = [None]

    errors: list[str] = []
    out_of_budget: str | None = None
    for model in candidates:
        out_of_budget = budget.exhausted_reason()
        if out_of_budget:
            break

        budget.consume()
        label = model or "(mặc định)"
        provider = make_provider(
            credential.provider,
            api_key=credential.api_key.strip(),
            base_url=get_settings().openrouter_base_url if credential.provider == "openrouter" else None,
            default_model=model,
        )
        started = time.monotonic()
        try:
            response = provider.complete(list(messages), model=model, temperature=temperature)
        except Exception as exc:
            # Thông báo lỗi của SDK có thể chứa lại API key -> chỉ đưa ra mã HTTP đã được diễn giải.
            described = describe_provider_error(credential.provider, exc, model=model)
            errors.append(described)
            logger.warning("provider.user_credential_failed %s", described)
            console_log.llm_attempt(provider=credential.provider, model=label, ok=False, note=described)
            if _status_code_of(exc) in _KEY_LEVEL_STATUSES:
                break
            continue

        latency_ms = int((time.monotonic() - started) * 1000)
        text = (response.text or "").strip()
        if not text:
            errors.append(f"{credential.provider}/{label}: trả về nội dung rỗng")
            console_log.llm_attempt(provider=credential.provider, model=label, ok=False, note="nội dung rỗng")
            continue

        logger.info(
            "provider.selected provider=%s model=%s latency_ms=%d source=user_credential",
            credential.provider, label, latency_ms,
        )
        console_log.llm_attempt(provider=credential.provider, model=label, ok=True, latency_ms=latency_ms)
        return CompletionResult(text=text, provider=credential.provider, model=label)

    if out_of_budget:
        logger.warning("provider.budget_exhausted %s source=user_credential", out_of_budget)
        errors.append(f"dừng sớm: {out_of_budget}")

    raise NoProviderConfiguredError("Gọi thất bại -> " + " | ".join(errors))
