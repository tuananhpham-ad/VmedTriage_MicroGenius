import secrets
from datetime import datetime, timedelta, timezone

import jwt
from jwt import InvalidTokenError as JWTInvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.config import get_settings
from src.models.auth import LoginRequest, RegisterRequest, TokenClaims
from src.models.user import UserRecord, UserRole


class UserAlreadyExistsError(ValueError):
    pass


class InvalidCredentialsError(ValueError):
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

    def register(self, db: Session, request: RegisterRequest) -> UserRecord:
        settings = get_settings()
        if request.role == UserRole.NURSE:
            supplied_code = request.nurse_registration_code or ""
            configured_code = settings.nurse_registration_code
            if not configured_code or not secrets.compare_digest(supplied_code, configured_code):
                raise NurseRegistrationDeniedError("Mã đăng ký điều dưỡng không hợp lệ")

        email = self._normalize_email(str(request.email))
        if db.scalar(select(UserRecord).where(UserRecord.email == email)) is not None:
            raise UserAlreadyExistsError("Email đã được đăng ký")

        user = UserRecord(
            email=email,
            full_name=request.full_name.strip(),
            role=request.role,
            password_hash=self.password_hash.hash(request.password),
        )
        db.add(user)
        try:
            db.commit()
        except IntegrityError as error:
            db.rollback()
            raise UserAlreadyExistsError("Email đã được đăng ký") from error
        db.refresh(user)
        return user

    def authenticate(self, db: Session, request: LoginRequest) -> UserRecord:
        email = self._normalize_email(str(request.email))
        user = db.scalar(select(UserRecord).where(UserRecord.email == email))
        if user is None:
            self.password_hash.verify(request.password, self.dummy_password_hash)
            raise InvalidCredentialsError("Email hoặc mật khẩu không đúng")
        if not self.password_hash.verify(request.password, user.password_hash):
            raise InvalidCredentialsError("Email hoặc mật khẩu không đúng")
        if not user.is_active:
            raise InvalidCredentialsError("Tài khoản đã bị vô hiệu hóa")
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
        token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
        return token, expires_in

    def decode_access_token(self, token: str) -> TokenClaims:
        settings = get_settings()
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
            )
            claims = TokenClaims.model_validate(payload)
        except (JWTInvalidTokenError, ValueError) as error:
            raise InvalidAccessTokenError("Token không hợp lệ hoặc đã hết hạn") from error
        if claims.type != "access" or not claims.sub.isdigit():
            raise InvalidAccessTokenError("Token không hợp lệ")
        return claims

    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> UserRecord | None:
        return db.get(UserRecord, user_id)


auth_service = AuthService()
