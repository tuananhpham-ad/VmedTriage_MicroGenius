"""Tạo 2 tài khoản demo để khỏi phải đăng ký + xác thực email mỗi lần thử.

    python -m scripts.seed_demo_users

| Vai trò    | Tài khoản | Mật khẩu |
|------------|-----------|----------|
| Bệnh nhân  | `user0`   | `user0`  |
| Điều dưỡng | `nurse0`  | `nurse0` |

Đăng nhập được bằng tên đăng nhập hoặc email (`user0@example.com` / `nurse0@example.com`).

⚠️ Mật khẩu ở đây CỐ TÌNH yếu và KHÔNG qua `validate_strong_password` - script ghi thẳng hash vào DB,
bỏ qua tầng validate của `RegisterRequest`. Chỉ dùng cho demo local. Script tự từ chối chạy khi
`APP_ENV=production`. Tài khoản cũng được đánh dấu `email_verified=True` để bỏ qua bước nhập mã.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone

from sqlalchemy import select

from src.config import get_settings
from src.database import configure_database, create_tables, get_db_session
from src.models.user import Gender, UserRecord, UserRole
from src.services.infra.auth import auth_service

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Ảnh đại diện 1x1 px - `avatar_data_url` là NOT NULL nên phải có giá trị hợp lệ.
PLACEHOLDER_AVATAR = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNk"
    "YAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)

DEMO_USERS = (
    {
        "username": "user0",
        "password": "user0",
        "email": "user0@example.com",
        "full_name": "Bệnh nhân Demo",
        "phone_number": "+84900000001",
        "role": UserRole.PATIENT,
    },
    {
        "username": "nurse0",
        "password": "nurse0",
        "email": "nurse0@example.com",
        "full_name": "Điều dưỡng Demo",
        "phone_number": "+84900000002",
        "role": UserRole.NURSE,
        "professional_license": "DEMO-LICENSE-0001",
        "workplace": "Bệnh viện Demo",
        "department": "Khoa Khám bệnh",
        "bio": "Tài khoản điều dưỡng dùng cho bản demo.",
    },
)


def seed() -> int:
    settings = get_settings()
    if settings.app_env == "production":
        print("Từ chối chạy: seed tài khoản demo với mật khẩu yếu không được phép ở production.")
        return 1

    configure_database()
    create_tables()

    session = next(get_db_session())
    try:
        for spec in DEMO_USERS:
            existing = session.scalar(select(UserRecord).where(UserRecord.username == spec["username"]))
            if existing is not None:
                # Đặt lại mật khẩu + mở khoá, để tài khoản demo luôn dùng được dù trước đó bị đổi.
                existing.email = spec["email"]
                existing.password_hash = auth_service.password_hash.hash(spec["password"])
                existing.email_verified = True
                existing.is_active = True
                print(f"  cập nhật lại: {spec['username']} / {spec['password']}  ({existing.role.value})")
                continue

            session.add(
                UserRecord(
                    username=spec["username"],
                    email=spec["email"],
                    phone_number=spec["phone_number"],
                    full_name=spec["full_name"],
                    date_of_birth=date(1990, 1, 1),
                    gender=Gender.PREFER_NOT_TO_SAY,
                    avatar_data_url=PLACEHOLDER_AVATAR,
                    role=spec["role"],
                    password_hash=auth_service.password_hash.hash(spec["password"]),
                    email_verified=True,  # bỏ qua bước nhập mã xác thực email
                    terms_accepted_at=datetime.now(timezone.utc),
                    professional_license=spec.get("professional_license"),
                    workplace=spec.get("workplace"),
                    department=spec.get("department"),
                    bio=spec.get("bio"),
                    is_active=True,
                )
            )
            print(f"  đã tạo: {spec['username']} / {spec['password']}  ({spec['role'].value})")
        session.commit()
    finally:
        session.close()

    print("\nĐăng nhập bằng tên đăng nhập hoặc email, mật khẩu như trên.")
    return 0


if __name__ == "__main__":
    raise SystemExit(seed())
