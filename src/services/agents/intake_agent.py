"""Intake Agent cho demo hỏi-đáp: LLM trích xuất checklist + sinh câu hỏi tiếp theo tự nhiên.

Ranh giới an toàn (giữ đúng nguyên tắc đã chốt ở _guidance/vmedtriage_solution_design_review.md):

- LLM CHỈ làm hai việc: (1) trích xuất thông tin đã có trong câu trả lời vào các trường checklist,
  (2) diễn đạt câu hỏi tiếp theo cho tự nhiên. KHÔNG kết luận bệnh, KHÔNG đề xuất mức ưu tiên,
  KHÔNG đưa hướng xử trí.
- Phát hiện red-flag là RULE THUẦN trên văn bản thô (`scan_red_flags`), chạy mỗi lượt, độc lập hoàn
  toàn với LLM. Nếu LLM lỗi/không cấu hình, red-flag vẫn hoạt động.
- Nếu LLM không khả dụng, cả extraction lẫn follow-up đều rơi về fallback deterministic để demo
  không chết - nhưng độ tự nhiên của câu hỏi sẽ giảm (đây là đánh đổi có chủ đích, không im lặng:
  response có cờ `llm_used` để UI hiển thị).
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field

from src.services.checklists.intake_checklist import (
    FIELDS_BY_KEY,
    INTAKE_CHECKLIST,
    ChecklistField,
    missing_optional_keys,
    missing_required_keys,
)
from src.services.infra import provider_router

logger = logging.getLogger("vmedtriage.intake")


# --- Red-flag scan: RULE THUẦN trên text thô, KHÔNG dùng LLM, chạy mỗi lượt ------------------
# Đây là bản demo rút gọn của RedFlagSafetyLayer (src/services/red_flag.py) làm việc trực tiếp trên
# câu chữ bệnh nhân, vì luồng intake này chưa map sang StructuredSymptomData.
RED_FLAG_KEYWORDS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "loss_of_consciousness",
        "Ngất / mất ý thức",
        ("ngất", "bất tỉnh", "mất ý thức", "hôn mê", "lịm đi"),
    ),
    ("seizure", "Co giật", ("co giật", "lên cơn giật", "giật kinh phong")),
    (
        "severe_breathing",
        "Khó thở nặng / tím tái",
        ("không thở được", "khó thở nặng", "tím tái", "thở gấp", "hụt hơi nặng", "thở rít"),
    ),
    (
        "severe_chest_pain",
        "Đau ngực dữ dội",
        ("đau ngực dữ dội", "đau thắt ngực", "đau ngực nhiều", "đau tức ngực dữ dội"),
    ),
    (
        "heavy_bleeding",
        "Chảy máu nặng",
        ("chảy máu nhiều", "máu không cầm", "không cầm được máu", "ra máu ồ ạt", "nôn ra máu", "ho ra máu"),
    ),
    (
        "stroke_signs",
        "Dấu hiệu nghi ngờ đột quỵ",
        ("méo miệng", "lệch mặt", "yếu liệt", "liệt nửa người", "nói khó", "nói ngọng", "tê nửa người"),
    ),
    (
        "altered_consciousness",
        "Li bì / lơ mơ",
        ("li bì", "lơ mơ", "gọi không tỉnh", "không tỉnh táo", "lú lẫn"),
    ),
)


@dataclass(slots=True)
class RedFlagHit:
    code: str
    label: str
    matched_keyword: str


def strip_diacritics(text: str) -> str:
    """Bỏ dấu tiếng Việt để so khớp không phụ thuộc dấu.

    Cần thiết vì người dùng gõ tiếng Việt không dấu rất phổ biến trên điện thoại ("li bi", "ngat",
    "co giat"). Nếu chỉ so khớp bản có dấu thì red-flag sẽ lọt - đây là lỗi an toàn, không phải lỗi
    tiện dụng. `đ` không bị NFD tách nên phải thay tay.
    """
    lowered = (text or "").casefold().replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", lowered)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def scan_red_flags(*texts: str) -> list[RedFlagHit]:
    """Quét red-flag bằng từ khoá. Deterministic, không phụ thuộc LLM.

    Nhận nhiều nguồn text (tin nhắn thô + giá trị field đã trích xuất) vì LLM có thể chuẩn hoá
    "li bi" thành "li bì" khi điền checklist - quét cả hai phía để không bỏ sót.
    """
    haystack = strip_diacritics(" \n ".join(item for item in texts if item))
    hits: list[RedFlagHit] = []
    for code, label, keywords in RED_FLAG_KEYWORDS:
        for keyword in keywords:
            if strip_diacritics(keyword) in haystack:
                hits.append(RedFlagHit(code=code, label=label, matched_keyword=keyword))
                break
    return hits


# --- LLM helpers -----------------------------------------------------------------------------

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


# --- Extraction ------------------------------------------------------------------------------

_EXTRACTION_SYSTEM = """Bạn là bộ trích xuất thông tin y tế cho một hệ thống phân loại mức độ ưu tiên.

NHIỆM VỤ DUY NHẤT: đọc tin nhắn của người dùng và điền vào các trường checklist dưới đây.

QUY TẮC BẮT BUỘC:
- CHỈ trích xuất thông tin ĐÃ CÓ trong tin nhắn. TUYỆT ĐỐI KHÔNG suy diễn, KHÔNG phỏng đoán.
- Nếu tin nhắn không nói gì về một trường, để giá trị null cho trường đó.
- KHÔNG chẩn đoán bệnh. KHÔNG đề xuất điều trị. KHÔNG đánh giá mức độ nguy hiểm.
- Giữ nguyên cách diễn đạt của người bệnh, chỉ chuẩn hoá nhẹ (vd "hôm kia" -> "2 ngày trước").
- Chỉ trả về MỘT JSON object, không kèm giải thích.

CÁC TRƯỜNG CẦN TRÍCH XUẤT:
{field_specs}

Định dạng trả về:
{{"patient_name": <string hoặc null>, "age": <string hoặc null>, ...}}"""


_CORRECTION_SYSTEM = """Bạn là bộ xử lý ĐÍNH CHÍNH thông tin cho một hệ thống y tế.

Người bệnh đã xem phiếu tóm tắt dưới đây và nói rằng có chỗ CHƯA ĐÚNG.

PHIẾU TÓM TẮT HIỆN TẠI:
{current_summary}

NHIỆM VỤ: đọc câu đính chính của người bệnh và chỉ trả về NHỮNG TRƯỜNG HỌ ĐANG SỬA.

QUY TẮC BẮT BUỘC:
- CHỈ trả về trường mà người bệnh nhắc đến rõ ràng trong câu đính chính.
- TUYỆT ĐỐI KHÔNG trả về trường họ không nhắc tới, kể cả khi bạn nghĩ có thể diễn đạt lại hay hơn.
  Trường không được nhắc tới phải giữ nguyên giá trị cũ, nên KHÔNG đưa vào kết quả.
- KHÔNG chẩn đoán bệnh, KHÔNG suy diễn thêm thông tin.
- Chỉ trả về MỘT JSON object, không kèm giải thích. Nếu không sửa gì, trả về {{}}.

CÁC TRƯỜNG HỢP LỆ:
{field_specs}"""


class IntakeAgent:
    """Bọc LLM cho các tác vụ intake, chạy qua provider_router nên dùng được với mọi provider
    đã cấu hình API key (gemini/deepseek/openai/anthropic/openrouter).

    Mọi lỗi LLM đều được nuốt và rơi về fallback deterministic - hàm gọi luôn nhận thêm cờ
    `llm_used` để tầng trên biết và hiển thị cho người dùng, không im lặng.
    """

    def __init__(self, credential: provider_router.LLMCredential | None = None) -> None:
        # Key riêng của người đang test (nếu có). Chỉ giữ in-memory, không ghi log/không trả về API.
        self.credential = credential

    @property
    def llm_available(self) -> bool:
        return bool(self.credential) or bool(provider_router.available_providers())

    @property
    def active_provider(self) -> str | None:
        """Provider sẽ được thử đầu tiên - dùng để hiển thị chế độ đang chạy trên UI."""
        if self.credential:
            return self.credential.provider
        providers = provider_router.available_providers()
        return providers[0] if providers else None

    def _complete(self, messages: list[dict[str, str]]):
        return provider_router.complete(messages, credential=self.credential)

    def extract(self, message: str, current_answers: dict[str, str | None]) -> tuple[dict[str, str], bool]:
        """Trích xuất field từ tin nhắn. Trả (field mới trích được, có dùng LLM hay không).

        Chỉ trả về các trường CHƯA có giá trị - không ghi đè câu trả lời trước đó của người bệnh
        (tránh việc LLM diễn giải lại làm sai lệch thông tin đã xác nhận ở lượt trước).
        """
        field_specs = "\n".join(f"- {item.key} ({item.label}): {item.hint}" for item in INTAKE_CHECKLIST)
        system_prompt = _EXTRACTION_SYSTEM.format(field_specs=field_specs)
        parsed = self._invoke_json(system_prompt, message)
        if parsed is None:
            return self._extract_fallback(message, current_answers), False
        return self._collect(parsed, skip_existing=current_answers), True

    def extract_correction(
        self,
        message: str,
        current_answers: dict[str, str | None],
    ) -> tuple[dict[str, str], bool]:
        """Trích xuất phần người bệnh đang ĐÍNH CHÍNH trên phiếu tóm tắt.

        Khác `extract`: kết quả ĐƯỢC PHÉP ghi đè giá trị cũ, nhưng prompt ràng buộc LLM chỉ trả về
        đúng những trường người bệnh nhắc tới. Nếu dùng lại `extract` với `current_answers={}` thì
        LLM sẽ trích lại cả trường không được sửa và có thể làm nghèo dữ liệu đã có
        (vd "đau bụng" bị ghi đè thành "đau" khi người bệnh chỉ đang sửa tuổi).
        """
        current_summary = "\n".join(
            f"- {FIELDS_BY_KEY[key].label} ({key}): {value}" for key, value in current_answers.items() if value
        ) or "(chưa có thông tin nào)"
        field_specs = "\n".join(f"- {item.key} ({item.label}): {item.hint}" for item in INTAKE_CHECKLIST)
        system_prompt = _CORRECTION_SYSTEM.format(current_summary=current_summary, field_specs=field_specs)

        parsed = self._invoke_json(system_prompt, message)
        if parsed is None:
            # Không đoán mò khi sửa: thà không đổi gì còn hơn ghi đè sai lên dữ liệu đã có.
            return {}, False
        return self._collect(parsed, skip_existing=None), True

    def _invoke_json(self, system_prompt: str, user_message: str) -> dict | None:
        try:
            result = self._complete(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ]
            )
            return _parse_json_object(result.text)
        except Exception as exc:
            logger.warning("intake.extract_failed reason=%s detail=%s", type(exc).__name__, exc)
            return None

    def _collect(self, parsed: dict, skip_existing: dict[str, str | None] | None) -> dict[str, str]:
        """Lọc output LLM về đúng các key hợp lệ, bỏ null/rỗng, phẳng hoá list."""
        extracted: dict[str, str] = {}
        for key, value in parsed.items():
            if key not in FIELDS_BY_KEY or value in (None, "", "null"):
                continue
            if skip_existing is not None and skip_existing.get(key):
                continue  # đã có -> không ghi đè
            text = ", ".join(str(item) for item in value) if isinstance(value, list) else str(value)
            if text.strip():
                extracted[key] = text.strip()
        return extracted

    def next_question(
        self,
        conversation: list[dict[str, str]],
        answers: dict[str, str | None],
    ) -> tuple[str, list[str], bool]:
        """Sinh câu hỏi tiếp theo. Trả (câu hỏi, các field đang nhắm tới, có dùng LLM hay không)."""
        targets = missing_required_keys(answers) or missing_optional_keys(answers)
        if not targets:
            return "", [], False

        # Hỏi tối đa 2 trường một lượt cho tự nhiên, tránh dồn câu hỏi làm người bệnh quá tải.
        focus_keys = targets[:2]
        focus_fields = [FIELDS_BY_KEY[key] for key in focus_keys]

        collected = "\n".join(
            f"- {FIELDS_BY_KEY[key].label}: {value}" for key, value in answers.items() if value
        ) or "(chưa có thông tin nào)"
        wanted = "\n".join(f"- {item.label}: {item.hint}" for item in focus_fields)
        history = "\n".join(
            f"{'Người bệnh' if turn['role'] == 'user' else 'Trợ lý'}: {turn['content']}"
            for turn in conversation[-6:]
        )

        prompt = f"""Bạn là trợ lý y tế đang hỏi thông tin ban đầu của người bệnh qua ứng dụng chat.

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
- Không hỏi lại thông tin người bệnh đã trả lời.
- Chỉ trả về đúng câu hỏi, không thêm lời dẫn hay giải thích."""

        try:
            question = self._complete([{"role": "user", "content": prompt}]).text.strip().strip('"')
        except Exception as exc:
            logger.warning("intake.question_failed reason=%s detail=%s", type(exc).__name__, exc)
            return self._question_fallback(focus_fields), focus_keys, False

        if not question:
            return self._question_fallback(focus_fields), focus_keys, False
        return question, focus_keys, True

    # --- Fallback deterministic (khi LLM không khả dụng) -------------------------------------

    def _extract_fallback(self, message: str, current_answers: dict[str, str | None]) -> dict[str, str]:
        """Fallback tối giản: gán nguyên tin nhắn cho trường bắt buộc đang thiếu đầu tiên.

        Không cố đoán ngữ nghĩa - việc đó là của LLM. Mục tiêu duy nhất là giữ demo chạy được
        khi chưa cấu hình LLM, và điều đó được báo rõ cho UI qua cờ `llm_used=False`.
        """
        cleaned = (message or "").strip()
        if not cleaned:
            return {}
        missing = missing_required_keys(current_answers)
        return {missing[0]: cleaned} if missing else {}

    def _question_fallback(self, focus_fields: list[ChecklistField]) -> str:
        labels = " và ".join(item.label.lower() for item in focus_fields)
        return f"Bạn vui lòng cho biết {labels} giúp mình nhé?"


intake_agent = IntakeAgent()


@dataclass(slots=True)
class TurnResult:
    """Kết quả một lượt hỏi-đáp, dùng bởi intake_session."""

    extracted: dict[str, str] = field(default_factory=dict)
    red_flags: list[RedFlagHit] = field(default_factory=list)
    llm_used: bool = False
