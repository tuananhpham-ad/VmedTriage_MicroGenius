from urllib.parse import parse_qs, urlparse

import pytest

from src.services.infra.account_mailer import DELIVERED, account_mailer


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
        lambda *, recipient, code: (delivered_codes.append(code), DELIVERED)[1],
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
async def test_login_accepts_phone_number(client, monkeypatch):
    delivered_codes: list[str] = []
    monkeypatch.setattr(
        account_mailer,
        "send_email_verification_code",
        lambda *, recipient, code: (delivered_codes.append(code), DELIVERED)[1],
    )
    payload = registration_payload(email="phone.login@example.com", username="phone.login")
    payload["phone_number"] = "0901234578"
    assert (await client.post("/api/v1/register", json=payload)).status_code == 201
    assert delivered_codes
    assert (
        await client.post(
            "/api/v1/auth/email-verification/confirm",
            json={"email": payload["email"], "code": delivered_codes[0]},
        )
    ).status_code == 200
    login_response = await client.post(
        "/api/v1/login", json={"email": payload["phone_number"], "password": payload["password"]}
    )
    assert login_response.status_code == 200
    assert login_response.json()["user"]["phone_number"] == payload["phone_number"]


@pytest.mark.asyncio
async def test_register_accepts_the_streamlined_patient_form(client, monkeypatch):
    monkeypatch.setattr(account_mailer, "send_email_verification_code", lambda **_: DELIVERED)
    response = await client.post(
        "/api/v1/register",
        json={
            "email": "short.form@example.com",
            "phone_number": "0901234569",
            "full_name": "Short Form Patient",
            "password": "StrongPass123!",
            "confirm_password": "StrongPass123!",
            "terms_accepted": True,
            "role": "patient",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["username"] == "short.form"


@pytest.mark.asyncio
async def test_profile_updates_extended_optional_information(client, patient_headers):
    response = await client.put(
        "/api/v1/me",
        headers=patient_headers,
        json={
            "full_name": "Patient Updated",
            "phone_number": "0901234567",
            "date_of_birth": "1990-01-01",
            "gender": "female",
            "address": "Cầu Giấy, Hà Nội",
            "emergency_contact_name": "Người thân",
            "emergency_contact_relationship": "Mẹ",
            "emergency_contact_phone": "0901234599",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["address"] == "Cầu Giấy, Hà Nội"
    assert body["emergency_contact_phone"] == "0901234599"


@pytest.mark.asyncio
async def test_patient_can_update_own_health_profile_but_nurse_cannot(client, patient_headers, nurse_headers):
    initial = await client.get("/api/v1/me/health-profile", headers=patient_headers)
    assert initial.status_code == 200, initial.text
    assert initial.json()["allergy_status"] == "unknown"

    updated = await client.put(
        "/api/v1/me/health-profile",
        headers=patient_headers,
        json={
            "allergy_status": "yes",
            "allergies": "Dị ứng penicillin, từng nổi mẩn",
            "chronic_conditions": ["tieu_duong", "tim_mach"],
            "conditions_note": "Đang theo dõi định kỳ.",
            "current_medications": "Thuốc theo đơn hiện tại",
            "recent_care_status": "none",
            "pregnancy_status": "unknown",
            "recent_note": "Người bệnh chưa nhớ đầy đủ mốc thời gian.",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["chronic_conditions"] == ["tieu_duong", "tim_mach"]
    assert updated.json()["confirmed_at"]

    fetched = await client.get("/api/v1/me/health-profile", headers=patient_headers)
    assert fetched.json()["allergies"] == "Dị ứng penicillin, từng nổi mẩn"
    assert (await client.get("/api/v1/me/health-profile", headers=nurse_headers)).status_code == 403


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


@pytest.mark.asyncio
async def test_case_summary_is_restricted_to_authenticated_nurse(client, patient_headers, nurse_headers):
    path = "/api/v1/cases/no-such-case/summary"

    assert (await client.get(path)).status_code == 401
    assert (await client.get(path, headers=patient_headers)).status_code == 403
    # Nhân viên y tế đi qua middleware; route mới trả 404 vì case không tồn tại.
    assert (await client.get(path, headers=nurse_headers)).status_code == 404


@pytest.mark.asyncio
async def test_demo_login_creates_a_new_test_account_per_call(client):
    """Mỗi lần bấm "Dùng thử" phải là một tài khoản riêng, nếu không hai người demo dùng chung lịch sử ca."""
    first = await client.post("/api/v1/auth/demo-login", json={"role": "patient"})
    second = await client.post("/api/v1/auth/demo-login", json={"role": "nurse"})

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    first_user = first.json()["user"]
    second_user = second.json()["user"]
    assert first_user["username"].startswith("test-patient-")
    assert second_user["username"].startswith("test-nurse-")
    assert first_user["username"] != second_user["username"]
    assert first_user["role"] == "patient"
    assert second_user["role"] == "nurse"


@pytest.mark.asyncio
async def test_demo_login_token_reaches_role_protected_routes(client):
    """Token demo phải dùng được ngay: tài khoản demo bỏ qua xác thực email và mã đăng ký điều dưỡng."""
    response = await client.post("/api/v1/auth/demo-login", json={"role": "nurse"})
    token = response.json()["access_token"]

    queue = await client.get("/api/v1/nurse/queue", headers={"Authorization": f"Bearer {token}"})
    assert queue.status_code == 200


@pytest.mark.asyncio
async def test_demo_login_is_refused_when_disabled(client, monkeypatch):
    from src.config import get_settings

    monkeypatch.setattr(get_settings(), "demo_login_enabled", False)
    response = await client.post("/api/v1/auth/demo-login", json={"role": "patient"})
    assert response.status_code == 403
