import json
from unittest.mock import Mock

import pytest
from sqlalchemy import select

from src.api import routes
from src.config import get_settings
from src.database import session_scope
from src.models.case_record import ConversationRow
from src.models.schemas import CaseStatus, TriageCase, TriagePriority, TriageProposal
from src.services.infra import provider_router
from src.services.stores.approval_store import approval_store
from src.services.stores.case_store import case_store


class _EchoExtractor:
    """LLM giả: trả về đúng những field cho sẵn, kèm `evidence_span` trích từ chính tin nhắn.

    Cần `evidence_span` thật vì ở LƯỢT MỞ mọi field đều thuộc diện "chưa được hỏi" - giá trị enum/số
    và mọi `"false"` bị loại nếu không trích được nguyên văn (`intake_agent._needs_evidence`). Fake nào
    trả JSON phẳng ở đây sẽ "chứng minh" nhầm rằng guard bị hỏng."""

    def __init__(self, extracted: dict[str, tuple[object, str]]) -> None:
        self.extracted = extracted

    def __call__(self, messages, *, credential=None, temperature=None, max_attempts=3, role=None):
        system = messages[0]["content"]
        # Khớp cụm BẤT BIẾN giữa hai biến thể prompt: lượt hỏi lẻ ghi "Ý CẦN HỎI", lượt hỏi gộp
        # ghi "3 Ý CẦN HỎI" (`intake_agent._batch_scope`).
        if "Ý CẦN HỎI" in system:
            return provider_router.CompletionResult(text="Dạ cho em hỏi thêm ạ?", provider="fake", model="fake")
        payload = {
            key: {"value": value, "evidence_span": evidence}
            for key, (value, evidence) in self.extracted.items()
            if key in system
        }
        return provider_router.CompletionResult(text=json.dumps(payload), provider="fake", model="fake")


@pytest.fixture
def scripted_llm(monkeypatch):
    def _install(extracted: dict[str, tuple[object, str]]):
        monkeypatch.setattr(provider_router, "complete", _EchoExtractor(extracted))

    return _install


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_demo_ui(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert "VMedTriage" in response.text


@pytest.mark.asyncio
async def test_chat_empty_message(client, patient_headers):
    response = await client.post("/api/v1/chat", json={"message": ""}, headers=patient_headers)
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_agent_status(client):
    response = await client.get("/api/v1/status")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_documented_emergency_does_not_call_advisory_graph_model(monkeypatch):
    """With C6 disabled, escalated cases retain the prior no-graph behavior."""
    graph_decide = Mock()
    monkeypatch.setattr(routes.graph_triage_service, "decide_for_case", graph_decide)
    monkeypatch.setattr(get_settings(), "graph_triage_mode", "ensemble")

    case = TriageCase(status=CaseStatus.ESCALATED, summary_ready=True)
    await routes._attach_graph_decision(case, previous=None)

    graph_decide.assert_not_called()
    assert case.graph_decision is None


@pytest.mark.asyncio
async def test_safety_gate_allows_c6_for_escalated_case(monkeypatch):
    graph_decide = Mock(return_value={"triage_label": "cap_cuu", "safety_gate": {}})
    monkeypatch.setattr(routes.graph_triage_service, "decide_for_case", graph_decide)
    monkeypatch.setattr(get_settings(), "graph_triage_mode", "c6")

    case = TriageCase(status=CaseStatus.ESCALATED, summary_ready=True)
    await routes._attach_graph_decision(case, previous=None)

    # Hai kwarg báo tiến trình luôn được truyền, kể cả khi rỗng - `/chat` thường không có ai
    # nghe. Điều bài test này khẳng định là ca nào được đưa vào, không phải hình dạng lời gọi.
    graph_decide.assert_called_once_with(case, on_progress=None, on_token=None)
    assert case.graph_decision == {"triage_label": "cap_cuu", "safety_gate": {}}


def test_c6_priority_mapping_only_raises():
    case = TriageCase(
        triage_proposal=TriageProposal(priority=TriagePriority.SELF_CARE, reason="rule baseline"),
    )

    assert routes._raise_priority_from_c6(case, {"triage_label": "cap_cuu"}) == (
        TriagePriority.SELF_CARE,
        TriagePriority.EMERGENCY,
    )
    assert case.triage_proposal.priority is TriagePriority.EMERGENCY
    assert routes._raise_priority_from_c6(case, {"triage_label": "theo_doi_tai_nha"}) is None
    assert case.triage_proposal.priority is TriagePriority.EMERGENCY


@pytest.mark.asyncio
async def test_safety_gate_does_not_change_approved_case(client):
    case = TriageCase(
        case_id="c6-approved-case",
        status=CaseStatus.APPROVED,
        triage_proposal=TriageProposal(priority=TriagePriority.SELF_CARE, reason="nurse decision"),
    )
    case_store.save(case)

    routes._persist_safety_gate_result(
        case.case_id,
        {"triage_label": "cap_cuu", "safety_gate": {}, "escalated_by": ["direct"]},
    )

    restored = case_store.get(case.case_id)
    assert restored is not None
    assert restored.graph_decision is None
    assert restored.triage_proposal.priority is TriagePriority.SELF_CARE
    assert approval_store.audit_for_case(case.case_id)[-1].action == "completed_after_approval"


@pytest.mark.asyncio
async def test_safety_gate_persists_and_raises_pending_case(client):
    case = TriageCase(
        case_id="c6-pending-case",
        status=CaseStatus.ESCALATED,
        triage_proposal=TriageProposal(priority=TriagePriority.SELF_CARE, reason="rule baseline"),
    )
    case_store.save(case)
    decision = {"triage_label": "cap_cuu", "safety_gate": {}, "escalated_by": ["documented_rule"]}

    routes._persist_safety_gate_result(case.case_id, decision)

    restored = case_store.get(case.case_id)
    assert restored is not None
    assert restored.graph_decision == decision
    assert restored.triage_proposal.priority is TriagePriority.EMERGENCY
    audit = approval_store.audit_for_case(case.case_id)
    assert audit[-1].action == "raise_priority_from_c6"
    assert audit[-1].old_value == TriagePriority.SELF_CARE.value
    assert audit[-1].new_value == TriagePriority.EMERGENCY.value


@pytest.mark.asyncio
async def test_list_mcp_tool_descriptors(client, nurse_headers):
    response = await client.get("/api/v1/tools", headers=nurse_headers)

    assert response.status_code == 200
    data = response.json()
    tool_names = {tool["name"] for tool in data}
    assert "clinical_guideline_search" in tool_names
    assert "snomed_concept_lookup" in tool_names


@pytest.mark.asyncio
async def test_unconfigured_mcp_tool_call_returns_503(client, nurse_headers):
    response = await client.post(
        "/api/v1/tools/clinical_guideline_search/call",
        json={"arguments": {"symptom_group": "chest_pain", "query": "chest pain triage"}},
        headers=nurse_headers,
    )

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_chat_routes_red_flag_alerts_patient_immediately(client, patient_headers):
    # Tin nhắn đổi từ "đau ngực" sang "co giật": `/api/v1/chat` giờ chạy AGENT FEVER, mà agent này chỉ
    # có protocol cho sốt - xem `test_chat_non_fever_complaint_has_no_red_flag_coverage_yet` bên dưới.
    # Ý ĐỊNH của test không đổi: có red flag -> chốt đỏ NGAY lượt đầu, không lộ proposal/rule nội bộ.
    response = await client.post(
        "/api/v1/chat",
        json={"message": "Con em đang sốt cao, giờ tay chân đang co giật."},
        headers=patient_headers,
    )

    assert response.status_code == 200
    data = response.json()
    # Chỉ hiển thị hướng dẫn cấp cứu cố định; không lộ proposal/rule nội bộ.
    assert data["triage_proposal"] is None
    assert data["red_flags"] == []
    assert data["status"] == "escalated"
    assert data["requires_human_approval"] is False
    assert data["pipeline_trace"] == []
    assert "115" in data["response"]


@pytest.mark.asyncio
async def test_chat_non_fever_complaint_is_scanned_by_universal_red_flag_rules(
    client, patient_headers, scripted_llm,
):
    """VÁ LỖ HỔNG: than phiền ngoài sốt lại được luật đỏ quét.

    Từ lúc `/chat` chuyển sang agent, chỉ có protocol SỐT tồn tại nên "đau ngực, đi vài bước là hụt
    hơi" không còn luật nào bắt - trước đó `RED_FLAG_RULES` (`src/config.py`) bắt ngay lượt đầu. Giờ
    lượt mở chọn `GENERIC_PROTOCOL`, và protocol đó chạy đúng bộ rule đỏ PHỔ QUÁT của
    `common_safety/rules.py`."""
    scripted_llm({
        "chest_pain": ("true", "đau ngực"),
        "breathing_difficulty": ("severe", "đi vài bước là hụt hơi"),
    })
    response = await client.post(
        "/api/v1/chat",
        json={"message": "Tôi đau ngực từ sáng, đi vài bước là hụt hơi."},
        headers=patient_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "escalated"
    assert "115" in data["response"]
    # Vẫn không lộ kết luận nội bộ cho bệnh nhân (P0-2) - y như nhánh sốt.
    assert data["triage_proposal"] is None
    assert data["red_flags"] == []


@pytest.mark.asyncio
async def test_chat_non_fever_case_is_not_labelled_as_fever(client, patient_headers, nurse_headers, scripted_llm):
    """Ca ngoài sốt KHÔNG được gắn `symptom_group="fever"` ở bất kỳ trường downstream nào.

    Đây là lỗi DỮ LIỆU chứ không phải hiển thị: JSON này là feature đầu vào của model xác suất bên
    triage, gắn nhãn sai làm hỏng dữ liệu huấn luyện chứ không chỉ hỏng một phiên."""
    scripted_llm({"chief_complaint": ("đau bụng", "đau bụng"), "complaint_site": ("bụng", "đau bụng")})
    chat = await client.post(
        "/api/v1/chat", json={"message": "Tôi đau bụng hai hôm nay."}, headers=patient_headers,
    )
    case_id = chat.json()["case_id"]

    case = await client.get(f"/api/v1/cases/{case_id}", headers=nurse_headers)

    assert case.status_code == 200
    structured = case.json()["structured_data"]
    assert structured["symptom_group"] == "abdominal"
    # F09 dùng nhiệt độ trong mapping đau bụng, nhưng các field điều trị sốt vẫn không được lẫn vào.
    assert "temp_c" in structured["fields"]
    assert "antipyretic_taken" not in structured["fields"]


@pytest.mark.asyncio
async def test_chat_opening_turn_answers_a_greeting_without_starting_the_checklist(
    client, patient_headers, scripted_llm,
):
    """"xin chào" chưa đủ để chọn protocol - KHÔNG được lao vào bộ câu hỏi lâm sàng.

    Nhảy sang "bé hay người lớn, bao nhiêu tuổi" khi người ta mới chào là cách nhanh nhất để người
    bệnh bỏ cuộc, và tệ hơn: protocol lúc đó bị chọn bằng cách đoán.

    ⚠️ Đổi 2026-08-23: bài này trước đây đòi câu trả lời là NGUYÊN VĂN câu mở ("khó chịu thế nào").
    Lane chitchat (§4.10) nay trả lời lời chào rồi mới kéo về hỏi bệnh, nên phần được kiểm là ĐƯỜNG
    ĐI (chưa vào checklist) chứ không phải câu chữ."""
    scripted_llm({})
    response = await client.post(
        "/api/v1/chat", json={"message": "xin chào"}, headers=patient_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "collecting_information"
    # Chua vao protocol nao thi chua co structured_data - lượt mở không dựng phiếu.
    assert data["structured_data"] is None
    reply = data["response"].casefold()
    assert "khó chịu" in reply or "sức khỏe" in reply


@pytest.mark.asyncio
async def test_nurse_can_approve_case(client, patient_headers, nurse_headers):
    chat_response = await client.post(
        "/api/v1/chat",
        json={"message": "Tôi đau ngực từ sáng, mức đau 6/10, không lan tay."},
        headers=patient_headers,
    )
    case_id = chat_response.json()["case_id"]

    review_response = await client.post(
        f"/api/v1/cases/{case_id}/review",
        json={
            "action": "approve",
            "approved_response": "Phản hồi đã được điều dưỡng duyệt.",
        },
        headers=nurse_headers,
    )

    assert review_response.status_code == 200
    data = review_response.json()
    assert data["status"] == "approved"
    assert data["patient_visible_response"] == "Phản hồi đã được điều dưỡng duyệt."


# --- streaming (SSE) ---------------------------------------------------------------------------


def _sse_events(body: str) -> list[tuple[str, object]]:
    """Tách khung SSE thành `(tên sự kiện, dữ liệu)`. Viết ở đây thay vì dùng thư viện: đúng cái
    định dạng mà `api.js` phải tự tách, nên test phải đọc y hệt cách client đọc."""
    events = []
    for frame in body.split("\n\n"):
        lines = [line for line in frame.splitlines() if line.strip()]
        name = next((line.split(":", 1)[1].strip() for line in lines if line.startswith("event:")), None)
        raw = next((line.split(":", 1)[1].strip() for line in lines if line.startswith("data:")), None)
        if name and raw is not None:
            events.append((name, json.loads(raw)))
    return events


@pytest.mark.asyncio
async def test_chat_stream_emits_status_tokens_then_the_same_body_as_chat(
    client, patient_headers, scripted_llm, monkeypatch,
):
    """Sự kiện `done` phải mang NGUYÊN VĂN body của `ChatResponse`: client dùng lại đúng đường xử lý
    của `/chat`, nên lệch một field là một nhánh xử lý riêng phải viết thêm ở frontend."""
    scripted_llm({"fever_reported": ("true", "sốt")})

    def fake_stream(messages, *, temperature=None, max_attempts=3, credential=None, role=None):
        yield "Dạ cho "
        yield "em hỏi thêm ạ?"

    monkeypatch.setattr(provider_router, "complete_stream", fake_stream)

    response = await client.post(
        "/api/v1/chat/stream", json={"message": "Tôi bị sốt từ hôm qua."}, headers=patient_headers,
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _sse_events(response.text)
    names = [name for name, _ in events]
    assert names[0] == "status"
    assert "token" in names
    assert names[-1] == "done"

    tokens = "".join(data for name, data in events if name == "token")
    # KHÔNG khẳng định chữ nào do model viết. Lượt đầu của mọi ca giờ là câu quét cấp cứu phổ quát
    # (stage `E`, `screening.probe_question`) - văn bản TĨNH, cố ý không qua LLM. Bài này viết từ
    # trước khi stage đó tồn tại nên nó chờ đúng chuỗi mà `fake_stream` phát ra, và chờ mãi.
    #
    # Bất biến thật sự đáng canh ở đây không phải "ai viết câu đó", mà là HAI KÊNH KHỚP NHAU: những
    # gì người bệnh đọc dần qua `token` phải đúng bằng câu nằm trong `done`. Lệch nhau nghĩa là màn
    # hình hiện một đằng còn bản ghi lưu một nẻo - và đó mới là thứ làm vỡ frontend.
    body = next(data for name, data in events if name == "done")
    assert set(body) >= {"case_id", "response", "status", "requires_human_approval"}
    assert tokens == body["response"]


@pytest.mark.asyncio
async def test_chat_stream_requires_a_patient_token(client):
    """`^/api/v1/chat/?$` KHÔNG phủ `/chat/stream` - thiếu policy riêng thì endpoint này chạy agent
    mà không cần token nào."""
    response = await client.post("/api/v1/chat/stream", json={"message": "Tôi bị sốt."})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_chat_stream_rejects_another_patients_case_before_streaming(
    client, patient_headers, scripted_llm,
):
    """Lỗi quyền phải là HTTP status THẬT, không phải một sự kiện `error` trong thân stream - header
    đã gửi đi rồi thì không đặt lại status được nữa."""
    from src.services.stores.case_store import case_store

    scripted_llm({"fever_reported": ("true", "sốt")})
    first = await client.post(
        "/api/v1/chat", json={"message": "Tôi bị sốt."}, headers=patient_headers,
    )
    case_id = first.json()["case_id"]

    # Gán case cho một bệnh nhân khác - rẻ và tường minh hơn việc dựng thêm một tài khoản thật, mà
    # vẫn chạm đúng nhánh cần kiểm (`_prepare_chat_turn` so `patient_id`).
    stolen = case_store.get(case_id)
    stolen.patient_id = (stolen.patient_id or 0) + 999
    case_store.save(stolen)

    response = await client.post(
        "/api/v1/chat/stream",
        json={"message": "Cho tôi xem", "case_id": case_id},
        headers=patient_headers,
    )

    assert response.status_code == 403
    assert not response.headers["content-type"].startswith("text/event-stream")


@pytest.mark.asyncio
async def test_a_closed_chat_turn_writes_the_nurse_summary_to_the_conversation_row(
    client, patient_headers,
):
    """LỖ HỔNG ĐÃ TỪNG CÓ THẬT: `_remember_nurse_summary` tồn tại nhưng KHÔNG ai gọi.

    Mọi test M3 cũ gọi thẳng `conversation_store.save_nurse_summary`, nên chúng vẫn xanh trong khi
    đường thật không bao giờ ghi được một phiếu nào - `recent_summaries_for_user` chỉ lấy hàng CÓ
    `nurse_summary_json`, cột rỗng nghĩa là không bao giờ có 3 phiếu để chắt lọc. Test này đi qua
    route, không đi qua store."""
    response = await client.post(
        "/api/v1/chat",
        json={"message": "Con em đang sốt cao, giờ tay chân đang co giật."},
        headers=patient_headers,
    )
    assert response.status_code == 200
    case_id = response.json()["case_id"]

    with session_scope() as db:
        row = db.scalars(
            select(ConversationRow).where(ConversationRow.conversation_id == case_id)
        ).one()
        assert row.nurse_summary_json is not None
