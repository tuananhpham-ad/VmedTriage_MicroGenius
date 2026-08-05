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
async def test_chat_routes_red_flag_to_nurse_queue(client, patient_headers):
    response = await client.post(
        "/api/v1/chat",
        json={"message": "Tôi đau ngực từ sáng, đi vài bước là hụt hơi."},
        headers=patient_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["triage_proposal"]["priority"] == "Emergency"
    assert data["status"] == "needs_nurse_review"
    assert data["requires_human_approval"] is True
    assert data["pipeline_trace"][-1]["stage"] == "response"
    assert data["pipeline_trace"][-1]["output"]["response"] == data["response"]
    assert "chuyển" in data["response"] or "chuyá»ƒn" in data["response"]


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
