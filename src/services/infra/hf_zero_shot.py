"""HTTP client cho Hugging Face Inference API, endpoint `zero-shot-classification`.

Dùng làm cửa lọc RẺ trước `non_clinical.classify_with_model` (LLM sinh văn bản đầy đủ): model NLI nhỏ
(mặc định `MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli`) chỉ chấm điểm các nhãn có sẵn, không sinh
câu, nên rẻ và nhanh hơn một lượt chat completion. Module này KHÔNG quyết định lane - nó chỉ trả điểm
số thô, việc map nhãn -> lane và áp ngưỡng tin cậy là việc của caller (`non_clinical`).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

import requests

logger = logging.getLogger("vmedtriage.hf_zero_shot")

_API_URL = "https://api-inference.huggingface.co/models/{model}"


@dataclass(frozen=True, slots=True)
class ZeroShotResult:
    label: str
    score: float


def classify(
    text: str,
    candidate_labels: Sequence[str],
    *,
    api_key: str,
    model_name: str,
    timeout_seconds: float = 8.0,
    multi_label: bool = False,
) -> list[ZeroShotResult] | None:
    """Gọi HF Inference API. Trả `None` khi thiếu key, thiếu văn bản, lỗi mạng, hoặc response không
    hợp lệ - KHÔNG BAO GIỜ raise, vì caller cần fail-open sang bước tiếp theo (LLM hoặc luồng lâm
    sàng) thay vì làm hỏng cả lượt hội thoại vì một dịch vụ phân loại phụ trợ."""
    if not api_key or not text.strip() or not candidate_labels:
        return None
    try:
        response = requests.post(
            _API_URL.format(model=model_name),
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "inputs": text,
                "parameters": {"candidate_labels": list(candidate_labels), "multi_label": multi_label},
            },
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as error:
        logger.warning("hf zero-shot classify failed: %s", error)
        return None

    if not isinstance(payload, dict):
        return None
    labels = payload.get("labels")
    scores = payload.get("scores")
    if not isinstance(labels, list) or not isinstance(scores, list) or len(labels) != len(scores):
        return None
    try:
        return [ZeroShotResult(label=str(label), score=float(score)) for label, score in zip(labels, scores)]
    except (TypeError, ValueError):
        return None
