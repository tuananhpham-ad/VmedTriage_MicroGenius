from __future__ import annotations

from src.config import get_settings
from src.providers.openai_provider import OpenAIProvider


class DeepSeekProvider(OpenAIProvider):
    """DeepSeek uses an OpenAI-compatible Chat Completions surface."""

    def __init__(self, *, api_key: str | None = None) -> None:
        settings = get_settings()
        super().__init__(
            api_key_env="DEEPSEEK_API_KEY",
            api_key=api_key,
            base_url=settings.deepseek_base_url,
            default_model=settings.deepseek_model_name,
        )
