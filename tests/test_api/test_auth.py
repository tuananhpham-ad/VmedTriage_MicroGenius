import pytest


@pytest.mark.asyncio
async def test_register_and_login_return_safe_user_and_token(client):
    register_response = await client.post(
        "/api/v1/register",
        json={
            "email": "Patient.One@Example.com",
            "password": "StrongPass123!",
            "full_name": "Patient One",
            "role": "patient",
        },
    )

    assert register_response.status_code == 201
    registered = register_response.json()
    assert registered["email"] == "patient.one@example.com"
    assert registered["role"] == "patient"
    assert "password" not in registered
    assert "password_hash" not in registered

    login_response = await client.post(
        "/api/v1/login",
        json={"email": "patient.one@example.com", "password": "StrongPass123!"},
    )

    assert login_response.status_code == 200
    session = login_response.json()
    assert session["token_type"] == "bearer"
    assert session["access_token"]
    assert session["expires_in"] == 3600
    assert session["user"]["role"] == "patient"

    me_response = await client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {session['access_token']}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "patient.one@example.com"


@pytest.mark.asyncio
async def test_duplicate_registration_is_rejected(client):
    payload = {
        "email": "duplicate@example.com",
        "password": "StrongPass123!",
        "full_name": "Duplicate User",
        "role": "patient",
    }
    assert (await client.post("/api/v1/register", json=payload)).status_code == 201
    response = await client.post("/api/v1/register", json=payload)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_login_with_wrong_password_is_rejected(client):
    await client.post(
        "/api/v1/register",
        json={
            "email": "wrong-password@example.com",
            "password": "StrongPass123!",
            "full_name": "Wrong Password",
            "role": "patient",
        },
    )
    response = await client.post(
        "/api/v1/login",
        json={"email": "wrong-password@example.com", "password": "incorrect"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_nurse_registration_requires_private_code(client):
    response = await client.post(
        "/api/v1/register",
        json={
            "email": "nurse-denied@example.com",
            "password": "StrongPass123!",
            "full_name": "Nurse Denied",
            "role": "nurse",
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_middleware_allows_correct_role(client, nurse_headers):
    response = await client.get("/api/v1/nurse/queue", headers=nurse_headers)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_middleware_blocks_wrong_role(client, patient_headers):
    response = await client.get("/api/v1/nurse/queue", headers=patient_headers)
    assert response.status_code == 403
    assert "patient" in response.json()["detail"]


@pytest.mark.asyncio
async def test_middleware_requires_bearer_token(client):
    response = await client.get("/api/v1/nurse/queue")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
