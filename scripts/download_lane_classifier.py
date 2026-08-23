"""Tải trọng số model phân loại lane phi lâm sàng về cache Hugging Face — chạy lúc BUILD.

**Vì sao lúc build chứ không lúc chạy.** Ổ đĩa container trên Azure Container Apps là ephemeral và
replica bị thu hồi/khởi động lại bất cứ lúc nào. Tải lúc khởi động nghĩa là mỗi cold start phải chờ
vài trăm MB, và một lần Hugging Face Hub hỏng là app không lên được. Đây đúng là lý do
`scripts/download_graph_artifacts.py` tồn tại, và file này đi cùng đường.

Cache đích là `$HF_HOME` - `Dockerfile` trỏ nó vào `/app/.hf_cache` để thư mục nằm trong layer được
COPY sang stage runtime. Để mặc định (`~/.cache/huggingface`) thì trọng số nằm trong home của user
builder và biến mất ở stage cuối.

Chạy tay:  python -m scripts.download_lane_classifier
"""

from __future__ import annotations

import sys
from pathlib import Path

from src.config import get_settings


def _human(num_bytes: int) -> str:
    return f"{num_bytes / 1024 / 1024:.0f} MB"


def main() -> int:
    model_name = get_settings().hf_zero_shot_model_name.strip()
    if not model_name:
        print("[lane-classifier] HF_ZERO_SHOT_MODEL_NAME rỗng - bỏ qua.")
        return 0

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        # requirements-graph.txt chưa cài. Không phải lỗi: app vẫn chạy bằng sàn keyword.
        print("[lane-classifier] thiếu huggingface_hub - bỏ qua, hệ thống chạy bằng sàn keyword.")
        return 0

    print(f"[lane-classifier] tải {model_name} ...")
    path = snapshot_download(
        repo_id=model_name,
        # Chỉ lấy thứ `transformers.pipeline` cần. Không lọc thì repo kéo về cả bản `.bin`, `.h5`,
        # `.msgpack` của cùng một bộ trọng số - nhân đôi, nhân ba dung lượng image cho không.
        allow_patterns=["*.json", "*.txt", "*.model", "*.safetensors", "sentencepiece*"],
    )
    total = sum(item.stat().st_size for item in Path(path).rglob("*") if item.is_file())
    print(f"[lane-classifier] xong: {path} ({_human(total)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
