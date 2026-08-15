from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from src.config import get_settings

logger = logging.getLogger(__name__)


class AccountMailer:
    """Deliver account emails by SMTP, with a development-only console fallback."""

    def send_email(self, *, recipient: str, subject: str, body: str, development_value: str) -> None:
        settings = get_settings()
        if not settings.smtp_host:
            if settings.app_env == "production":
                logger.error("Account email not sent: SMTP is not configured.")
            else:
                logger.warning("Development account email for %s: %s", recipient, development_value)
            return

        sender = settings.smtp_from_email or settings.smtp_username
        if not sender:
            logger.error("Account email not sent: SMTP_FROM_EMAIL is not configured.")
            return

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = sender
        message["To"] = recipient
        message.set_content(body)

        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
                if settings.smtp_use_tls:
                    smtp.starttls()
                if settings.smtp_username:
                    smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException):
            logger.exception("Account email delivery failed.")

    def send_email_verification_code(self, *, recipient: str, code: str) -> None:
        settings = get_settings()
        self.send_email(
            recipient=recipient,
            subject="Mã xác thực email VMedTriage",
            body=f"Mã xác thực email của bạn là: {code}\n\nMã có hiệu lực trong {settings.email_verification_code_expire_minutes} phút.",
            development_value=f"Email verification code: {code}",
        )

    def send_password_reset_email(self, *, recipient: str, reset_url: str) -> None:
        settings = get_settings()
        self.send_email(
            recipient=recipient,
            subject="Đặt lại mật khẩu VMedTriage",
            body=(
                "Bạn vừa yêu cầu đặt lại mật khẩu VMedTriage.\n\n"
                f"Mở liên kết này để đặt mật khẩu mới (có hiệu lực trong {settings.password_reset_token_expire_minutes} phút):\n"
                f"{reset_url}\n\nNếu bạn không yêu cầu thao tác này, hãy bỏ qua email."
            ),
            development_value=f"Password reset link: {reset_url}",
        )


account_mailer = AccountMailer()
