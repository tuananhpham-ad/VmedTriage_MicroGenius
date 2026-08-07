from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.config import get_settings
from src.database import configure_database, create_tables, dispose_database
from src.main import app
from src.services.account_mailer import account_mailer


@pytest_asyncio.fixture
async def client(tmp_path):
    """Async HTTP client for testing API endpoints."""
    settings = get_settings()
    previous_nurse_code = settings.nurse_registration_code
    settings.nurse_registration_code = "test-nurse-code"
    database_path = (tmp_path / "test.db").as_posix()
    configure_database(f"sqlite+pysqlite:///{database_path}")
    create_tables()
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        dispose_database()
        settings.nurse_registration_code = previous_nurse_code


async def _create_session(client: AsyncClient, role: str) -> dict[str, str]:
    email = f"{role}@example.com"
    register_payload = {
        "email": email,
        "password": "StrongPass123!",
        "confirm_password": "StrongPass123!",
        "full_name": "Test Patient" if role == "patient" else "Test Nurse",
        "username": f"test-{role}",
        "phone_number": "0900000001" if role == "patient" else "0900000002",
        "date_of_birth": "1990-01-01",
        "gender": "prefer_not_to_say",
        "avatar_data_url": "data:image/png;base64,AAAAAAAAAAAAAAAA",
        "terms_accepted": True,
        "role": role,
    }
    if role == "nurse":
        register_payload["nurse_registration_code"] = "test-nurse-code"
        register_payload.update(
            {
                "professional_license": "LIC-TEST-001",
                "workplace": "Test Hospital",
                "department": "Emergency",
                "bio": "Test nurse profile.",
            }
        )
    register_response = await client.post("/api/v1/register", json=register_payload)
    assert register_response.status_code == 201, register_response.text

    delivered_codes: list[str] = []
    original_sender = account_mailer.send_email_verification_code
    account_mailer.send_email_verification_code = lambda *, recipient, code: delivered_codes.append(code)
    try:
        resend_response = await client.post(
            "/api/v1/auth/email-verification/resend", json={"email": email}
        )
    finally:
        account_mailer.send_email_verification_code = original_sender
    assert resend_response.status_code == 202, resend_response.text
    verify_response = await client.post(
        "/api/v1/auth/email-verification/confirm",
        json={"email": email, "code": delivered_codes[0]},
    )
    assert verify_response.status_code == 200, verify_response.text

    login_response = await client.post(
        "/api/v1/login",
        json={"email": email, "password": "StrongPass123!"},
    )
    assert login_response.status_code == 200, login_response.text
    return {"Authorization": f"Bearer {login_response.json()['access_token']}"}


@pytest_asyncio.fixture
async def patient_headers(client):
    return await _create_session(client, "patient")


@pytest_asyncio.fixture
async def nurse_headers(client):
    return await _create_session(client, "nurse")


@pytest.fixture
def mock_llm():
    """Mock LLM to avoid calling OpenAI during tests.

    Usage in test:
        def test_something(mock_llm):
            # LLM calls will return mock response instead of hitting OpenAI
            ...
    """
    mock = AsyncMock()
    mock.ainvoke.return_value = AsyncMock(content="Mocked LLM response")
    return mock
