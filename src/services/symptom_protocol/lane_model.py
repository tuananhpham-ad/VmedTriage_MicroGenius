"""Tầng phân loại y-tế / phi-y-tế bằng **model NLI zero-shot** (§4.10 mục 14).

Đây là thứ mà `non_clinical.classify` đã hẹn trước trong docstring của nó: *"Router bằng model nhỏ
sẽ đứng SAU hàm này, không thay nó"*. Model được chọn từ trước và nằm sẵn trong `.env`:
`MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli`.

```text
tin nhắn
   │
   ├─► L0 text_safety_signals        [THUẦN CODE] ── dấu hiệu đỏ ⇒ thoát ngay, không ai hỏi model
   │
   ├─► non_clinical.classify         [THUẦN CODE] ── khớp cụm từ ⇒ CHỐT
   │        │
   │        └── is_undecided (không marker lâm sàng, không lane nào khớp)
   │                 │
   │                 └─► lane_model.classify   [MODEL] ── chỉ ở ĐÚNG nhánh này
   │
   └─► đường lâm sàng bình thường
```

**Bốn ràng buộc, và ràng buộc 2 là thứ khiến tầng này an toàn:**

1. **Import lazy.** `transformers`/`torch` nằm ở `requirements-graph.txt`, không ở `requirements.txt`.
   Import ở top-level là cả app chết lúc khởi động trên môi trường chưa cài (kể cả CI).
2. **Chỉ được hỏi khi tầng keyword KHÔNG QUYẾT ĐƯỢC.** Tin nhắn đã có dấu hiệu lâm sàng thì model
   không bao giờ được nhìn thấy - nó không có cửa nào lật một ca thật thành chitchat. Đây là lý do
   `NonClinicalVerdict.clinical_markers` tồn tại.
3. **Không quyết được ⇒ rơi về đường LÂM SÀNG.** Dưới ngưỡng, model hỏng, thiếu thư viện, hết thời
   gian - tất cả đều trả `NONE`. Định tuyến nhầm một câu tán gẫu vào bộ câu hỏi chỉ tốn một câu hỏi
   thừa; định tuyến nhầm một triệu chứng vào chitchat là bỏ một ca.
4. **Tắt cờ thì hệ thống chạy y hệt hôm nay.** `INVARIANTS.md` §4 đòi điều này cho mọi công tắc, và
   ở đây nó đúng theo nghĩa đen: sàn tất định chạy trước và tự nó đã đủ để hệ thống hoạt động.

**Vì sao zero-shot NLI chứ không phải một classifier được huấn luyện:** chúng ta không có bộ nhãn
"y tế / phi y tế" nào cả. Một model đã học suy luận entailment đa ngữ cho phép mô tả nhãn bằng câu
tiếng Việt và dùng được ngay - và điểm mấu chốt là **đa ngữ**: mọi cụm từ trong `non_clinical` đều
là tiếng Việt không dấu, nên "hello" hay "how are you" không có cửa nào được nhận ra.

**Chi phí:** model tải MỘT lần lúc khởi động (singleton có khoá), suy luận trên CPU. Trên Azure
Container Apps thì trọng số phải nằm sẵn trong image - ổ đĩa container là ephemeral, y như artifact
graph triage (xem `Dockerfile`).
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from src.config import get_settings
from src.services.symptom_protocol.non_clinical import NonClinicalLane, NonClinicalVerdict

logger = logging.getLogger("vmedtriage.lane_model")

_lock = threading.Lock()
_classifier: Any | None = None
_unavailable_reason: str | None = None

HYPOTHESIS_TEMPLATE = "Tin nhắn này là {}."
"""Câu giả thuyết của NLI. Tiếng Việt chứ không phải tiếng Anh: model là đa ngữ, và giả thuyết cùng
ngôn ngữ với tiền đề cho điểm ổn định hơn trên XNLI."""

CLINICAL_LABEL = "lời kể về triệu chứng hoặc vấn đề sức khỏe"
"""Nhãn LÂM SÀNG. Bắt buộc phải có mặt trong tập nhãn: thiếu nó thì model buộc phải chọn một lane phi
lâm sàng nào đó cho mọi tin nhắn, kể cả tin nhắn kể bệnh - zero-shot chấm điểm tương đối giữa các
nhãn được đưa, nó không có quyền trả lời "không nhãn nào cả"."""

_LABELS: tuple[tuple[str, NonClinicalLane], ...] = (
    (CLINICAL_LABEL, NonClinicalLane.NONE),
    ("lời chào hỏi, cảm ơn hoặc trò chuyện xã giao", NonClinicalLane.CHITCHAT),
    ("câu hỏi về ăn uống, rượu bia, tập luyện hoặc thuốc đang dùng", NonClinicalLane.LIFESTYLE),
    ("câu hỏi về trợ lý này hoặc về dữ liệu cá nhân của người dùng", NonClinicalLane.META),
    ("câu hỏi về chủ đề không liên quan tới sức khỏe", NonClinicalLane.OUT_OF_SCOPE),
)
"""Nhãn mô tả bằng câu, không phải bằng mã. Zero-shot chấm bằng chính nghĩa của câu nhãn, nên
`"chitchat"` cho điểm tệ hơn hẳn `"lời chào hỏi, cảm ơn hoặc trò chuyện xã giao"`.

Cố ý KHÔNG có nhãn cho `LOW_CONTENT` và `NO_SYMPTOMS`: cả hai đã được tầng keyword bắt tất định và
chính xác ("..." không cần model nào để biết là tin nhắn rỗng nghĩa)."""

_LANE_BY_LABEL = dict(_LABELS)
_LABEL_LIST = [label for label, _ in _LABELS]

_MAX_CHARS = 400
"""Cắt bớt tin nhắn dài trước khi đưa vào model. Lượt phi lâm sàng luôn ngắn; một tin nhắn 2000 ký
tự gần như chắc chắn là lời kể bệnh, và cắt nó không đổi kết luận nhưng giữ độ trễ ổn định."""


def available() -> bool:
    """Tầng model có đang phục vụ không. Không tự nạp model - chỉ đọc cờ và trạng thái đã biết."""
    return get_settings().enable_hf_zero_shot_domain_classifier and _unavailable_reason is None


def classify(message: str, *, keyword_verdict: NonClinicalVerdict) -> NonClinicalVerdict:
    """Phán quyết của model, hoặc chính `keyword_verdict` khi model không được hỏi / không quyết được.

    Hàm này KHÔNG BAO GIỜ ném và không bao giờ trả về một lane khác `keyword_verdict` trừ khi model
    thật sự vượt ngưỡng."""
    settings = get_settings()
    if not settings.enable_hf_zero_shot_domain_classifier or not keyword_verdict.is_undecided:
        return keyword_verdict

    classifier = _get_classifier()
    if classifier is None:
        return keyword_verdict

    try:
        result = classifier(
            message[:_MAX_CHARS],
            candidate_labels=_LABEL_LIST,
            hypothesis_template=HYPOTHESIS_TEMPLATE,
            multi_label=False,
        )
        label = str(result["labels"][0])
        score = float(result["scores"][0])
    except Exception as error:
        logger.warning("lane model failed: %s", error)
        return keyword_verdict

    lane = _LANE_BY_LABEL.get(label, NonClinicalLane.NONE)
    if lane is NonClinicalLane.NONE:
        # Model nói đây là chuyện lâm sàng. Đi tiếp đường lâm sàng - và KHÔNG cần xét ngưỡng, vì đó
        # cũng đúng là hướng mà "không chắc" phải rơi về.
        return keyword_verdict
    if score < settings.hf_zero_shot_threshold:
        logger.debug("lane model below threshold: %s %.2f", lane.value, score)
        return keyword_verdict
    return NonClinicalVerdict(lane=lane, matched=(label,), source="model", score=score)


# --- nạp model ---------------------------------------------------------------------------------


def _get_classifier() -> Any | None:
    """Singleton lười, khoá bằng `threading.Lock` vì uvicorn chạy nhiều worker thread.

    Thất bại được ghi nhớ ở `_unavailable_reason`: thiếu `transformers` hay thiếu trọng số là một
    sự thật ổn định của môi trường, thử lại mỗi lượt chỉ trả tiền cho cùng một lỗi."""
    global _classifier, _unavailable_reason
    if _classifier is not None or _unavailable_reason is not None:
        return _classifier
    with _lock:
        if _classifier is not None or _unavailable_reason is not None:
            return _classifier
        try:
            _classifier = _build_classifier()
            logger.info("lane model ready: %s", get_settings().hf_zero_shot_model_name)
        except Exception as error:
            _unavailable_reason = str(error)
            logger.warning("lane model unavailable, dùng sàn keyword: %s", error)
    return _classifier


def _build_classifier() -> Any:
    """Mọi import nặng nằm TRONG hàm - xem ràng buộc 1."""
    from transformers import pipeline as hf_pipeline

    model_name = get_settings().hf_zero_shot_model_name
    return hf_pipeline("zero-shot-classification", model=model_name, device=-1)


def reset_for_tests() -> None:
    """Xoá singleton. Chỉ dùng trong test - một bài vá `transformers` không được để lại model giả
    cho bài sau."""
    global _classifier, _unavailable_reason
    with _lock:
        _classifier = None
        _unavailable_reason = None
