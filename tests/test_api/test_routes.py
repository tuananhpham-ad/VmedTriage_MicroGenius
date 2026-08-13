import pytest


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
async def test_chat_non_fever_complaint_has_no_red_flag_coverage_yet(client, patient_headers):
    """LỖ HỔNG ĐÃ BIẾT, ghi lại để nó hiện ra trong CI thay vì nằm im.

    `/api/v1/chat` đã chuyển từ pipeline rule-based đa triệu chứng sang agent fever. Agent fever chỉ
    có protocol cho SỐT, nên các than phiền khác (đau ngực, khó thở, đột quỵ...) không còn được luật
    red-flag nào quét nữa - trước đây `RED_FLAG_RULES` trong `src/config.py` bắt được.

    Khi nào có routing đa protocol (chest_pain, breathing...) thì test này PHẢI hỏng - lúc đó xoá nó
    đi, đừng nới assert."""
    response = await client.post(
        "/api/v1/chat",
        json={"message": "Tôi đau ngực từ sáng, đi vài bước là hụt hơi."},
        headers=patient_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "collecting_information"


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
