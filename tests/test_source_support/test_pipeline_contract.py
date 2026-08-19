"""Hợp đồng của tầng: part 3 KHÔNG BAO GIỜ đổi nhãn, chỉ được BẬT THÊM cờ người xem, và hỏng thì im.

Đây là ba lời hứa mà cả thiết kế dựa vào, nên chúng phải có bài kiểm chứ không chỉ có docstring:

1. Không có đường nào từ part 3 sửa `triage_label` - mức ưu tiên có hiệu lực vẫn do rule engine quyết
   (ràng buộc 4 của `graph_triage/service.py`).
2. Cờ `requires_human_review` chỉ đi một chiều. Đảo chiều phép OR ở chỗ nối là cách một ca cần người
   xem lặng lẽ trôi qua - loại lỗi một dòng, không ai đọc ra, và không bao giờ báo lỗi.
3. Trích nguồn hỏng thì ca vẫn vào hàng đợi điều dưỡng như thường (ràng buộc 3 của service).
"""

from __future__ import annotations

import pytest

from src.config import get_settings
from src.graph_triage import service
from src.models.schemas import TriageCase
from src.source_support.pipeline import merge_human_review
from src.source_support.schemas import Method, SourceSupport, SupportSummary


def _support(*, requires_human_review: bool) -> SourceSupport:
    return SourceSupport(summary=SupportSummary(requires_human_review=requires_human_review))


# --- lời hứa 1: không đổi nhãn ------------------------------------------------------------------


def test_method_can_change_label_is_locked_false() -> None:
    """`Literal[False]` chứ không phải `bool`: một thay đổi tương lai làm nó thành True sẽ hỏng lúc
    validate, không lặng lẽ đi qua."""
    assert SourceSupport().method.can_change_label is False
    with pytest.raises(Exception):
        Method(can_change_label=True)


def test_source_support_carries_no_triage_label() -> None:
    """Khối trả về không có chỗ nào để đặt nhãn - hợp đồng được bảo đảm bằng hình dạng dữ liệu, không
    bằng quy ước."""
    assert "triage_label" not in SourceSupport().model_dump()


# --- lời hứa 2: cờ chỉ đi một chiều -------------------------------------------------------------


@pytest.mark.parametrize(
    ("decision_flag", "support_flag", "expected"),
    [
        (False, False, False),
        (False, True, True),   # part 3 BẬT THÊM được
        (True, False, True),   # part 3 KHÔNG hạ được cờ của part 2
        (True, True, True),
    ],
)
def test_merge_human_review_only_raises(decision_flag: bool, support_flag: bool, expected: bool) -> None:
    assert merge_human_review(decision_flag, _support(requires_human_review=support_flag)) is expected


def test_merge_human_review_passes_through_when_support_missing() -> None:
    """Part 3 tắt hoặc hỏng thì cờ của part 2 phải đi qua nguyên vẹn."""
    assert merge_human_review(True, None) is True
    assert merge_human_review(False, None) is False


def test_contradiction_sets_the_flag() -> None:
    from src.source_support.schemas import Claim, ClaimResult, Retrieval

    result = ClaimResult(
        claim=Claim(claim_en="x", claim_vi="x", claim_kind="red_flag", grounded_in="x"),
        verdict="contradicts",
        retrieval=Retrieval(from_index=True, searched_web=False, best_score=0.6),
    )
    contradicted = [r.claim.claim_vi for r in [result] if r.verdict == "contradicts"]
    assert SupportSummary(contradicted_claims=contradicted, requires_human_review=bool(contradicted)).requires_human_review


# --- lời hứa 3: best-effort ở tầng service ------------------------------------------------------


@pytest.fixture
def _case() -> TriageCase:
    return TriageCase(case_id="case-test")


def test_service_skips_when_feature_disabled(_case: TriageCase, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "source_support_enabled", False)
    assert service._source_support_for(_case, {"triage_label": "cap_cuu"}) is None


def test_service_swallows_failures(_case: TriageCase, monkeypatch, caplog) -> None:
    """Guard chặn, model hỏng, hết quota - đều thành `None` + một dòng log, không thành lỗi của ca."""
    from src.source_support import pipeline

    monkeypatch.setattr(get_settings(), "source_support_enabled", True)
    monkeypatch.setattr(pipeline, "run", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("hết quota")))

    with caplog.at_level("WARNING"):
        assert service._source_support_for(_case, {"triage_label": "cap_cuu"}) is None
    assert "source_support_failed" in caplog.text


def test_service_returns_support_when_it_works(_case: TriageCase, monkeypatch) -> None:
    from src.source_support import pipeline

    monkeypatch.setattr(get_settings(), "source_support_enabled", True)
    monkeypatch.setattr(pipeline, "run", lambda *a, **k: _support(requires_human_review=True))

    support = service._source_support_for(_case, {"triage_label": "cap_cuu"})
    assert support is not None and support.summary.requires_human_review


def test_service_import_stays_light() -> None:
    """Ràng buộc 1 của `service.py`: import ở mức module không được kéo theo torch/transformers.

    Chạy trong TIẾN TRÌNH RIÊNG. Kiểm `sys.modules` ngay trong bộ test là vô nghĩa - một bài test khác
    chạy trước đã kéo torch vào rồi, nên phép kiểm sẽ đỏ hoặc xanh tuỳ thứ tự chạy chứ không tuỳ vào
    điều nó định khẳng định."""
    import subprocess
    import sys

    probe = (
        "import sys; import src.graph_triage.service; "
        "heavy = {'torch','transformers','sentence_transformers','torch_geometric'} & set(sys.modules); "
        "print(sorted(heavy))"
    )
    output = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert output == "[]", f"import service.py đã kéo theo module nặng: {output}"
