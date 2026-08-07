import re
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from src.models.user import Gender, UserRole

PASSWORD_REQUIREMENTS_MESSAGE = "Mật khẩu phải có chữ hoa, chữ thường, số và ký tự đặc biệt."


def validate_strong_password(value: str) -> str:
    if not all((re.search(r"[A-Z]", value), re.search(r"[a-z]", value), re.search(r"\d", value), re.search(r"[^A-Za-z0-9]", value))):
        raise ValueError(PASSWORD_REQUIREMENTS_MESSAGE)
    return value


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=50)
    phone_number: str = Field(min_length=9, max_length=32)
    full_name: str = Field(min_length=2, max_length=120)
    date_of_birth: date
    gender: Gender
    avatar_data_url: str = Field(min_length=30, max_length=2_000_000)
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)
    terms_accepted: bool
    role: UserRole = UserRole.PATIENT
    nurse_registration_code: str | None = Field(default=None, max_length=256)
    professional_license: str | None = Field(default=None, max_length=160)
    workplace: str | None = Field(default=None, max_length=160)
    department: str | None = Field(default=None, max_length=160)
    bio: str | None = Field(default=None, max_length=2000)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9_.-]{3,50}", normalized):
            raise ValueError("Tên đăng nhập chỉ gồm chữ, số, dấu chấm, gạch dưới hoặc gạch ngang.")
        return normalized

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, value: str) -> str:
        normalized = re.sub(r"[\s()-]", "", value)
        digits = normalized[1:] if normalized.startswith("+") else normalized
        if not digits.isdigit() or not 9 <= len(digits) <= 15:
            raise ValueError("Số điện thoại không hợp lệ.")
        return normalized

    @field_validator("avatar_data_url")
    @classmethod
    def validate_avatar(cls, value: str) -> str:
        if not re.match(r"^data:image/(png|jpeg|webp);base64,", value, flags=re.IGNORECASE):
            raise ValueError("Ảnh đại diện phải là PNG, JPEG hoặc WebP.")
        return value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return validate_strong_password(value)

    @model_validator(mode="after")
    def validate_registration(self):
        if self.password != self.confirm_password:
            raise ValueError("Xác nhận mật khẩu không khớp.")
        if not self.terms_accepted:
            raise ValueError("Bạn cần chấp nhận Điều khoản sử dụng và Chính sách quyền riêng tư.")
        if self.role == UserRole.NURSE:
            fields = {
                "giấy phép/chứng chỉ hành nghề": self.professional_license,
                "nơi công tác": self.workplace,
                "khoa/phòng ban": self.department,
                "tiểu sử": self.bio,
            }
            missing = [label for label, value in fields.items() if not value or not value.strip()]
            if missing:
                raise ValueError(f"Vui lòng nhập: {', '.join(missing)}.")
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    new_password: str = Field(min_length=8, max_length=128)
    confirm_new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return validate_strong_password(value)

    @model_validator(mode="after")
    def validate_confirmation(self):
        if self.new_password != self.confirm_new_password:
            raise ValueError("Xác nhận mật khẩu không khớp.")
        return self


class EmailVerificationConfirmRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("Mã xác thực gồm 6 chữ số.")
        return value


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
    confirm_new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return validate_strong_password(value)

    @model_validator(mode="after")
    def validate_confirmation(self):
        if self.current_password == self.new_password:
            raise ValueError("Mật khẩu mới phải khác mật khẩu hiện tại.")
        if self.new_password != self.confirm_new_password:
            raise ValueError("Xác nhận mật khẩu không khớp.")
        return self


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: EmailStr
    full_name: str
    role: UserRole
    email_verified: bool
    is_active: bool
    created_at: datetime


class MessageResponse(BaseModel):
    message: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class TokenClaims(BaseModel):
    sub: str
    role: UserRole
    email: EmailStr
    exp: int
    iat: int
    type: str
