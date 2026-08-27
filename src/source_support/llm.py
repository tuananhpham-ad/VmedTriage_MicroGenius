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
from collections.abc import Callable
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
    result = provider_router.complete(messages, temperature=temperature, role=role)
    if meter is not None:
        meter.record_call(result.provider, system_prompt + user_prompt, result.text)
    try:
        return schema.model_validate(parse_json_object(result.text))
    except (ValidationError, ValueError, json.JSONDecodeError) as error:
        logger.warning(
            "source_support.json_rejected role=%s provider=%s attempt=1 reason=%s",
            role, result.provider, type(error).__name__,
        )
        return _repair(
            messages=messages, previous=result.text, problem=str(error), schema=schema,
            role=role, meter=meter, temperature=temperature,
            meter_prompt=system_prompt + user_prompt,
        )


class StreamedFieldDecoder:
    """Bóc dần MỘT trường chuỗi ra khỏi một JSON đang được stream về.

    VÌ SAO BÓC, THAY VÌ ĐỔI PROMPT SANG VĂN XUÔI. Bước 7 trả JSON vì Guard 5a cần `used_markers` và
    cần ranh giới rõ giữa đoạn văn với phần siêu dữ liệu; bỏ JSON để stream cho tiện là đánh đổi một
    lớp guard lấy một hiệu ứng hiển thị. Ở đây JSON giữ nguyên - ta chỉ đọc ké phần thân của trường
    trong lúc nó đang được viết ra, còn validate vẫn chạy trên KHỐI JSON HOÀN CHỈNH y như cũ.

    KHÔNG DÙNG PARSER JSON TĂNG DẦN. Việc cần làm hẹp hơn nhiều: đúng một trường, kiểu chuỗi, ở tầng
    ngoài cùng. Quét chuỗi bằng tay cho việc đó là vài chục dòng đọc hết được, còn kéo về một parser
    tăng dần là thêm phụ thuộc cho một bài toán ta không có.

    HAI THỨ PHẢI CHỊU ĐƯỢC, vì mẩu stream cắt ở vị trí tuỳ ý:

    1. Mẩu kết thúc GIỮA một chuỗi thoát (dấu gạch chéo ngược đứng lẻ, hoặc một escape unicode mới
       viết được nửa). Decode ngay sẽ ném lỗi, nên phần đuôi dở dang bị cắt lại và chờ mẩu sau.
    2. Trường chưa xuất hiện trong buffer - trả về rỗng. Đó là trạng thái bình thường của mấy mẩu
       đầu tiên chứ không phải lỗi.
    """

    def __init__(self, field_name: str) -> None:
        self._name = json.dumps(field_name)
        self._buffer = ""
        self._emitted = 0

    def feed(self, piece: str) -> str:
        """Nạp một mẩu thô, trả về phần chữ MỚI của trường (rỗng nếu chưa có gì mới)."""
        self._buffer += piece
        decoded = self._decode_so_far()
        if len(decoded) <= self._emitted:
            # `<=` chứ không `<`: một stream chỉ nối thêm thì không bao giờ ngắn đi, nhưng nếu có thì
            # phát ra một đoạn "lùi" còn khó hiểu cho người đọc hơn là im lặng.
            return ""
        fresh = decoded[self._emitted:]
        self._emitted = len(decoded)
        return fresh

    def _decode_so_far(self) -> str:
        start = self._buffer.find(self._name)
        if start < 0:
            return ""
        colon = self._buffer.find(":", start + len(self._name))
        if colon < 0:
            return ""
        opening = self._buffer.find('"', colon + 1)
        if opening < 0:
            return ""

        body: list[str] = []
        index = opening + 1
        while index < len(self._buffer):
            char = self._buffer[index]
            if char == "\\":
                body.append(self._buffer[index:index + 2])
                index += 2
                continue
            if char == '"':
                break
            body.append(char)
            index += 1

        raw = "".join(body)
        while raw:
            try:
                return json.loads('"' + raw + '"')
            except ValueError:
                # Đuôi dở dang: bỏ một ký tự rồi thử lại. Thực tế chạy tối đa 5 lượt - escape unicode
                # là dạng dài nhất JSON có.
                raw = raw[:-1]
        return ""


def call_json_streaming(
    *,
    system_prompt: str,
    user_prompt: str,
    schema: type[BaseModel],
    role: str,
    stream_field: str,
    on_token: Callable[[str], None],
    meter: CostMeter | None = None,
    temperature: float = 0.0,
) -> BaseModel:
    """Như `call_json` nhưng phát dần phần thân của `stream_field` ra `on_token` trong lúc chờ.

    HỢP ĐỒNG VỚI NGƯỜI GỌI, phải đọc trước khi dùng: những gì đi qua `on_token` là BẢN NHÁP CHƯA QUA
    GUARD. Bước 7 có Guard 5a/5b chạy SAU khi đã có đủ văn bản, và khi guard chặn thì cả đoạn bị thay
    bằng bản do code dựng. Người gọi vì thế phải hiển thị dòng chảy này ĐÚNG NHƯ một bản nháp và luôn
    vẽ lại theo giá trị trả về cuối cùng - để chữ đã stream nằm lại trên màn hình như kết quả là đúng
    thứ `explain.py` tồn tại để chặn.

    KHÔNG STREAM LƯỢT SỬA. Lượt hai mang theo lỗi validate và gần như luôn viết lại từ đầu; phát tiếp
    vào cùng một dòng sẽ nối hai bản văn thành một đoạn vô nghĩa. Lượt sửa quay về `complete()` một
    cục - hỏng ở lượt đầu thì mất hiệu ứng chữ chạy, đổi lấy một kết quả không lẫn lộn.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    decoder = StreamedFieldDecoder(stream_field)
    pieces: list[str] = []
    provider_used = "(stream)"

    def _note_provider(provider: str, _model: str | None) -> None:
        nonlocal provider_used
        provider_used = provider

    try:
        for piece in provider_router.complete_stream(
            messages, temperature=temperature, role=role, on_provider=_note_provider,
        ):
            pieces.append(piece)
            fresh = decoder.feed(piece)
            if fresh:
                on_token(fresh)
    except Exception as error:
        # Stream hỏng KHÔNG phải bước 7 hỏng: rơi về đường gọi một cục, chỉ mất hiệu ứng chữ chạy.
        logger.warning(
            "source_support.stream_failed role=%s reason=%s: %s", role, type(error).__name__, error,
        )
        return call_json(
            system_prompt=system_prompt, user_prompt=user_prompt, schema=schema,
            role=role, meter=meter, temperature=temperature,
        )

    text = "".join(pieces)
    if meter is not None:
        meter.record_call(provider_used, system_prompt + user_prompt, text)
    try:
        return schema.model_validate(parse_json_object(text))
    except (ValidationError, ValueError, json.JSONDecodeError) as error:
        logger.warning(
            "source_support.json_rejected role=%s provider=%s attempt=1 mode=stream reason=%s",
            role, provider_used, type(error).__name__,
        )
        return _repair(
            messages=messages, previous=text, problem=str(error), schema=schema,
            role=role, meter=meter, temperature=temperature,
            meter_prompt=system_prompt + user_prompt,
        )


def _repair(
    *,
    messages: list[dict[str, str]],
    previous: str,
    problem: str,
    schema: type[BaseModel],
    role: str,
    meter: CostMeter | None,
    temperature: float,
    meter_prompt: str,
) -> BaseModel:
    """Lượt sửa DUY NHẤT. Tách ra để đường một-cục và đường stream dùng chung đúng một prompt sửa:
    hai bản sao của prompt này sẽ trôi ra xa nhau, mà đây là prompt phải giữ được lời hứa "không gợi
    ý nội dung lâm sàng" ở cả hai đường."""
    repair_messages = messages[:2] + [
        {"role": "assistant", "content": previous},
        # Chỉ đưa lại MÔ TẢ LỖI, tuyệt đối không gợi ý nội dung lâm sàng nào - cùng nguyên tắc với
        # `deepseek_extractor.REPAIR_PROMPT`. Gợi ý nội dung là tự tay bịa hộ model.
        {"role": "user", "content": _REPAIR_PROMPT.format(errors=problem)},
    ]
    result = provider_router.complete(repair_messages, temperature=temperature, role=role)
    if meter is not None:
        meter.record_call(result.provider, meter_prompt, result.text)
    try:
        return schema.model_validate(parse_json_object(result.text))
    except (ValidationError, ValueError, json.JSONDecodeError) as error:
        logger.warning(
            "source_support.json_rejected role=%s provider=%s attempt=2 reason=%s",
            role, result.provider, type(error).__name__,
        )
        raise SourceSupportLLMError(f"Bước {role} không trả được JSON hợp lệ: {error}") from error


_REPAIR_PROMPT = """JSON của bạn bị bộ kiểm tra từ chối. Lỗi ghi nhận được:
{errors}

Trả lại DUY NHẤT một JSON object đã sửa đúng schema. Không thêm lời giải thích, không thêm trường mới,
và không đổi nội dung lâm sàng - chỉ sửa đúng chỗ bị báo lỗi."""
