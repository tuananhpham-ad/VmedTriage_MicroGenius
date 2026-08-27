from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class HealthProfileRecord(Base):
    """Bối cảnh sức khỏe do chính bệnh nhân tự khai.

    Hồ sơ này tách khỏi một ca sàng lọc: dữ liệu không được tự động đưa vào rule engine hoặc kết quả
    của ca. Một luồng chia sẻ có kiểm soát và xác nhận lại theo từng ca sẽ được xây riêng sau.
    """

    __tablename__ = "health_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True, nullable=False)
    allergy_status: Mapped[str] = mapped_column(String(24), nullable=False, default="unknown")
    allergies: Mapped[str | None] = mapped_column(Text, nullable=True)
    chronic_conditions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    conditions_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_medications: Mapped[str | None] = mapped_column(Text, nullable=True)
    recent_care_status: Mapped[str] = mapped_column(String(24), nullable=False, default="unknown")
    pregnancy_status: Mapped[str] = mapped_column(String(24), nullable=False, default="unknown")
    recent_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
