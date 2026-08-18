from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import Any

from src.config import get_settings
from src.providers.base import ModelResponse, ToolCall


class OpenAIProvider:
    """OpenAI Chat Completions provider with normalized tool_calls output."""

    def __init__(
        self,
        *,
        api_key_env: str = "OPENAI_API_KEY",
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str | None = None,
    ) -> None:
        self.api_key_env = api_key_env
        # Key truyền tường minh (vd key riêng của người đang test). None -> đọc env như trước.
        # Bắt buộc phải có đường truyền tường minh: os.environ là biến TOÀN PROCESS, nếu mỗi
        # request ghi key của mình vào đó thì hai người test song song sẽ đè key lên nhau.
        self.api_key = api_key
        self.base_url = base_url
        self.default_model = default_model or get_settings().openai_model_name

    def complete(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        *,
        model: str | None = None,
        temperature: float = 0.0,
        tool_choice: Any | None = None,
    ) -> ModelResponse:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install live provider dependency first: pip install openai") from exc

        api_key = self.api_key or os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing API key env var: {self.api_key_env}")

        client = OpenAI(api_key=api_key, base_url=self.base_url)
        kwargs: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice

        resp = client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message

        calls: list[ToolCall] = []
        for call in msg.tool_calls or []:
            args = json.loads(call.function.arguments or "{}")
            calls.append(ToolCall(name=call.function.name, args=args))
        return ModelResponse(text=msg.content, tool_calls=calls, raw=resp)

    def complete_stream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.0,
    ) -> Iterator[str]:
        """Trả text theo từng mẩu ngay khi model sinh ra, thay vì đợi trọn câu trả lời.

        CỐ Ý không nhận `tools`/`tool_choice`: đường streaming chỉ phục vụ bước diễn đạt câu hỏi cho
        người bệnh - thứ duy nhất được hiển thị dần. Trích xuất field vẫn đi qua `complete()` vì nó
        trả JSON, mà JSON dở dang thì không parse được, streaming không giúp gì.

        DeepSeek và OpenRouter kế thừa nguyên hàm này: cả ba đều là Chat Completions của OpenAI.
        """
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install live provider dependency first: pip install openai") from exc

        api_key = self.api_key or os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing API key env var: {self.api_key_env}")

        client = OpenAI(api_key=api_key, base_url=self.base_url)
        stream = client.chat.completions.create(
            model=model or self.default_model,
            messages=messages,
            temperature=temperature,
            stream=True,
        )
        for chunk in stream:
            for choice in chunk.choices or []:
                piece = getattr(choice.delta, "content", None)
                if piece:
                    yield piece
