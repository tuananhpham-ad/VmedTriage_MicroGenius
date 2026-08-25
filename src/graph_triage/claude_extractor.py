"""Claude (Anthropic) JSON extraction with validation, retry, and no label leakage.

Drop-in replacement for `DeepSeekExtractor` (same `patient_graph_v1` contract, same
retry/repair loop) - only the API client differs, since DeepSeek account ran out of
balance (xem `docs/eval/03_track2_live_trace_review.md` muc 3.1)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

from src.config import get_settings
from src.graph_triage.deepseek_extractor import MAX_OUTPUT_TOKENS, REPAIR_PROMPT, SYSTEM_PROMPT, FatalExtractionError
from src.graph_triage.graph_schema import ClinicalGraph, validate_provenance

# Anthropic không có mã lỗi "insufficient balance" riêng như DeepSeek (402) - hết credit trả về
# 400 invalid_request_error kèm message nhắc "credit balance". Auth/permission thì vẫn theo status
# code chuẩn, nên vẫn coi là fatal ngay không cần xem message.
_FATAL_STATUS_CODES = {401: "the API key was rejected", 403: "the API key is not allowed to use this model"}
_CREDIT_BALANCE_MARKER = "credit balance"


def _strip_markdown_fence(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
    return text.strip()


@dataclass
class ClaudeExtractor:
    model: str | None = None
    max_tokens: int = 4000
    retries: int = 4

    def __post_init__(self) -> None:
        # Credential đọc qua `get_settings()` chứ không phải `os.environ` trực tiếp - giữ đúng quy
        # ước của `DeepSeekExtractor.__post_init__`.
        from anthropic import Anthropic

        settings = get_settings()
        if not settings.anthropic_api_key:
            raise RuntimeError("Set ANTHROPIC_API_KEY before running graph extraction.")
        self.model = self.model or settings.anthropic_model_name
        if settings.anthropic_base_url:
            # Token của endpoint tương thích Anthropic bên thứ 3 (proxy) - dùng `auth_token` (Bearer)
            # thay vì `api_key` (x-api-key), đúng như ANTHROPIC_BASE_URL/ANTHROPIC_AUTH_TOKEN của
            # Claude Code CLI.
            self.client = Anthropic(auth_token=settings.anthropic_api_key, base_url=settings.anthropic_base_url)
        else:
            self.client = Anthropic(api_key=settings.anthropic_api_key)

    def extract(self, patient_text: str) -> ClinicalGraph:
        from anthropic import APIStatusError

        errors: list[str] = []
        messages: list[dict[str, str]] = [
            {"role": "user", "content": f"Patient report:\n{patient_text}"},
        ]
        max_tokens = self.max_tokens
        for attempt in range(self.retries):
            content = None
            try:
                response = self.client.messages.create(
                    model=self.model,
                    system=SYSTEM_PROMPT,
                    messages=messages,
                    temperature=0,
                    max_tokens=max_tokens,
                )
                content = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
                if response.stop_reason == "max_tokens":
                    content = None  # Truncated JSON is useless as a repair starting point.
                    truncated_budget, max_tokens = max_tokens, min(max_tokens * 2, MAX_OUTPUT_TOKENS)
                    raise ValueError(f"Claude output hit max_tokens={truncated_budget}; the JSON is truncated.")
                if not content:
                    raise ValueError("Claude returned empty JSON content.")
                graph = ClinicalGraph.model_validate(json.loads(_strip_markdown_fence(content)))
                validate_provenance(graph, patient_text)
                return graph
            except APIStatusError as error:
                # Hết tiền hoặc sai key thì mọi ca còn lại cũng trượt y hệt - dừng hẳn, đừng đốt retry.
                is_credit_balance = error.status_code == 400 and _CREDIT_BALANCE_MARKER in str(error).lower()
                reason = _FATAL_STATUS_CODES.get(error.status_code) or (
                    "the Anthropic account has insufficient credit balance" if is_credit_balance else None
                )
                if reason:
                    raise FatalExtractionError(f"Claude returned HTTP {error.status_code}: {reason}. Retrying cannot help.") from error
                errors.append(f"attempt {attempt + 1}: {error}")
                if attempt + 1 >= self.retries:
                    break
                time.sleep(2 ** attempt)
            except Exception as error:  # API và schema error đều retry.
                errors.append(f"attempt {attempt + 1}: {error}")
                if attempt + 1 >= self.retries:
                    break
                # Gửi lại y nguyên ở temperature=0 sẽ nhận lại y nguyên câu trả lời hỏng - các lần thử
                # đều trượt cùng một lỗi, tốn tiền nhiều lần. Đưa chính lỗi validate ngược lại để model
                # sửa. Chỉ thêm mô tả lỗi, KHÔNG gợi ý nội dung lâm sàng nào.
                if content:
                    messages = messages[:1] + [
                        {"role": "assistant", "content": content},
                        {"role": "user", "content": REPAIR_PROMPT.format(errors="\n".join(f"- {message}" for message in errors))},
                    ]
                time.sleep(2 ** attempt)
        raise RuntimeError("Extraction failed after retries: " + " | ".join(errors))
