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
