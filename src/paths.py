"""Đường dẫn gốc của dự án, khai báo một chỗ duy nhất.

Vì sao cần: các module trước đây tự tính đường dẫn bằng `Path(__file__).parents[N]`, tức là mã hoá
cứng độ sâu thư mục của chính nó. Chỉ cần chuyển file sang thư mục con là N sai, và lỗi chỉ lộ ra
lúc chạy (`ChecklistNotFoundError`, ghi log vào nhầm chỗ) chứ không phải lúc import.

Neo vào đây thì file nằm ở đâu trong `src/` cũng không ảnh hưởng.
"""

from __future__ import annotations

from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SRC_DIR.parent

DOMAIN_DIR = SRC_DIR / "domain"
"""Checklist theo từng bệnh (`_<disease_id>.json`)."""

LOGS_DIR = PROJECT_ROOT / "logs"
"""Log phiên hỏi-đáp. Đã nằm trong .gitignore vì chứa nguyên văn hội thoại (PHI)."""

DATA_DIR = PROJECT_ROOT / "data"

RUNS_DIR = PROJECT_ROOT / "runs"
"""Artifact model đã train (`logreg_full/`, `bert_full/`, `fusion_full/`). Trong .gitignore vì một
thư mục PhoBERT đã hơn 500 MB."""

GRAPH_CACHE_DIR = DATA_DIR / "graphs"
"""Patient Graph JSONL do `src/graph_triage/extract_graphs.py` sinh ra."""

SOURCE_INDEX_DIR = DATA_DIR / "source_index"
"""Corpus y văn của `src/source_support/` (part 3): `corpus.jsonl` + `embeddings.npy`, hai file song
song cùng thứ tự dòng. Sinh ra bằng `scripts/build_source_corpus.py` và tự bồi đắp mỗi lần một claim
không tra được trong index. Trong .gitignore vì nó là dữ liệu tải về, không phải mã nguồn."""
