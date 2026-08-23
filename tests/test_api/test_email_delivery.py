"""Luồng xác thực email khi HỆ THỐNG THƯ HỎNG — sự cố production 2026-08-23.

Triệu chứng người dùng báo: *"đăng ký xong, thấy tài khoản trong DB, nhưng đăng nhập không được."*

Chuỗi nhân quả:

```text
đăng ký  ->  ghi user OK  ->  HTTP 201  ->  gửi thư HỎNG (bản cũ nuốt lỗi, trả None)
         ->  người dùng không bao giờ nhận mã  ->  email_verified = false
         ->  login luôn 403
```

Không bài nào ở đây kiểm SMTP thật. Chúng kiểm thứ đã biến một lỗi hạ tầng thành một lỗi của người
dùng: **hệ thống nói dối rằng thư đã được gửi.**
"""

from __future__ import annotations

import smtplib

import pytest

from src.services.infra.account_mailer import DELIVERED, AccountMailer, account_mailer
from tests.test_api.test_auth import registration_payload


def _broken_smtp(monkeypatch, error: Exception | None = None) -> None:
    """Giả lập đúng thứ đang nghi trên production: cổng SMTP mở không được."""
    def explode(*_args, **_kwargs):
        raise error or smtplib.SMTPConnectError(421, "cannot connect")

    monkeypatch.setattr(AccountMailer, "_connect", explode)


# --- đăng ký ------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_registration_still_succeeds_when_the_mail_server_is_down(client, monkeypatch):
    """Tài khoản KHÔNG bị rollback: người dùng đã điền xong form, và họ còn đường gửi lại mã.

    Đây là hành vi cố ý giữ nguyên - bài này tồn tại để lần sau ai đó "sửa" bằng cách rollback thì
    biết là đang đổi một quyết định, không phải sửa một lỗi."""
    _broken_smtp(monkeypatch)

    response = await client.post("/api/v1/register", json=registration_payload())

    assert response.status_code == 201
    assert response.json()["email_verified"] is False


@pytest.mark.asyncio
async def test_a_user_created_while_mail_was_down_cannot_log_in(client, monkeypatch):
    """CA CHẶN: đây chính xác là thứ người dùng báo. Row có trong DB, mật khẩu đúng, vẫn 403.

    Bài này KHÔNG khẳng định 403 là sai - cổng xác thực email là có chủ đích. Nó khẳng định rằng
    con đường dẫn tới đây tồn tại thật, để hai bài dưới (báo đúng sự thật khi gửi lại) có nghĩa."""
    _broken_smtp(monkeypatch)
    await client.post("/api/v1/register", json=registration_payload())

    login = await client.post(
        "/api/v1/login",
        json={"email": "patient.one@example.com", "password": "StrongPass123!"},
    )

    assert login.status_code == 403
    assert "chưa được xác thực" in login.json()["detail"]


# --- gửi lại mã: chỗ người dùng kẹt sẽ tới -------------------------------------------------------


@pytest.mark.asyncio
async def test_resending_reports_the_outage_instead_of_pretending_to_send(client, monkeypatch):
    """⚠️ Đây là lỗi UX nặng nhất của bản cũ: endpoint trả 202 "đã gửi mã mới" trong khi không có
    thư nào đi cả.

    Nghe 202 ba lần rồi vẫn không thấy thư thì người dùng kết luận mình gõ sai email, chứ không kết
    luận hệ thống hỏng - nên họ không báo cho ai, và sự cố kéo dài đúng bằng thời gian không ai nhìn
    vào log."""
    _broken_smtp(monkeypatch)
    await client.post("/api/v1/register", json=registration_payload())

    resend = await client.post(
        "/api/v1/auth/email-verification/resend", json={"email": "patient.one@example.com"},
    )

    assert resend.status_code == 503
    assert "sự cố" in resend.json()["detail"]


@pytest.mark.asyncio
async def test_the_outage_reply_does_not_leak_whether_an_account_exists(client, monkeypatch):
    """503 phải nói về MÁY CHỦ THƯ, không nói về tài khoản.

    Nếu chỉ email có thật mới nhận 503 thì endpoint này thành một máy dò tài khoản. Vì vậy khi không
    có tài khoản nào, `probe()` hỏi thẳng SMTP thay vì gửi gì - hai nhánh cho ra cùng một mã lỗi."""
    _broken_smtp(monkeypatch)

    unknown = await client.post(
        "/api/v1/auth/email-verification/resend", json={"email": "khong-ton-tai@example.com"},
    )

    assert unknown.status_code == 503


@pytest.mark.asyncio
async def test_resending_returns_202_when_mail_actually_goes_out(client, monkeypatch):
    """Đường thành công phải giữ nguyên thông điệp mơ hồ - đó là thứ chặn dò tài khoản."""
    sent: list[str] = []
    monkeypatch.setattr(
        account_mailer,
        "send_email_verification_code",
        lambda *, recipient, code: (sent.append(code), DELIVERED)[1],
    )
    await client.post("/api/v1/register", json=registration_payload())

    resend = await client.post(
        "/api/v1/auth/email-verification/resend", json={"email": "patient.one@example.com"},
    )

    assert resend.status_code == 202
    assert "Nếu tài khoản" in resend.json()["message"]
    assert len(sent) == 2  # một lần lúc đăng ký, một lần gửi lại


# --- tầng mailer --------------------------------------------------------------------------------


def test_the_mailer_reports_why_it_failed_instead_of_swallowing_the_error(monkeypatch):
    """`send_email` vẫn KHÔNG ném (một lỗi gửi thư không được làm hỏng lần đăng ký), nhưng người gọi
    phải biết được là hỏng - đó là toàn bộ khác biệt so với bản cũ."""
    _broken_smtp(monkeypatch)
    from src.config import get_settings

    monkeypatch.setattr(get_settings(), "smtp_host", "smtp.example.com")
    monkeypatch.setattr(get_settings(), "smtp_from_email", "no-reply@example.com")

    result = account_mailer.send_email(
        recipient="ai-do@example.com", subject="x", body="y", development_value="z",
    )

    assert result.delivered is False
    assert result.reason == "SMTPConnectError"
    assert not result  # __bool__ theo trạng thái gửi


def test_port_465_uses_implicit_ssl_without_a_second_flag(monkeypatch):
    """Cổng 465 là SMTPS (TLS ngầm định), 587 là STARTTLS - hai giao thức khác nhau. Nói STARTTLS với
    465 sẽ treo tới lúc hết thời gian chờ, nên cổng phải tự quyết giao thức thay vì bắt người triển
    khai nhớ bật thêm một cờ."""
    from src.config import get_settings

    calls: list[str] = []
    monkeypatch.setattr(get_settings(), "smtp_host", "smtp.example.com")
    monkeypatch.setattr(get_settings(), "smtp_port", 465)
    monkeypatch.setattr(get_settings(), "smtp_use_ssl", False)  # cố ý TẮT cờ
    monkeypatch.setattr(get_settings(), "smtp_username", "")
    monkeypatch.setattr(smtplib, "SMTP_SSL", lambda *a, **k: calls.append("ssl") or _FakeSMTP())
    monkeypatch.setattr(smtplib, "SMTP", lambda *a, **k: calls.append("plain") or _FakeSMTP())

    AccountMailer()._connect()

    assert calls == ["ssl"]


class _FakeSMTP:
    def starttls(self) -> None:
        raise AssertionError("STARTTLS không được gọi trên cổng 465")

    def login(self, *_args) -> None: ...
    def noop(self) -> None: ...
    def __enter__(self): return self
    def __exit__(self, *_exc) -> None: ...
