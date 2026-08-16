from __future__ import annotations

import os

from src.providers.openai_provider import OpenAIProvider


class OpenRouterProvider(OpenAIProvider):
    """OpenRouter uses an OpenAI-compatible Chat Completions surface."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str | None = None,
    ) -> None:
        # `base_url`/`default_model` truyền tường minh là đường đi CHÍNH; os.getenv chỉ còn là
        # phương án dự phòng khi adapter được dựng trực tiếp ngoài `provider_router` (script, test
        # tay). Lý do: os.environ là biến TOÀN PROCESS - nếu router ghi model vào đó rồi mới dựng
        # adapter, hai request song song sẽ đè model của nhau đúng trong khe giữa ghi và đọc.
        super().__init__(
            api_key_env="OPENROUTER_API_KEY",
            api_key=api_key,
            base_url=base_url or os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            default_model=default_model or os.getenv("OPENROUTER_MODEL_NAME", "openai/gpt-4o-mini"),
        )
