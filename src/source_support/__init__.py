"""Part 3 - `source_support`: trích nguồn y văn cho một nhãn triage ĐÃ CHỐT.

RANH GIỚI CỦA CẢ GÓI, một câu: tầng này chạy SAU part 3 quyết định nhãn, và đường DUY NHẤT nó tác
động tới ca là bật thêm `requires_human_review`. Nó không bao giờ đổi `triage_label` - cùng ràng buộc
với `graph_triage/service.py` mục 4 và với `apply_escalation_policy`.

Bảy bước, ba trong số đó gọi model:

    nhãn đã chốt -> [1] tách claim -> [2] tra index cục bộ
                                          |  hit  -> dùng chunk có sẵn, 0 network call
                                          |  miss -> [3] search -> [4] fetch + nạp vào index
                                    [5] chọn quote (cosine, KHÔNG dùng LLM)
                                    [6] chấm verdict (blind)
                                    [7] diễn giải tiếng Việt + guard URL

RỦI RO CỐ HỮU, ghi ra thay vì giấu đi: retrieval chạy sau khi đã có kết luận thì hệ thống sẽ tìm được
thứ gì đó ủng hộ kết luận ấy (confirmation-seeking). Kiến trúc post-hoc không khử được điều này, nên
nó được ĐO: thang chấm có nấc `contradicts`, và ca bị nguồn nói ngược sẽ bật cờ người xem.
"""

from __future__ import annotations

from src.source_support.schemas import (
    Citation,
    Claim,
    ClaimResult,
    CostReport,
    Method,
    SourceHit,
    SourceSupport,
    SupportSummary,
    Verdict,
)

__all__ = [
    "Citation",
    "Claim",
    "ClaimResult",
    "CostReport",
    "Method",
    "SourceHit",
    "SourceSupport",
    "SupportSummary",
    "Verdict",
]
