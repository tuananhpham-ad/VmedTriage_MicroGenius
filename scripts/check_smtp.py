"""Chan doan duong gui email tu CHINH moi truong dang chay.

Vi sao can: "dang ky xong khong dang nhap duoc" gan nhu luon la mot loi SMTP im lang, va loi do chi
tai hien duoc o noi ma app dang chay. May cua lap trinh vien gui duoc 587 khong noi len dieu gi ve
mot container tren Azure - nhieu nen tang PaaS chan outbound 587 nhung mo 465.

Chay tren Azure Container Apps:

    az containerapp exec -n vmedtriage -g <resource-group> --command "python -m scripts.check_smtp"

Chay tai may:

    python -m scripts.check_smtp                  # chi bat tay + dang nhap, KHONG gui thu
    python -m scripts.check_smtp --to ban@vd.com  # gui that mot thu thu

Script chi DOC cau hinh va mo ket noi. No khong sua gi, khong ghi DB, va khong bao gio in mat khau.
"""

from __future__ import annotations

import argparse
import smtplib
import socket
import sys
import time

from src.config import get_settings
from src.services.infra.account_mailer import SSL_PORT, account_mailer


def _mask(value: str) -> str:
    if not value:
        return "(trong)"
    return f"{value[:2]}***{value[-1:]} (do dai {len(value)})"


def _report_config() -> None:
    s = get_settings()
    use_ssl = s.smtp_use_ssl or s.smtp_port == SSL_PORT
    print("--- Cau hinh SMTP ---")
    print(f"  host          : {s.smtp_host or '(trong -> KHONG gui duoc o production)'}")
    print(f"  port          : {s.smtp_port}")
    print(f"  giao thuc     : {'SMTPS/SSL ngam dinh' if use_ssl else 'STARTTLS' if s.smtp_use_tls else 'KHONG ma hoa'}")
    print(f"  username      : {s.smtp_username or '(trong)'}")
    print(f"  password      : {_mask(s.smtp_password)}")
    print(f"  from_email    : {s.smtp_from_email or '(trong)'}")
    print(f"  app_env       : {s.app_env}")
    print(f"  han ma xac thuc: {s.email_verification_code_expire_minutes} phut")


def _check_tcp(host: str, port: int) -> bool:
    """Tach rieng buoc mo cong TCP: phan biet 'nen tang chan cong' voi 'sai mat khau'.

    Hai loi nay cung bieu hien la 'khong gui duoc thu' nhung cach sua nguoc nhau hoan toan."""
    print(f"\n--- Buoc 1: mo cong TCP toi {host}:{port} ---")
    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=10):
            print(f"  OK ({(time.monotonic() - started) * 1000:.0f} ms)")
            return True
    except OSError as error:
        print(f"  THAT BAI sau {(time.monotonic() - started) * 1000:.0f} ms: {type(error).__name__}: {error}")
        print("  -> Rat co the nen tang chan outbound cong nay. Thu cong 465 (SMTP_PORT=465).")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--to", help="Gui THAT mot thu thu toi dia chi nay.")
    args = parser.parse_args()

    _report_config()
    settings = get_settings()
    if not settings.smtp_host:
        print("\nKET LUAN: SMTP_HOST trong. O production khong thu nao duoc gui, va moi tai khoan")
        print("dang ky moi se ket o buoc xac thuc email.")
        return 1

    if not _check_tcp(settings.smtp_host, settings.smtp_port):
        return 1

    print("\n--- Buoc 2: bat tay + dang nhap (khong gui thu) ---")
    result = account_mailer.probe()
    if result.delivered:
        print("  OK - may chu nhan dang nhap.")
    else:
        print(f"  THAT BAI: {result.reason}")
        if "Auth" in result.reason:
            print("  -> Sai username/password. Voi Gmail phai dung App Password 16 ky tu,")
            print("     khong phai mat khau tai khoan, va tai khoan phai bat 2FA.")
        return 1

    if args.to:
        print(f"\n--- Buoc 3: gui thu that toi {args.to} ---")
        sent = account_mailer.send_email(
            recipient=args.to,
            subject="VMedTriage - thu kiem tra SMTP",
            body="Neu ban doc duoc thu nay thi duong gui email dang hoat dong.",
            development_value="(kiem tra SMTP)",
        )
        print("  OK - da gui." if sent.delivered else f"  THAT BAI: {sent.reason}")
        if not sent.delivered:
            return 1

    print("\nKET LUAN: duong gui email hoat dong.")
    print("Neu van co nguoi dang ky khong dang nhap duoc thi ho ket vi ly do khac -")
    print("kiem cot users.email_verified va bang email_verification_codes.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except smtplib.SMTPException as error:
        print(f"Loi SMTP khong bat duoc: {type(error).__name__}: {error}")
        sys.exit(1)
