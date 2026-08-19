"""Nhúng vector cho `source_support`, dùng `text-embedding-3-small` của OpenAI.

VÌ SAO KHÔNG DÙNG MODEL CỤC BỘ. Bản đầu của module này mượn `bkai-foundation-models/vietnamese-bi-encoder`
đã có sẵn trong dự án, với lý do "$0 tiền và tối ưu cho tiếng Việt". Cả hai vế đều sai chỗ:

* Corpus v1 là tài liệu TIẾNG ANH (NHS, NICE, MSD, WHO) và bước tra dùng `claim_en`. Tức đây là bài
  toán Anh-Anh, còn `vietnamese-bi-encoder` dựng trên PhoBERT và huấn luyện trên tiếng Việt. Tệ hơn,
  tầng đó chạy `underthesea.word_tokenize` trước khi nhúng - tách từ tiếng Việt áp lên chữ tiếng Anh,
  biến "A febrile" thành token vô nghĩa "A_febrile".
* Khoản tiết kiệm là ~$0,005 cho toàn bộ lần nạp corpus. Đó là cái giá đã trả để đổi lấy retrieval
  kém hẳn.

ĐO ĐƯỢC (2026-08-19, cùng một claim "co giật do sốt ở trẻ dưới 5 tuổi kèm không đáp ứng kéo dài"):

                              đoạn ĐÚNG cao nhất   đoạn SAI cao nhất   chênh lệch
    vietnamese-bi-encoder            0.380               0.246           0.135
    text-embedding-3-small           0.683               0.172           0.511

Model cục bộ KHÔNG đưa nổi đúng câu cần trích lên trên ngưỡng 0.45 - tức mọi claim đều thành
index-miss dù corpus có sẵn câu đó, và mỗi ca sẽ đổ hết sang search (chỗ tốn tiền thật). Đây là lý do
số đo phải có trước lựa chọn kỹ thuật, không phải sau.

MUỐN PHỦ TÀI LIỆU TIẾNG VIỆT thì `text-embedding-3-small` cũng làm được (nó đa ngữ), nên hướng mở
rộng v2 không bị khoá lại bởi lựa chọn này.
"""

from __future__ import annotations

import logging

from src.config import get_settings

logger = logging.getLogger("vmedtriage.source_support")

EMBEDDING_MODEL_NAME = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

BATCH_SIZE = 256
"""Số đoạn mỗi lời gọi. API nhận tới 2048, nhưng lô nhỏ hơn thì một lần lỗi mạng chỉ phải làm lại
một phần nhỏ - lần nạp corpus có hơn một nghìn chunk."""

__all__ = ["EMBEDDING_MODEL_NAME", "embed_many", "embed_one", "last_token_usage"]

_last_tokens = 0


def _client():
    """Client OpenAI. Dựng theo yêu cầu chứ không giữ singleton - `Settings` đọc lại được lúc chạy."""
    from openai import OpenAI

    settings = get_settings()
    if not settings.openai_api_key.strip():
        raise RuntimeError(
            "Thiếu OPENAI_API_KEY - tầng trích nguồn cần nó để nhúng vector. "
            "Đặt key, hoặc tắt bằng SOURCE_SUPPORT_ENABLED=false."
        )
    return OpenAI(api_key=settings.openai_api_key)


def embed_many(texts: list[str]) -> list[list[float]]:
    """Nhúng nhiều đoạn, trả về vector đã chuẩn hoá L2, ĐÚNG THỨ TỰ đầu vào.

    Thứ tự là bất biến người gọi dựa vào: `index.add_document` ghép vector theo hàng khớp với chunk
    theo dòng, lệch một vị trí là mọi trích dẫn từ đó gắn sai nguồn.

    Chuẩn hoá ngay tại đây để `index.search` chỉ cần tích vô hướng - cùng con số cosine, ít phép tính
    hơn, và không có chỗ nào quên chia chuẩn."""
    global _last_tokens

    cleaned = [text.replace("\n", " ").strip() for text in texts]
    if not any(cleaned):
        return []

    client = _client()
    vectors: list[list[float]] = []
    _last_tokens = 0
    for start in range(0, len(cleaned), BATCH_SIZE):
        batch = cleaned[start : start + BATCH_SIZE]
        response = client.embeddings.create(model=EMBEDDING_MODEL_NAME, input=batch)
        # `response.data` không bảo đảm đúng thứ tự gửi đi; mỗi mục có `index` riêng nên sắp lại theo
        # nó thay vì tin vào thứ tự trả về.
        vectors.extend(item.embedding for item in sorted(response.data, key=lambda item: item.index))
        _last_tokens += response.usage.total_tokens
    return [_normalise(vector) for vector in vectors]


def embed_one(text: str) -> list[float]:
    """Nhúng một đoạn. Vỏ mỏng của `embed_many`."""
    vectors = embed_many([text])
    if not vectors:
        raise ValueError("Không nhúng được chuỗi rỗng.")
    return vectors[0]


def last_token_usage() -> int:
    """Số token THẬT của lần `embed_many` gần nhất, lấy từ `usage` của API.

    Khác hẳn bản trước vốn ước theo ~4 ký tự/token: đây là con số có hoá đơn đối chiếu, đúng tinh
    thần "chi phí ghi vào output phải là số đo được, không phải số ước"."""
    return _last_tokens


def _normalise(vector: list[float]) -> list[float]:
    total = sum(value * value for value in vector) ** 0.5
    if total == 0:
        return vector
    return [value / total for value in vector]
