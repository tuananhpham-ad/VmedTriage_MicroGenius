"""Tải 3 artifact của graph triage agent (logreg/bert/fusion) từ Hugging Face Hub về `runs/`.

VÌ SAO CẦN SCRIPT NÀY: `src/graph_triage/service.py` chỉ đọc artifact từ đĩa cục bộ
(`GRAPH_TRIAGE_ARTIFACT_ROOT`, mặc định `<repo>/runs`) - nó không tự tải gì từ mạng. `runs/` nằm
trong .gitignore (PhoBERT + fusion > 500 MB), nên trên một host mới (vd Render) thư mục này rỗng cho
tới khi có bước tải riêng. Script này là bước đó - chạy trong buildCommand, TRƯỚC khi app khởi động.

Đọc repo id từ 3 biến môi trường (khớp tên trong `.env`):
    FUSION_FULL_MODEL, LOGREG_FULL_MODEL, BERT_FULL_MODEL

Idempotent: nếu file mấu chốt của một artifact đã có trên đĩa (vd đĩa persistent của Render còn giữ
từ lần deploy trước) thì bỏ qua, không tải lại. Dùng --force để tải lại tất cả.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from src.config import get_settings
from src.paths import RUNS_DIR

logger = logging.getLogger("vmedtriage.graph_triage.download")


def _artifact_root():
    """Khớp đúng logic `src/graph_triage/service.py::_artifact_root` - nếu không thì script tải vào
    một chỗ còn app đọc ở chỗ khác."""
    from pathlib import Path

    configured = get_settings().graph_triage_artifact_root.strip()
    return Path(configured) if configured else RUNS_DIR

# (env var đọc repo id, thư mục đích trong runs/, file dùng để kiểm "đã tải xong chưa")
ARTIFACTS: tuple[tuple[str, str, str], ...] = (
    ("LOGREG_FULL_MODEL", "logreg_full", "model.joblib"),
    ("BERT_FULL_MODEL", "bert_full", "model/config.json"),
    ("FUSION_FULL_MODEL", "fusion_full", "model.pt"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Tải lại kể cả khi artifact đã có trên đĩa.")
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args()

    from huggingface_hub import snapshot_download

    root = _artifact_root()
    failed: list[str] = []
    for env_var, subdir, marker_relpath in ARTIFACTS:
        repo_id = os.getenv(env_var, "").strip()
        target_dir = root / subdir
        marker = target_dir / marker_relpath

        if not repo_id:
            print(f"BỎ QUA {subdir}: thiếu biến môi trường {env_var}.")
            failed.append(subdir)
            continue

        if marker.is_file() and not args.force:
            print(f"CÓ SẴN {subdir}: {marker} đã tồn tại, bỏ qua tải ({repo_id}).")
            continue

        print(f"TẢI {subdir} <- {repo_id} ...")
        try:
            snapshot_download(repo_id=repo_id, local_dir=target_dir)
        except Exception as error:  # network, quyền truy cập repo, repo không tồn tại...
            logger.error("download_failed subdir=%s repo_id=%s error=%s", subdir, repo_id, error)
            failed.append(subdir)
            continue

        if not marker.is_file():
            print(f"CẢNH BÁO {subdir}: tải xong nhưng thiếu {marker} - kiểm lại cấu trúc repo {repo_id}.")
            failed.append(subdir)
        else:
            print(f"XONG {subdir}: {marker}")

    if failed:
        print(f"\nThất bại: {', '.join(failed)}. Graph triage agent sẽ tự tắt (best-effort) khi thiếu artifact.")
        return 1
    print("\nCả 3 artifact đã sẵn sàng.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
