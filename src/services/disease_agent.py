"""Agent hỏi-đáp dùng chung cho MỌI checklist theo bệnh (mục 10 solution design:
`_guidance/vmedtriage_solution_design_review.md`).

Khác `intake_agent.py` (hardcode 1 bộ trường chung cho luồng demo), agent ở đây nhận một
`DiseaseChecklist` bất kỳ (nạp qua `disease_checklist.load_checklist`) nên dùng lại được cho nhiều
bệnh mà không phải viết agent riêng cho từng bệnh.

Ranh giới an toàn giữ nguyên như `IntakeAgent`:
- LLM CHỈ làm hai việc: (1) trích xuất thông tin đã có trong câu trả lời vào checklist, (2) diễn đạt
  câu hỏi tiếp theo cho tự nhiên. KHÔNG chẩn đoán bệnh, KHÔNG đề xuất mức ưu tiên.
- Phiếu tóm tắt cuối (`build_summary_text`) là template DETERMINISTIC, không qua LLM - tránh việc LLM
  "diễn giải thêm" hoặc bịa thông tin không có trong answers khi tổng hợp tóm tắt.
- Nếu LLM lỗi/chưa cấu hình, extract/next_question rơi về fallback deterministic, báo qua `llm_used`.
"""

from __future__ import annotations

import json
import logging
import re

from src.services import provider_router
from src.services.disease_checklist import ChecklistField, DiseaseChecklist, missing_required_keys

logger = logging.getLogger("vmedtriage.disease_agent")

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_json_object(raw: str) -> dict:
    """Bóc JSON object khỏi output LLM (chịu được ```json fence và chữ thừa xung quanh)."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = _JSON_BLOCK_RE.search(cleaned)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    return parsed if isinstance(parsed, dict) else {}


_EXTRACTION_SYSTEM = """Bạn là bộ trích xuất thông tin y tế cho một hệ thống phân loại mức độ ưu tiên.

NHIỆM VỤ DUY NHẤT: đọc tin nhắn của người dùng và điền vào các trường checklist của "{disease_label}".

QUY TẮC BẮT BUỘC:
- CHỈ trích xuất thông tin ĐÃ CÓ trong tin nhắn. TUYỆT ĐỐI KHÔNG suy diễn, KHÔNG phỏng đoán.
- Nếu tin nhắn không nói gì về một trường, để giá trị null cho trường đó.
- KHÔNG chẩn đoán bệnh. KHÔNG đề xuất điều trị. KHÔNG đánh giá mức độ nguy hiểm.
- Giữ nguyên cách diễn đạt của người bệnh, chỉ chuẩn hoá nhẹ (vd "hôm kia" -> "2 ngày trước").
- Chỉ trả về MỘT JSON object, không kèm giải thích.

CÁC TRƯỜNG CẦN TRÍCH XUẤT:
{field_specs}

Định dạng trả về: {{"<key>": <string hoặc null>, ...}}"""


_CORRECTION_SYSTEM = """Bạn là bộ xử lý ĐÍNH CHÍNH thông tin cho một hệ thống y tế.

Người dùng đã xem phiếu tóm tắt dưới đây và nói rằng có chỗ CHƯA ĐÚNG.

PHIẾU TÓM TẮT HIỆN TẠI:
{current_summary}

NHIỆM VỤ: đọc câu đính chính của người dùng và chỉ trả về NHỮNG TRƯỜNG HỌ ĐANG SỬA.

QUY TẮC BẮT BUỘC:
- CHỈ trả về trường mà người dùng nhắc đến rõ ràng trong câu đính chính.
- TUYỆT ĐỐI KHÔNG trả về trường họ không nhắc tới, kể cả khi có thể diễn đạt lại hay hơn. Trường
  không được nhắc tới phải giữ nguyên giá trị cũ, nên KHÔNG đưa vào kết quả.
- KHÔNG chẩn đoán bệnh, KHÔNG suy diễn thêm thông tin.
- Chỉ trả về MỘT JSON object, không kèm giải thích. Nếu không sửa gì, trả về {{}}.

CÁC TRƯỜNG HỢP LỆ:
{field_specs}"""


class DiseaseQAAgent:
    """Bọc LLM cho các tác vụ hỏi-đáp theo checklist của một bệnh cụ thể.

    Chạy qua `provider_router` nên dùng được với mọi provider đã cấu hình API key trong `.env`
    (gemini/deepseek/openai/anthropic/openrouter), tự fallback nếu provider đầu lỗi.
    """

    def __init__(self, checklist: DiseaseChecklist) -> None:
        self.checklist = checklist

    @property
    def llm_available(self) -> bool:
        return bool(provider_router.available_providers())

    def extract(self, message: str, current_answers: dict[str, str | None]) -> tuple[dict[str, str], bool]:
        """Trích xuất field từ tin nhắn. Trả (field mới trích được, có dùng LLM hay không).

        Chỉ trả về các trường CHƯA có giá trị - không ghi đè câu trả lời trước đó.
        """
        system_prompt = _EXTRACTION_SYSTEM.format(
            disease_label=self.checklist.disease_label, field_specs=self._field_specs()
        )
        parsed = self._invoke_json(system_prompt, message)
        if parsed is None:
            return self._extract_fallback(message, current_answers), False
        return self._collect(parsed, skip_existing=current_answers), True

    def extract_correction(
        self,
        message: str,
        current_answers: dict[str, str | None],
    ) -> tuple[dict[str, str], bool]:
        """Trích xuất phần người dùng đang ĐÍNH CHÍNH trên phiếu tóm tắt (được phép ghi đè)."""
        current_summary = (
            "\n".join(
                f"- {self.checklist.fields_by_key[key].label} ({key}): {value}"
                for key, value in current_answers.items()
                if value
            )
            or "(chưa có thông tin nào)"
        )
        system_prompt = _CORRECTION_SYSTEM.format(current_summary=current_summary, field_specs=self._field_specs())
        parsed = self._invoke_json(system_prompt, message)
        if parsed is None:
            # Không đoán mò khi sửa: thà không đổi gì còn hơn ghi đè sai lên dữ liệu đã có.
            return {}, False
        return self._collect(parsed, skip_existing=None), True

    def next_question(
        self,
        conversation: list[dict[str, str]],
        answers: dict[str, str | None],
    ) -> tuple[str, list[str], bool]:
        """Sinh câu hỏi tiếp theo. Trả (câu hỏi, các field đang nhắm tới, có dùng LLM hay không)."""
        targets = missing_required_keys(self.checklist, answers)
        if not targets:
            return "", [], False

        focus_keys = targets[:2]
        focus_fields = [self.checklist.fields_by_key[key] for key in focus_keys]

        collected = (
            "\n".join(f"- {self.checklist.fields_by_key[key].label}: {value}" for key, value in answers.items() if value)
            or "(chưa có thông tin nào)"
        )
        wanted = "\n".join(f"- {item.label}: {item.hint}" for item in focus_fields)
        history = "\n".join(
            f"{'Người dùng' if turn['role'] == 'user' else 'Trợ lý'}: {turn['content']}" for turn in conversation[-6:]
        )

        prompt = f"""Bạn là trợ lý y tế đang hỏi thông tin ban đầu của người dùng về "{self.checklist.disease_label}" qua ứng dụng chat.

THÔNG TIN ĐÃ THU THẬP:
{collected}

THÔNG TIN CÒN THIẾU CẦN HỎI LƯỢT NÀY:
{wanted}

HỘI THOẠI GẦN ĐÂY:
{history}

Hãy viết MỘT câu hỏi tiếng Việt tự nhiên, ngắn gọn, lịch sự để hỏi phần còn thiếu ở trên.

QUY TẮC BẮT BUỘC:
- TUYỆT ĐỐI KHÔNG chẩn đoán bệnh, KHÔNG nhận định tình trạng nguy hiểm, KHÔNG khuyên điều trị.
- Không lặp lại câu hỏi đã hỏi trong hội thoại gần đây bằng cùng một cách diễn đạt.
- Không hỏi lại thông tin người dùng đã trả lời.
- Chỉ trả về đúng câu hỏi, không thêm lời dẫn hay giải thích."""

        try:
            question = provider_router.complete([{"role": "user", "content": prompt}]).text.strip().strip('"')
        except Exception as exc:
            logger.warning("disease_agent.question_failed reason=%s detail=%s", type(exc).__name__, exc)
            return self._question_fallback(focus_fields), focus_keys, False

        if not question:
            return self._question_fallback(focus_fields), focus_keys, False
        return question, focus_keys, True

    def build_summary_text(self, answers: dict[str, str | None]) -> str:
        """Tóm tắt tình trạng bệnh - deterministic, KHÔNG qua LLM (không được bịa/diễn giải thêm)."""
        lines = [f"Tóm tắt tình trạng bệnh - {self.checklist.disease_label}:"]
        for item in self.checklist.fields:
            value = answers.get(item.key)
            display = value.strip() if value and value.strip() else "(chưa cung cấp)"
            lines.append(f"- {item.label}: {display}")
        return "\n".join(lines)

    # --- internals ---------------------------------------------------------------------------

    def _field_specs(self) -> str:
        return "\n".join(f"- {item.key} ({item.label}): {item.hint}" for item in self.checklist.fields)

    def _invoke_json(self, system_prompt: str, user_message: str) -> dict | None:
        try:
            result = provider_router.complete(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ]
            )
            return _parse_json_object(result.text)
        except Exception as exc:
            logger.warning("disease_agent.extract_failed reason=%s detail=%s", type(exc).__name__, exc)
            return None

    def _collect(self, parsed: dict, skip_existing: dict[str, str | None] | None) -> dict[str, str]:
        """Lọc output LLM về đúng các key hợp lệ, bỏ null/rỗng, phẳng hoá list."""
        extracted: dict[str, str] = {}
        fields_by_key = self.checklist.fields_by_key
        for key, value in parsed.items():
            if key not in fields_by_key or value in (None, "", "null"):
                continue
            if skip_existing is not None and skip_existing.get(key):
                continue  # đã có -> không ghi đè
            text = ", ".join(str(item) for item in value) if isinstance(value, list) else str(value)
            if text.strip():
                extracted[key] = text.strip()
        return extracted

    def _extract_fallback(self, message: str, current_answers: dict[str, str | None]) -> dict[str, str]:
        """Fallback tối giản khi LLM không khả dụng: gán nguyên tin nhắn cho trường thiếu đầu tiên."""
        cleaned = (message or "").strip()
        if not cleaned:
            return {}
        missing = missing_required_keys(self.checklist, current_answers)
        return {missing[0]: cleaned} if missing else {}

    def _question_fallback(self, focus_fields: list[ChecklistField]) -> str:
        labels = " và ".join(item.label.lower() for item in focus_fields)
        return f"Bạn vui lòng cho biết {labels} giúp mình nhé?"
