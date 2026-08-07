from urllib.parse import parse_qs, urlparse

import pytest

from src.services.account_mailer import account_mailer


def registration_payload(*, email: str = "patient.one@example.com", username: str = "patient.one") -> dict:
    return {
        "email": email,
        "username": username,
        "phone_number": "0901234567",
        "full_name": "Patient One",
        "date_of_birth": "1990-01-01",
        "gender": "female",
        "avatar_data_url": "data:image/png;base64,AAAAAAAAAAAAAAAA",
        "password": "StrongPass123!",
        "confirm_password": "StrongPass123!",
        "terms_accepted": True,
        "role": "patient",
    }


@pytest.mark.asyncio
async def test_register_requires_email_verification_before_login(client, monkeypatch):
    delivered_codes: list[str] = []
    monkeypatch.setattr(
        account_mailer,
        "send_email_verification_code",
        lambda *, recipient, code: delivered_codes.append(code),
    )
    response = await client.post("/api/v1/register", json=registration_payload())
    assert response.status_code == 201
    assert response.json()["email_verified"] is False
    assert delivered_codes

    unverified_login = await client.post(
        "/api/v1/login", json={"email": "patient.one@example.com", "password": "StrongPass123!"}
    )
    assert unverified_login.status_code == 403

    verified = await client.post(
        "/api/v1/auth/email-verification/confirm",
        json={"email": "patient.one@example.com", "code": delivered_codes[0]},
    )
    assert verified.status_code == 200
    login_response = await client.post(
        "/api/v1/login", json={"email": "patient.one@example.com", "password": "StrongPass123!"}
    )
    assert login_response.status_code == 200
    session = login_response.json()
    assert session["user"]["username"] == "patient.one"
    assert session["user"]["email_verified"] is True


@pytest.mark.asyncio
async def test_registration_rejects_weak_password_and_missing_terms(client):
    weak_password = registration_payload(email="weak@example.com", username="weak.user")
    weak_password["password"] = weak_password["confirm_password"] = "weakpass"
    assert (await client.post("/api/v1/register", json=weak_password)).status_code == 422

    missing_terms = registration_payload(email="terms@example.com", username="terms.user")
    missing_terms["terms_accepted"] = False
    assert (await client.post("/api/v1/register", json=missing_terms)).status_code == 422


@pytest.mark.asyncio
async def test_nurse_registration_requires_profile_and_private_code(client):
    payload = registration_payload(email="nurse@example.com", username="nurse.user")
    payload.update({"role": "nurse", "phone_number": "0901234568"})
    assert (await client.post("/api/v1/register", json=payload)).status_code == 422

    payload.update(
        {
            "professional_license": "LIC-123",
            "workplace": "Demo Hospital",
            "department": "Cardiology",
            "bio": "Licensed nurse.",
            "nurse_registration_code": "wrong-code",
        }
    )
    assert (await client.post("/api/v1/register", json=payload)).status_code == 403


@pytest.mark.asyncio
async def test_password_reset_and_change_password(client, patient_headers, monkeypatch):
    delivered_urls: list[str] = []
    monkeypatch.setattr(
        account_mailer,
        "send_password_reset_email",
        lambda *, recipient, reset_url: delivered_urls.append(reset_url),
    )
    requested = await client.post(
        "/api/v1/auth/password-reset/request", json={"email": "patient@example.com"}
    )
    assert requested.status_code == 202
    token = parse_qs(urlparse(delivered_urls[0]).query)["reset_token"][0]
    confirmed = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={
            "token": token,
            "new_password": "NewPassword123!",
            "confirm_new_password": "NewPassword123!",
        },
    )
    assert confirmed.status_code == 200
    assert (
        await client.post(
            "/api/v1/login", json={"email": "patient@example.com", "password": "NewPassword123!"}
        )
    ).status_code == 200

    changed = await client.post(
        "/api/v1/auth/change-password",
        headers=patient_headers,
        json={
            "current_password": "NewPassword123!",
            "new_password": "ChangedPassword123!",
            "confirm_new_password": "ChangedPassword123!",
        },
    )
    assert changed.status_code == 200
    assert (
        await client.post(
            "/api/v1/login", json={"email": "patient@example.com", "password": "ChangedPassword123!"}
        )
    ).status_code == 200


@pytest.mark.asyncio
async def test_middleware_allows_correct_role(client, nurse_headers):
    assert (await client.get("/api/v1/nurse/queue", headers=nurse_headers)).status_code == 200


@pytest.mark.asyncio
async def test_middleware_blocks_wrong_role(client, patient_headers):
    response = await client.get("/api/v1/nurse/queue", headers=patient_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_middleware_requires_bearer_token(client):
    response = await client.get("/api/v1/nurse/queue")
    assert response.status_code == 401
