import re
import secrets
from datetime import datetime, timedelta, timezone
from hashlib import sha256

import jwt
from jwt import InvalidTokenError as JWTInvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.config import get_settings
from src.models.auth import LoginRequest, RegisterRequest, TokenClaims, UpdateProfileRequest
from src.models.password_reset import EmailVerificationCodeRecord, PasswordResetTokenRecord
from src.models.user import UserRecord, UserRole


class UserAlreadyExistsError(ValueError):
    pass


class InvalidCredentialsError(ValueError):
    pass


class EmailNotVerifiedError(ValueError):
    pass


class NurseRegistrationDeniedError(ValueError):
    pass


class InvalidAccessTokenError(ValueError):
    pass


class AuthService:
    def __init__(self) -> None:
        self.password_hash = PasswordHash.recommended()
        self.dummy_password_hash = self.password_hash.hash("not-a-real-user-password")

    @staticmethod
    def _normalize_email(email: str) -> str:
        return email.strip().lower()

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

    def register(self, db: Session, request: RegisterRequest) -> UserRecord:
        settings = get_settings()
        if request.role == UserRole.NURSE:
            supplied_code = request.nurse_registration_code or ""
            if not settings.nurse_registration_code or not secrets.compare_digest(
                supplied_code, settings.nurse_registration_code
            ):
                raise NurseRegistrationDeniedError("Mã đăng ký điều dưỡng không hợp lệ")

        email = self._normalize_email(str(request.email))
        username = request.username or self._username_from_email(db, email)
        if db.scalar(select(UserRecord).where(UserRecord.email == email)) is not None:
            raise UserAlreadyExistsError("Email đã được đăng ký")
        if db.scalar(select(UserRecord).where(UserRecord.username == username)) is not None:
            raise UserAlreadyExistsError("Tên đăng nhập đã được sử dụng")
        if db.scalar(select(UserRecord).where(UserRecord.phone_number == request.phone_number)) is not None:
            raise UserAlreadyExistsError("Số điện thoại đã được sử dụng")

        user = UserRecord(
            email=email,
            username=username,
            phone_number=request.phone_number,
            full_name=request.full_name.strip(),
            date_of_birth=request.date_of_birth,
            gender=request.gender,
            avatar_data_url=request.avatar_data_url,
            role=request.role,
            password_hash=self.password_hash.hash(request.password),
            terms_accepted_at=datetime.now(timezone.utc),
            professional_license=request.professional_license.strip() if request.professional_license else None,
            workplace=request.workplace.strip() if request.workplace else None,
            department=request.department.strip() if request.department else None,
            bio=request.bio.strip() if request.bio else None,
        )
        db.add(user)
        try:
            db.commit()
        except IntegrityError as error:
            db.rollback()
            raise UserAlreadyExistsError("Email, tên đăng nhập hoặc số điện thoại đã được sử dụng") from error
        db.refresh(user)
        return user

    @staticmethod
    def _username_from_email(db: Session, email: str) -> str:
        """Create an internal username when the streamlined registration form omits it."""
        local_part = email.partition("@")[0].lower()
        base = re.sub(r"[^a-z0-9_.-]+", "-", local_part).strip(".-_") or "user"
        base = f"user-{base}" if len(base) < 3 else base
        base = base[:50]
        candidate = base
        counter = 2
        while db.scalar(select(UserRecord.id).where(UserRecord.username == candidate)) is not None:
            suffix = f"-{counter}"
            candidate = f"{base[: 50 - len(suffix)]}{suffix}"
            counter += 1
        return candidate

    def create_email_verification_code(self, db: Session, user: UserRecord) -> str:
        now = datetime.now(timezone.utc)
        for existing in db.scalars(
            select(EmailVerificationCodeRecord).where(
                EmailVerificationCodeRecord.user_id == user.id,
                EmailVerificationCodeRecord.used_at.is_(None),
            )
        ):
            existing.used_at = now

        code = f"{secrets.randbelow(1_000_000):06d}"
        db.add(
            EmailVerificationCodeRecord(
                user_id=user.id,
                code_hash=sha256(code.encode("utf-8")).hexdigest(),
                expires_at=now + timedelta(minutes=get_settings().email_verification_code_expire_minutes),
            )
        )
        db.commit()
        return code

    def verify_email(self, db: Session, *, email: str, code: str) -> bool:
        user = db.scalar(select(UserRecord).where(UserRecord.email == self._normalize_email(email)))
        if user is None or user.email_verified:
            return False
        record = db.scalar(
            select(EmailVerificationCodeRecord)
            .where(
                EmailVerificationCodeRecord.user_id == user.id,
                EmailVerificationCodeRecord.code_hash == sha256(code.encode("utf-8")).hexdigest(),
                EmailVerificationCodeRecord.used_at.is_(None),
            )
            .order_by(EmailVerificationCodeRecord.created_at.desc())
        )
        if record is None or self._as_utc(record.expires_at) <= datetime.now(timezone.utc):
            return False
        user.email_verified = True
        record.used_at = datetime.now(timezone.utc)
        db.commit()
        return True

    def resend_email_verification_code(self, db: Session, email: str) -> tuple[UserRecord, str] | None:
        user = db.scalar(select(UserRecord).where(UserRecord.email == self._normalize_email(email)))
        if user is None or not user.is_active or user.email_verified:
            return None
        return user, self.create_email_verification_code(db, user)

    def authenticate(self, db: Session, request: LoginRequest) -> UserRecord:
        identifier = self._normalize_email(str(request.email))
        user = db.scalar(
            select(UserRecord).where(
                (UserRecord.email == identifier)
                | (UserRecord.username == identifier)
                | (UserRecord.phone_number == identifier)
            )
        )
        if user is None:
            # Vẫn verify với hash giả để thời gian phản hồi không tiết lộ tài khoản có tồn tại hay không.
            self.password_hash.verify(request.password, self.dummy_password_hash)
            raise InvalidCredentialsError("Tài khoản hoặc mật khẩu không đúng")
        if not self.password_hash.verify(request.password, user.password_hash):
            raise InvalidCredentialsError("Tài khoản hoặc mật khẩu không đúng")
        if not user.is_active:
            raise InvalidCredentialsError("Tài khoản đã bị vô hiệu hóa")
        if not user.email_verified:
            raise EmailNotVerifiedError("Email chưa được xác thực. Vui lòng nhập mã đã gửi tới email của bạn.")
        return user

    def create_password_reset_token(self, db: Session, email: str) -> tuple[UserRecord, str] | None:
        user = db.scalar(select(UserRecord).where(UserRecord.email == self._normalize_email(email)))
        if user is None or not user.is_active or not user.email_verified:
            return None

        now = datetime.now(timezone.utc)
        for existing in db.scalars(
            select(PasswordResetTokenRecord).where(
                PasswordResetTokenRecord.user_id == user.id,
                PasswordResetTokenRecord.used_at.is_(None),
            )
        ):
            existing.used_at = now
        token = secrets.token_urlsafe(32)
        db.add(
            PasswordResetTokenRecord(
                user_id=user.id,
                token_hash=sha256(token.encode("utf-8")).hexdigest(),
                expires_at=now + timedelta(minutes=get_settings().password_reset_token_expire_minutes),
            )
        )
        db.commit()
        return user, token

    def reset_password(self, db: Session, *, token: str, new_password: str) -> bool:
        record = db.scalar(
            select(PasswordResetTokenRecord).where(
                PasswordResetTokenRecord.token_hash == sha256(token.encode("utf-8")).hexdigest()
            )
        )
        if record is None or record.used_at is not None or self._as_utc(record.expires_at) <= datetime.now(timezone.utc):
            return False
        user = db.get(UserRecord, record.user_id)
        if user is None or not user.is_active:
            return False
        user.password_hash = self.password_hash.hash(new_password)
        record.used_at = datetime.now(timezone.utc)
        db.commit()
        return True

    def change_password(self, db: Session, *, user: UserRecord, current_password: str, new_password: str) -> bool:
        if not self.password_hash.verify(current_password, user.password_hash):
            return False
        user.password_hash = self.password_hash.hash(new_password)
        db.commit()
        return True

    def update_profile(self, db: Session, *, user: UserRecord, payload: UpdateProfileRequest) -> UserRecord:
        other_user = db.scalar(
            select(UserRecord).where(UserRecord.phone_number == payload.phone_number, UserRecord.id != user.id)
        )
        if other_user is not None:
            raise UserAlreadyExistsError("Số điện thoại đã được sử dụng")
        user.full_name = payload.full_name.strip()
        user.phone_number = payload.phone_number
        user.date_of_birth = payload.date_of_birth
        user.gender = payload.gender
        db.commit()
        db.refresh(user)
        return user

    def create_access_token(self, user: UserRecord) -> tuple[str, int]:
        settings = get_settings()
        now = datetime.now(timezone.utc)
        expires_in = settings.access_token_expire_minutes * 60
        payload = {
            "sub": str(user.id),
            "role": user.role.value,
            "email": user.email,
            "type": "access",
            "iat": now,
            "exp": now + timedelta(seconds=expires_in),
        }
        return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm), expires_in

    def decode_access_token(self, token: str) -> TokenClaims:
        settings = get_settings()
        try:
            claims = TokenClaims.model_validate(
                jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
            )
        except (JWTInvalidTokenError, ValueError) as error:
            raise InvalidAccessTokenError("Token không hợp lệ hoặc đã hết hạn") from error
        if claims.type != "access" or not claims.sub.isdigit():
            raise InvalidAccessTokenError("Token không hợp lệ")
        return claims

    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> UserRecord | None:
        return db.get(UserRecord, user_id)


auth_service = AuthService()
