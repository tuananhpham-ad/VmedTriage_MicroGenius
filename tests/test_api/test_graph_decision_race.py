import asyncio

import pytest

from src.api import routes
from src.models.schemas import TriageCase, TriageProposal
from src.services.stores.case_store import case_store


def _make_case(case_id: str) -> TriageCase:
    return TriageCase(
        case_id=case_id,
        conversation=[],
        summary_ready=True,
        status="needs_nurse_review",
        triage_proposal=TriageProposal(priority="Urgent", reason="test"),
    )


@pytest.mark.asyncio
async def test_concurrent_saves_do_not_drop_graph_decision(monkeypatch, client):
    """Vá bug 'trace có, UI không': hai request `/chat` gần như đồng thời cho cùng case_id, mỗi
    request tự đọc `previous` rồi chạy agent vài giây - không khoá thì request lưu SAU cùng thắng và
    có thể ghi đè kết quả tốt của request kia bằng `None`, dù trace agent của request đó chạy thành
    công (xem docstring `_case_locks` trong `src/api/routes.py`)."""
    case_id = "race-case-001"
    routes._case_locks.clear()

    call_order = []

    async def fake_decide(triage_case):
        # Request thứ nhất CHẬM và THẤT BẠI (mô phỏng lỗi mạng thoáng qua -> trả None, best-effort
        # theo docstring `decide_for_case`). Request thứ hai NHANH và THÀNH CÔNG, lưu trước. Nếu
        # không khoá, request thứ nhất lưu SAU cùng và ghi đè kết quả tốt bằng `None` - đúng bug
        # "trace có, UI không".
        if not call_order:
            call_order.append("first")
            await asyncio.sleep(0.05)
            return None
        call_order.append("second")
        return {"triage_label": "theo_doi_tai_nha", "decision_summary": "ổn định, theo dõi tại nhà"}

    def fake_decide_for_case(triage_case):
        # `decide_for_case` chạy đồng bộ trong threadpool thật, ở test này chỉ cần trả kết quả khớp
        # thứ tự gọi để mô phỏng agent chậm/nhanh.
        return asyncio.run(fake_decide(triage_case))

    monkeypatch.setattr(routes.graph_triage_service, "decide_for_case", fake_decide_for_case)

    case_a = _make_case(case_id)
    case_b = _make_case(case_id)

    await asyncio.gather(
        routes._save_with_graph_decision(case_a),
        routes._save_with_graph_decision(case_b),
    )

    saved = case_store.get(case_id)
    assert saved is not None
    assert saved.graph_decision is not None, "graph_decision không được biến mất sau khi hai request chạy gần đồng thời"
    assert saved.graph_decision["triage_label"] == "theo_doi_tai_nha"
