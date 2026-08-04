from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from src.config import get_settings

LLMProvider = Literal["openai", "deepseek", "gemini"]


def _provider_order(configured_provider: str, configured_order: str) -> list[LLMProvider]:
    if configured_provider != "auto":
        return [configured_provider]  # type: ignore[list-item]

    providers: list[LLMProvider] = []
    for raw_provider in configured_order.split(","):
        provider = raw_provider.strip().lower()
        if provider in {"openai", "deepseek", "gemini"} and provider not in providers:
            providers.append(provider)  # type: ignore[arg-type]
    return providers or ["openai", "deepseek", "gemini"]


def get_llm() -> BaseChatModel:
    settings = get_settings()
    missing_keys: list[str] = []

    for provider in _provider_order(settings.llm_provider, settings.llm_provider_order):
        if provider == "openai":
            if not settings.openai_api_key:
                missing_keys.append("OPENAI_API_KEY")
                continue
            return ChatOpenAI(
                model=settings.model_name or settings.openai_model_name,
                api_key=settings.openai_api_key,
                temperature=settings.llm_temperature,
            )

        if provider == "deepseek":
            if not settings.deepseek_api_key:
                missing_keys.append("DEEPSEEK_API_KEY")
                continue
            return ChatOpenAI(
                model=settings.model_name or settings.deepseek_model_name,
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
                temperature=settings.llm_temperature,
            )

        if provider == "gemini":
            if not settings.gemini_api_key:
                missing_keys.append("GEMINI_API_KEY or GOOGLE_API_KEY")
                continue
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
            except ImportError as exc:
                raise RuntimeError("Gemini provider requires `langchain-google-genai` to be installed.") from exc

            return ChatGoogleGenerativeAI(
                model=settings.model_name or settings.gemini_model_name,
                google_api_key=settings.gemini_api_key,
                temperature=settings.llm_temperature,
            )

    raise RuntimeError(
        "No LLM provider is configured. Set one of these env vars in provider order "
        f"({settings.llm_provider_order}): {', '.join(dict.fromkeys(missing_keys))}."
    )
