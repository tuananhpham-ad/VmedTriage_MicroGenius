"""Câu trả lời cho lượt PHI LÂM SÀNG, do LLM viết — §4.10.

Trước đây mọi lane phi lâm sàng đọc một trong ba câu tĩnh. Tĩnh thì an toàn tuyệt đối nhưng nó
không **trả lời**: người bệnh chào, hệ thống lặp lại câu hỏi mở. Module này thay tầng phát ngôn đó
bằng một lời gọi model, và giữ nguyên tầng an toàn bằng cách vây nó bằng code ở cả hai đầu.

```text
lane (keyword hoặc model)
   │
   ├─► compose()
   │      ├── prompt: lane + tin nhắn + Ý CẦN NÓI (chính là câu tĩnh)
   │      ├── LLM  ──────────────► câu trả lời
   │      └── output_guard.check_chitchat  ── không đạt ─┐
   │                                                     │
   └────────────────── câu TĨNH ◄────────────────────────┘  (cũng là đường của: tắt cờ, model chết)
```

**Ba đường thất bại đều rơi về đúng một chỗ** — văn bản tĩnh đang chạy hôm nay. Nghĩa là hành vi tệ
nhất của module này bằng hành vi tốt nhất của bản trước nó, và đó là lý do nó bật được mặc định.

**Vì sao câu tĩnh vẫn được đưa vào prompt làm "Ý CẦN NÓI":** nó không phải để model chép lại, mà để
model biết lane này TỒN TẠI ĐỂ LÀM GÌ. Bỏ nó ra thì model tự nghĩ mục đích của lượt, và cái nó hay
nghĩ ra là trấn an - đúng thứ `VIOLATION_REASSURANCE` sinh ra để chặn.

**Không stream.** `/chat/stream` chỉ stream bước synthesis của đường lâm sàng. Câu ở đây ngắn, và
quan trọng hơn: guard chỉ chấm được câu ĐÃ TRỌN VẸN. Stream nó ra rồi mới phát hiện vi phạm thì
người bệnh đã đọc xong.
"""

from __future__ import annotations

import logging

from src.config import get_settings
from src.services.infra import provider_router
from src.services.symptom_protocol import output_guard, phrasing
from src.services.symptom_protocol.non_clinical import NonClinicalLane

logger = logging.getLogger("vmedtriage.chitchat")

# Nhiet do cua vai tro nay da chuyen sang `Settings.role_temperature_chitchat` (2026-08-25) de moi vai tro
# chinh duoc mot cho, thay vi rai hang so khap cac module. `provider_router._resolve_temperature`
# doc no theo `role=` da truyen san o loi goi ben duoi.
"""Cao hơn 0 vì đây là lượt xã giao: cùng một lời chào mà lượt nào cũng nhận đúng một câu thì hội
thoại nghe như máy trả lời tự động. Thấp hơn bước synthesis lâm sàng (0.7) vì câu ở đây không có
`ResponsePlan` giới hạn nội dung - chỉ có guard, mà guard chấm sau."""

_HISTORY_TURNS = 4
"""Số lượt gần nhất đưa vào prompt. Đủ để model không hỏi lại thứ vừa hỏi, và không hơn: lượt phi
lâm sàng không cần bối cảnh lâm sàng, đưa cả hội thoại vào chỉ mời model bình luận về triệu chứng."""

_LANE_BRIEF: dict[NonClinicalLane, str] = {
    NonClinicalLane.CHITCHAT: (
        "Người dùng đang chào hỏi / cảm ơn / nói chuyện xã giao, chưa nói gì về sức khỏe. "
        "Hãy đáp lại đúng điều họ vừa nói một cách tự nhiên, ngắn, rồi mời họ kể tình trạng sức khỏe."
    ),
    NonClinicalLane.META: (
        "Người dùng đang hỏi về CHÍNH trợ lý này (bạn là ai, dữ liệu có an toàn không, ai sẽ đọc). "
        "Trả lời thẳng câu hỏi đó dựa trên phần SỰ THẬT VỀ HỆ THỐNG bên dưới, rồi mời họ kể tình trạng."
    ),
    NonClinicalLane.OUT_OF_SCOPE: (
        "Người dùng hỏi một chuyện ngoài y tế. Nói thật là bạn không hỗ trợ việc đó, "
        "không bịa thông tin, rồi mời họ quay lại chuyện sức khỏe."
    ),
    NonClinicalLane.LIFESTYLE: (
        "Người dùng hỏi về sinh hoạt/thuốc men và câu trả lời PHỤ THUỘC thuốc + bệnh nền cụ thể. "
        "TUYỆT ĐỐI không tự trả lời câu hỏi đó. Nói rằng nhân viên y tế sẽ xem giúp, "
        "rồi hỏi họ đang dùng thuốc gì và đang điều trị bệnh gì."
    ),
    NonClinicalLane.LOW_CONTENT: (
        "Tin nhắn quá ít thông tin để hiểu người dùng cần gì. Nói ngắn gọn là bạn chưa rõ ý, "
        "rồi mời họ mô tả điều đang khó chịu."
    ),
    NonClinicalLane.NO_SYMPTOMS: (
        "Người dùng nói rõ hiện không có triệu chứng nào. Ghi nhận điều đó, KHÔNG kết luận họ khỏe mạnh, "
        "và cho họ biết có thể quay lại khi thấy bất thường."
    ),
}
"""Mô tả nhiệm vụ theo lane. Lifestyle được viết gắt nhất vì nó là lane sát y khoa nhất - và cũng là
lane mà một câu viết lại trôi chảy dễ trở thành lời khuyên nhất."""

_SYSTEM_FACTS = """SỰ THẬT VỀ HỆ THỐNG (chỉ dùng khi người dùng hỏi tới, không tự khoe):
- Tên: VMedTriage. Là trợ lý ghi nhận triệu chứng, KHÔNG phải bác sĩ.
- Mọi thông tin người dùng kể đều được nhân viên y tế xem và xác nhận trước khi phản hồi cho họ.
- Hệ thống không đưa chẩn đoán bệnh và không kê đơn."""

_SYSTEM_PROMPT = """Bạn là trợ lý ghi nhận triệu chứng của VMedTriage, đang nói chuyện với người dùng bằng tiếng Việt.

Lượt này KHÔNG phải lượt khai bệnh. NHIỆM VỤ:
{brief}

QUY TẮC BẮT BUỘC — vi phạm bất kỳ dòng nào là câu trả lời bị loại bỏ:
- TUYỆT ĐỐI KHÔNG nêu tên bệnh, KHÔNG chẩn đoán, KHÔNG đoán nguyên nhân.
- TUYỆT ĐỐI KHÔNG khuyên dùng thuốc, không nói liều, không khuyên đi khám hay không đi khám.
- TUYỆT ĐỐI KHÔNG trấn an ("không sao đâu", "bạn yên tâm", "không nguy hiểm"). Bạn chưa hỏi gì thì
  chưa biết gì — nói người dùng ổn là một kết luận y tế.
- KHÔNG bịa thông tin ngoài y tế (giờ giấc, đường đi, giá cả, thời tiết). Không biết thì nói không biết.
- Viết 1–3 câu, tiếng Việt tự nhiên. Không markdown, không gạch đầu dòng.
- {persona_rule}
- Câu trả lời PHẢI kết thúc bằng một câu hỏi kéo người dùng về tình trạng sức khỏe của họ.

{facts}

Ý CẦN NÓI (diễn đạt lại bằng lời của bạn, KHÔNG chép nguyên văn):
{intent}
{history}
Tin nhắn vừa nhận của người dùng: "{message}"

Chỉ trả về câu trả lời, không kèm giải thích."""


def compose(
    message: str,
    lane: NonClinicalLane,
    *,
    fallback: str,
    conversation: list[dict[str, str]] | None = None,
    credential: provider_router.LLMCredential | None = None,
) -> tuple[str, bool]:
    """Trả `(câu trả lời, llm_used)`.

    KHÔNG BAO GIỜ ném và không bao giờ trả chuỗi rỗng: mọi đường hỏng đều trả `(fallback, False)`,
    mà `fallback` chính là câu tĩnh của lane đó."""
    settings = get_settings()
    if not settings.chitchat_llm_enabled or not fallback:
        return fallback, False

    brief = _LANE_BRIEF.get(lane)
    if brief is None:
        return fallback, False

    prompt = _SYSTEM_PROMPT.format(
        brief=brief,
        persona_rule=phrasing.PERSONA_RULE,
        facts=_SYSTEM_FACTS if lane is NonClinicalLane.META else "",
        intent=fallback,
        history=_format_history(conversation or []),
        message=message.replace('"', "'")[:400],
    )
    try:
        result = provider_router.complete(
            [{"role": "user", "content": prompt}],
            credential=credential,
            role=provider_router.ROLE_CHITCHAT,
        )
        text = result.text.strip().strip('"')
    except Exception as error:
        logger.info("chitchat fallback (provider): %s", error)
        return fallback, False

    verdict = output_guard.check_chitchat(text)
    if not verdict.ok:
        # Không thử lại: một model vừa viết ra câu trấn an sẽ viết lại câu trấn an khác, và mỗi lần
        # thử là thêm một giây người bệnh phải chờ cho một lượt vốn không mang giá trị lâm sàng nào.
        logger.info("chitchat rejected by guard: %s", verdict.violations)
        return fallback, False
    return text, True


def _format_history(conversation: list[dict[str, str]]) -> str:
    turns = [turn for turn in conversation if turn.get("role") in {"user", "assistant"}]
    if not turns:
        return ""
    lines = "\n".join(
        f"{'Người dùng' if turn.get('role') == 'user' else 'Bạn'}: {turn.get('content', '')}"
        for turn in turns[-_HISTORY_TURNS:]
    )
    return f"\nVài lượt gần nhất:\n{lines}\n"
