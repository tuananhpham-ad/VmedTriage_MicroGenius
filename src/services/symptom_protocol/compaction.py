"""Memory **M2** — nén phần hội thoại khi context vượt ngưỡng (§4.9, `F04_memory.md` §2).

Short memory của phiên là một hỗn hợp ba phần, và chỉ phần GIỮA là thứ module này đụng tới:

```text
Structured snapshot   `Session.answers`      <- NGUỒN SỰ THẬT. Module này KHÔNG BAO GIỜ chạm vào.
+ Tóm tắt lượt cũ     `conversation_summary` <- phần module này sinh ra
+ N lượt raw gần nhất `conversation[-N:]`    <- giữ nguyên văn
```

**Bất biến của cả module, và là lý do nó không được phép ghi vào `answers`:** bản tóm tắt là văn
xuôi do model viết, nó **không có `evidence_span`**. Snapshot thì có. Nếu hai thứ bất đồng thì
snapshot thắng - không phải vì snapshot mới hơn, mà vì nó là thứ duy nhất truy được về đúng câu chữ
người bệnh đã nói. Vì thế đường ghi ngược từ tóm tắt vào snapshot **không tồn tại trong code**, thay
vì tồn tại kèm một câu `if` bảo vệ mà ai đó có thể gỡ.

**Ngưỡng đếm bằng TOKEN, không đếm bằng số lượt** (`context_compaction_token_budget`). Đếm theo lượt
là sai đơn vị: 20 lượt "vâng"/"không" nhẹ hơn 6 lượt mà người bệnh kể ba đoạn dài, mà chính phiên
thứ hai mới là phiên làm tràn context.

`session.conversation` vẫn giữ ĐỦ lượt thô sau khi nén: nó là bản ghi bàn giao (`HandoffSummary.
raw_conversation`) và là thứ điều dưỡng đọc lại. Cái được nén là **khung nhìn gửi cho model**
(`history_view`), không phải bản ghi.
"""

from __future__ import annotations

import logging

from src.config import get_settings
from src.services.infra import provider_router

logger = logging.getLogger("vmedtriage.compaction")

ROLE_SUMMARY = "summary"
"""Vai của lượt tổng hợp trong `history_view`. Không phải `user`/`assistant`: nó không phải lời của
ai cả, và render nó thành "Trợ lý: ..." sẽ khiến model tưởng nó đã nói đúng nguyên văn câu đó."""

_MAX_SUMMARY_CHARS = 1200
"""Trần độ dài bản tóm tắt. Không có trần thì mỗi lần nén lại nối thêm vào bản cũ, và sau vài chục
lượt "bản nén" tự nó trở thành thứ làm tràn context - đúng thứ nó sinh ra để tránh."""

_SUMMARY_TEMPERATURE = 0.0

_SYSTEM_PROMPT = """Bạn tóm tắt phần đầu của một cuộc hỏi-đáp y tế để lưu vào bộ nhớ ngắn hạn.

QUY TẮC BẮT BUỘC:
- CHỈ ghi lại những gì đã thật sự được nói trong đoạn hội thoại bên dưới. TUYỆT ĐỐI không suy diễn.
- KHÔNG nêu tên bệnh, KHÔNG chẩn đoán, KHÔNG khuyên xử trí, KHÔNG đề xuất mức độ ưu tiên.
- Ghi rõ ý nào người bệnh nói CÓ, ý nào người bệnh nói KHÔNG CÓ; không trộn hai nhóm vào nhau.
- Ghi cả những ý người bệnh đã được hỏi mà chưa trả lời được.
- Viết ngôi thứ ba ("Người bệnh..."), tối đa 5 câu, không gạch đầu dòng, không markdown."""


def estimate_tokens(text: str) -> int:
    """Ước lượng token, KHÔNG gọi tokenizer thật.

    Tokenizer thật đòi đúng model đang chạy, mà `provider_router` có thể xoay qua 5 provider khác
    nhau giữa chừng - "đúng model" không phải một thứ ổn định để dựa vào. Ở đây chỉ cần một con số
    ĐỦ ĐÚNG để quyết định "đã tới lúc nén chưa", và một ước lượng thô sai 20% chỉ làm ngưỡng lệch
    20%, không làm hỏng gì.

    Hệ số 3 ký tự/token là mức đo được của tiếng Việt có dấu trên BPE (tiếng Việt tốn token hơn
    tiếng Anh vì dấu thanh tách thành byte riêng)."""
    return (len(text) + 2) // 3


def conversation_tokens(turns: list[dict[str, str]]) -> int:
    return sum(estimate_tokens(str(turn.get("content", ""))) for turn in turns)


def history_view(session) -> list[dict[str, str]]:
    """Khung nhìn hội thoại GỬI CHO MODEL: bản tóm tắt (nếu có) + các lượt thô chưa bị nén.

    Đây là hàm mà mọi lời gọi model phải đi qua thay vì đọc thẳng `session.conversation` - nếu không,
    phần đã nén vẫn được gửi kèm và việc nén không tiết kiệm được gì."""
    view: list[dict[str, str]] = []
    if session.conversation_summary:
        view.append({"role": ROLE_SUMMARY, "content": session.conversation_summary})
    view.extend(session.conversation[session.summarized_turns:])
    return view


def maybe_compact(session, *, credential: provider_router.LLMCredential | None = None) -> bool:
    """Nén nếu phần chưa nén đã vượt ngưỡng token. Trả `True` khi đã nén.

    KHÔNG BAO GIỜ ném: nén là một tối ưu về context, còn lượt người bệnh đang trả lời thì không.
    Model chết ⇒ rơi về bản tóm tắt tất định (ghép lời người bệnh), không rơi về chuỗi rỗng - mất
    bản tóm tắt nghĩa là mất luôn phần hội thoại vừa bị cắt khỏi khung nhìn."""
    settings = get_settings()
    keep = settings.context_compaction_keep_turns
    pending = session.conversation[session.summarized_turns:]
    if conversation_tokens(pending) <= settings.context_compaction_token_budget:
        return False

    foldable = pending[:-keep] if keep else pending
    if not foldable:
        # Ngưỡng đã vượt nhưng toàn bộ phần vượt nằm trong cửa sổ phải giữ nguyên văn. Không cắt vào
        # cửa sổ đó: đấy đúng là những lượt model cần đọc từng chữ để hiểu người bệnh vừa nói gì.
        return False

    session.conversation_summary = _summarize(
        foldable, previous=session.conversation_summary, credential=credential,
    )
    session.summarized_turns += len(foldable)
    logger.info(
        "compacted session=%s turns=%d summarized_total=%d",
        getattr(session, "session_id", ""), len(foldable), session.summarized_turns,
    )
    return True


# --- sinh bản tóm tắt -----------------------------------------------------------------------


def _summarize(
    turns: list[dict[str, str]], *, previous: str, credential: provider_router.LLMCredential | None,
) -> str:
    transcript = _render(turns)
    prompt = _SYSTEM_PROMPT
    if previous:
        prompt += f"\n\nTóm tắt của phần TRƯỚC ĐÓ (giữ lại các ý còn giá trị):\n{previous}"
    prompt += f"\n\nĐOẠN HỘI THOẠI CẦN TÓM TẮT:\n{transcript}"
    try:
        result = provider_router.complete(
            [{"role": "user", "content": prompt}],
            temperature=_SUMMARY_TEMPERATURE,
            credential=credential,
            role=provider_router.ROLE_SYNTHESIS,
        )
        text = result.text.strip()
    except Exception as error:  # provider hỏng / hết ngân sách / JSON rác
        logger.warning("compaction fallback: %s", error)
        text = ""
    return _clip(text or _deterministic_summary(turns, previous=previous))


def _deterministic_summary(turns: list[dict[str, str]], *, previous: str) -> str:
    """Bản tất định: ghép NGUYÊN VĂN lời người bệnh, không diễn giải.

    Kém súc tích hơn bản model viết, nhưng nó có một tính chất mà bản model viết không có: nó không
    thể bịa. Với một tầng chỉ để nhắc lại bối cảnh thì đó là đánh đổi đúng."""
    spoken = [
        str(turn.get("content", "")).strip()
        for turn in turns
        if turn.get("role") == "user" and str(turn.get("content", "")).strip()
    ]
    body = "Người bệnh đã kể: " + " | ".join(spoken) if spoken else ""
    return f"{previous}\n{body}".strip() if previous else body


def _render(turns: list[dict[str, str]]) -> str:
    return "\n".join(
        f"{'Người bệnh' if turn.get('role') == 'user' else 'Trợ lý'}: {turn.get('content', '')}"
        for turn in turns
    )


def _clip(text: str) -> str:
    """Cắt ở ranh giới câu gần nhất chứ không cắt giữa chữ - một bản tóm tắt đứt giữa câu là một câu
    model có thể đọc hiểu sai."""
    if len(text) <= _MAX_SUMMARY_CHARS:
        return text
    head = text[:_MAX_SUMMARY_CHARS]
    cut = head.rfind(". ")
    return (head[: cut + 1] if cut > _MAX_SUMMARY_CHARS // 2 else head).strip()
