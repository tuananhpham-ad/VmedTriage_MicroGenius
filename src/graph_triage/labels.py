"""Bộ nhãn triage và cách chuẩn hoá nhãn thô. KHÔNG phụ thuộc thư viện nặng nào.

VÌ SAO TÁCH KHỎI `common.py`: `common.py` import scikit-learn và pandas ở top-level cho phần đo đạc
lúc train. Đường inference (`agent/decision.py`, `agent/llm_decision.py`) chỉ cần đúng tuple
`TRIAGE_LABELS`, nhưng import nó qua `common.py` thì kéo luôn cả bộ thư viện huấn luyện vào tiến
trình web - vừa chậm khởi động vừa biến scikit-learn/pandas thành dependency bắt buộc của một
tính năng không hề dùng tới chúng.

Ba nhãn này khớp đúng 3 mức ưu tiên trong phạm vi MVP (xem `CLAUDE.md`).
"""

from __future__ import annotations

import re
import unicodedata

TRIAGE_LABELS = ("theo_doi_tai_nha", "kham_som", "cap_cuu")
EMERGENCY_LABEL = "cap_cuu"
LABEL_ALIASES = {
    "low severity": "theo_doi_tai_nha", "low": "theo_doi_tai_nha", "theo doi tai nha": "theo_doi_tai_nha",
    "medium severity": "kham_som", "medium": "kham_som", "kham som": "kham_som",
    "high severity": "cap_cuu", "high": "cap_cuu", "cap cuu": "cap_cuu",
}


def _label_key(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.lower())
    normalized = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", normalized).strip()


def normalize_label(value: str) -> str | None:
    return LABEL_ALIASES.get(_label_key(value))
