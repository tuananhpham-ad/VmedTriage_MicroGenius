"""Gọi model cho part 3: đi qua `provider_router`, đếm chi phí, và KHÔNG bao giờ hạ chất lượng ngầm.

VÌ SAO KHÔNG GỌI GEMINI TRẦN: `provider_router` đã có sẵn xoay vòng model, fallback provider, trần
thời gian và số lượt cho một request. Gọi SDK trần là dựng lại tất cả những thứ đó, tệ hơn, ở một
chỗ nữa.

ĐỊNH TUYẾN THEO TỪNG BƯỚC, KHÔNG THEO CẢ TẦNG. Ba bước dùng model của part 3 có hình dạng rủi ro khác
hẳn nhau: tách claim sai thì không guard nào bắt được, chấm verdict sai thì cả thiết kế mất lớp guard
ngữ nghĩa duy nhất, còn diễn giải sai thì guard 5 chặn được bằng so chuỗi. Vì thế mỗi bước mang một
`role` riêng và có thể chạy provider khác nhau - bước nào trượt cổng lọc chất lượng thì CHỈ bước đó
quay về provider đắt hơn.

HẾT QUOTA THÌ RAISE, KHÔNG ÂM THẦM TRẢ OUTPUT KÉM. `provider_router.complete` đã raise
`NoProviderConfiguredError` khi mọi provider đều lỗi; module này không nuốt nó. Người gọi ở tầng trên
(`service.decide_for_case`) mới là chỗ quyết định "bỏ phần trích nguồn của ca này" - và khi đó nó ghi
log, chứ không phải lặng lẽ trả một đoạn văn nghèo hơn mà không ai biết.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

from src.services.infra import provider_router
from src.services.infra.json_output import parse_json_object

logger = logging.getLogger("vmedtriage.source_support")


class SourceSupportLLMError(RuntimeError):
    """Bước dùng model của part 3 không cho ra JSON hợp lệ sau khi đã thử sửa."""


@dataclass
class CostMeter:
    """Sổ chi phí của MỘT ca. Ghi vào output để đây là số đo được, không phải số ước.

    `provider_calls` tách theo provider vì fallback theo từng bước là có thật: không nhìn số này thì
    không biết đoạn diễn giải vừa rồi do model nào viết."""

    llm_calls: int = 0
    input_chars: int = 0
    output_chars: int = 0
    embed_tokens: int = 0
    web_searches: int = 0
    provider_calls: dict[str, int] = field(default_factory=dict)

    def record_call(self, provider: str, prompt: str, output: str) -> None:
        self.llm_calls += 1
        self.input_chars += len(prompt)
        self.output_chars += len(output)
        self.provider_calls[provider] = self.provider_calls.get(provider, 0) + 1

    @property
    def input_tokens(self) -> int:
        """Ước theo ~4 ký tự/token. Gọi thẳng là ƯỚC: router không trả về usage thật của provider."""
        return self.input_chars // 4

    @property
    def output_tokens(self) -> int:
        return self.output_chars // 4


def call_json(
    *,
    system_prompt: str,
    user_prompt: str,
    schema: type[BaseModel],
    role: str,
    meter: CostMeter | None = None,
    temperature: float = 0.0,
) -> BaseModel:
    """Một lượt gọi model trả JSON, đã validate theo `schema`. Raise nếu không đạt.

    MỘT LẦN SỬA, KHÔNG PHẢI VÒNG LẶP RETRY: gửi lại y nguyên ở `temperature=0` sẽ nhận lại y nguyên
    câu trả lời hỏng, nên lượt thứ hai phải mang theo CHÍNH lỗi validate để model biết sửa gì. Quá đó
    thì raise - đốt thêm lượt gọi cho cùng một lỗi là tốn quota để đổi lấy cùng một kết quả."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    problem = ""
    for attempt in range(2):
        result = provider_router.complete(messages, temperature=temperature, role=role)
        if meter is not None:
            meter.record_call(result.provider, system_prompt + user_prompt, result.text)
        try:
            return schema.model_validate(parse_json_object(result.text))
        except (ValidationError, ValueError, json.JSONDecodeError) as error:
            problem = str(error)
            logger.warning(
                "source_support.json_rejected role=%s provider=%s attempt=%s reason=%s",
                role, result.provider, attempt + 1, type(error).__name__,
            )
            if attempt == 0:
                # Chỉ đưa lại MÔ TẢ LỖI, tuyệt đối không gợi ý nội dung lâm sàng nào - cùng nguyên tắc
                # với `deepseek_extractor.REPAIR_PROMPT`. Gợi ý nội dung là tự tay bịa hộ model.
                messages = messages[:2] + [
                    {"role": "assistant", "content": result.text},
                    {"role": "user", "content": _REPAIR_PROMPT.format(errors=problem)},
                ]
    raise SourceSupportLLMError(f"Bước {role} không trả được JSON hợp lệ: {problem}")


_REPAIR_PROMPT = """JSON của bạn bị bộ kiểm tra từ chối. Lỗi ghi nhận được:
{errors}

Trả lại DUY NHẤT một JSON object đã sửa đúng schema. Không thêm lời giải thích, không thêm trường mới,
và không đổi nội dung lâm sàng - chỉ sửa đúng chỗ bị báo lỗi."""
