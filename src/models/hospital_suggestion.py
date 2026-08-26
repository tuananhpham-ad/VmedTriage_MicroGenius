"""Bảng cache kết quả gợi ý bệnh viện gần nhất (patient-only, xem ADR-010 trong
`docs/context/decisions.md`).

Không có trạng thái duyệt: tính năng này được chốt là NGOẠI LỆ có phạm vi hẹp với ADR-002 (HITL bắt
buộc 100%) - bệnh nhân thấy danh sách trực tiếp, không có bước duyệt của điều dưỡng. Bảng chỉ đóng
vai trò CACHE (đỡ gọi lại provider mỗi lần bệnh nhân xem lại màn hình - quan trọng vì quota free của
Goong chỉ 1.000 request/ngày, xem `src/config.py`) và AUDIT TRAIL (nguyên tắc bảo vệ PII/PHI #5 của
CLAUDE.md - vẫn cần biết "bệnh nhân đã xem gợi ý gì, lúc nào" dù không có ai duyệt).

Một hàng MỚI NHẤT cho mỗi case, ghi đè khi bệnh nhân tra cứu lại (đổi vị trí, thử lại) - không tích
luỹ lịch sử nhiều lần tra cứu, đúng tinh thần `ApprovalRecordRow` (một quyết định cuối cùng, không
phải một nhật ký)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class HospitalSuggestionRow(Base):
    """`suggestions_json` giữ nguyên danh sách `HospitalCandidate` đã serialize (xem
    `src/services/hospital_lookup/models.py`) - cột JSON vì hình dạng response của 3 provider vẫn có
    thể đổi, cùng lý do với `TriageCaseRow.payload` (xem `case_record.py`)."""

    __tablename__ = "hospital_suggestions"

    case_id: Mapped[str] = mapped_column(String(64), ForeignKey("triage_cases.case_id"), primary_key=True)
    requested_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    location_source: Mapped[str] = mapped_column(String(16))
    """`"gps"` (HTML5 Geolocation) hoặc `"manual_address"` (bệnh nhân từ chối quyền/không hỗ trợ)."""
    patient_lat: Mapped[float] = mapped_column(Float)
    patient_lng: Mapped[float] = mapped_column(Float)
    address_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    """Địa chỉ hiển thị được - do bệnh nhân nhập (fallback) hoặc `formatted_address` provider trả về
    khi tra cứu bằng GPS (reverse/forward geocode), tuỳ nhánh nào chạy."""
    provider: Mapped[str] = mapped_column(String(20))
    """Nhà cung cấp đã tạo ra kết quả này (`"goong"`/`"google"`/`"osm"`) - giữ lại dù `Settings.
    hospital_lookup_provider` có đổi sau đó, để biết dữ liệu cache này đến từ đâu."""
    suggestions_json: Mapped[list] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
