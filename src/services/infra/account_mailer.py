"""Gửi email tài khoản (mã xác thực, đặt lại mật khẩu) qua SMTP.

**Vì sao file này được viết lại 2026-08-23.** Bản trước nuốt mọi lỗi SMTP rồi trả `None`, nên người
gọi không có cách nào biết thư có đi hay không. Hệ quả đo được trên production:

```text
đăng ký  ->  ghi user thành công  ->  HTTP 201  ->  gửi thư HỎNG (im lặng)
         ->  người dùng không bao giờ nhận mã
         ->  email_verified = false mãi mãi
         ->  đăng nhập luôn 403 "Email chưa được xác thực"
```

Người dùng thấy tài khoản của mình nằm trong hệ thống mà không vào được, còn log thì chỉ có một dòng
`Account email delivery failed` lẫn giữa mọi thứ khác. **Một lỗi hạ tầng không được phép biểu hiện
thành một lỗi của người dùng.**

Hai thay đổi, và cả hai đều nhỏ:

1. **Trả `DeliveryResult` thay vì `None`** - người gọi biết được thư đi hay không, và biết vì sao.
2. **Hỗ trợ SMTP over SSL (cổng 465)** bên cạnh STARTTLS (587). Nhiều nền tảng PaaS chặn outbound
   587 nhưng mở 465; trước đây không có đường nào để thử cổng còn lại.
"""

from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from src.config import get_settings

logger = logging.getLogger(__name__)

SSL_PORT = 465
"""Cổng SMTPS (TLS ngầm định). Cổng 587 dùng STARTTLS - hai giao thức khác nhau, không phải hai tên
của một thứ: nói STARTTLS với cổng 465 sẽ treo cho tới khi hết thời gian chờ."""


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    """Kết quả một lần gửi. `reason` là mã ổn định để log/đo, không phải câu cho người đọc."""

    delivered: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.delivered


DELIVERED = DeliveryResult(True)
NOT_CONFIGURED = DeliveryResult(False, "smtp_not_configured")
NO_SENDER = DeliveryResult(False, "smtp_from_email_missing")
DEV_CONSOLE = DeliveryResult(False, "development_console")
"""Môi trường dev không cấu hình SMTP: mã được in ra log thay vì gửi đi. KHÔNG tính là đã gửi - gọi
nó là thành công thì test và endpoint không phân biệt nổi "đã gửi" với "in ra màn hình"."""


class AccountMailer:
    """Gửi email tài khoản, có đường lùi ra console cho môi trường dev."""

    def send_email(self, *, recipient: str, subject: str, body: str, development_value: str) -> DeliveryResult:
        settings = get_settings()
        if not settings.smtp_host:
            if settings.app_env == "production":
                logger.error("Account email NOT sent to %s: SMTP is not configured.", recipient)
                return NOT_CONFIGURED
            logger.warning("Development account email for %s: %s", recipient, development_value)
            return DEV_CONSOLE

        sender = settings.smtp_from_email or settings.smtp_username
        if not sender:
            logger.error("Account email NOT sent to %s: SMTP_FROM_EMAIL is not configured.", recipient)
            return NO_SENDER

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = sender
        message["To"] = recipient
        message.set_content(body)

        try:
            with self._connect() as smtp:
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException) as error:
            # Vẫn KHÔNG ném ra ngoài - một lỗi gửi thư không được làm hỏng cả lần đăng ký, tài khoản
            # đã tạo xong và người dùng còn đường gửi lại mã. Nhưng lần này người gọi BIẾT là hỏng.
            logger.exception("Account email delivery to %s failed.", recipient)
            return DeliveryResult(False, type(error).__name__)
        return DELIVERED

    def probe(self) -> DeliveryResult:
        """Thử bắt tay + đăng nhập SMTP mà KHÔNG gửi thư gì.

        Dùng cho endpoint gửi lại mã: nó cần trả lời "hệ thống thư có sống không" mà không được tiết
        lộ email đó có tồn tại hay không (§ chống dò tài khoản). Câu hỏi đó thuộc về máy chủ, nên
        phải trả lời được kể cả khi chẳng có gì để gửi."""
        settings = get_settings()
        if not settings.smtp_host:
            return NOT_CONFIGURED if settings.app_env == "production" else DEV_CONSOLE
        try:
            with self._connect() as smtp:
                smtp.noop()
        except (OSError, smtplib.SMTPException) as error:
            logger.warning("SMTP probe failed: %s: %s", type(error).__name__, error)
            return DeliveryResult(False, type(error).__name__)
        return DELIVERED

    def _connect(self) -> smtplib.SMTP:
        """Mở phiên SMTP đã sẵn sàng gửi (đã mã hoá + đã đăng nhập nếu có tài khoản).

        Chọn giao thức theo cấu hình, và cổng 465 tự suy ra SSL: đó là quy ước phổ biến tới mức bắt
        người triển khai vừa đổi cổng vừa nhớ bật thêm một cờ là một cái bẫy chứ không phải một lựa
        chọn."""
        settings = get_settings()
        use_ssl = settings.smtp_use_ssl or settings.smtp_port == SSL_PORT
        if use_ssl:
            smtp: smtplib.SMTP = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=10)
        else:
            smtp = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)
            if settings.smtp_use_tls:
                smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        return smtp

    def send_email_verification_code(self, *, recipient: str, code: str) -> DeliveryResult:
        settings = get_settings()
        return self.send_email(
            recipient=recipient,
            subject="Mã xác thực email VMedTriage",
            body=f"Mã xác thực email của bạn là: {code}\n\nMã có hiệu lực trong {settings.email_verification_code_expire_minutes} phút.",
            development_value=f"Email verification code: {code}",
        )

    def send_password_reset_email(self, *, recipient: str, reset_url: str) -> DeliveryResult:
        settings = get_settings()
        return self.send_email(
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
