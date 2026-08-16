"""Bảng SQLite cho dữ liệu lâm sàng: case, quyết định duyệt và audit log.

Trước đây cả ba nằm in-memory và mất sạch sau mỗi lần restart hoặc redeploy. Với case và audit thì
đó không phải bất tiện mà là hỏng: một ca cấp cứu đang chờ điều dưỡng duyệt biến mất khi tiến trình
khởi động lại, và audit log - thứ tồn tại để truy được ai đã quyết định gì - không sống nổi qua một
lần deploy.

**Vì sao cột JSON thay vì bảng chuẩn hoá.** `TriageCase` là model Pydantic lồng nhiều tầng
(`structured_data`, `red_flags`, `triage_proposal`, `summary`, `queue_item`, `pipeline_trace`), và
hình dạng của nó vẫn đang đổi theo từng sprint. Chuẩn hoá bây giờ nghĩa là viết mapper hai chiều cho
mọi model con và một migration cho mỗi lần đổi schema Pydantic. Cách ở đây: cột PHẲNG cho đúng những
gì cần TRUY VẤN (lọc theo bệnh nhân, sắp theo mức ưu tiên, đếm theo trạng thái), còn toàn bộ bản ghi
giữ nguyên trong một cột JSON. Pydantic vẫn là nguồn sự thật về hình dạng dữ liệu; SQLite lo phần
sống sót qua restart.

Đánh đổi phải biết: không JOIN được vào phần lồng, và không có ràng buộc toàn vẹn ở tầng DB cho
chúng. Khi nào cần thống kê sâu theo `red_flags`/`reason_codes` thì đó là lúc chuẩn hoá - không phải
bây giờ.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TriageCaseRow(Base):
    """Một ca triage. `payload` giữ nguyên `TriageCase.model_dump(mode="json")`."""

    __tablename__ = "triage_cases"

    case_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # Nullable vì phiên demo (`/fever/*`) không có tài khoản; case vẫn được lưu để không mất dữ liệu.
    patient_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    priority: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    """Mức AI đề xuất, tách phẳng ra để sắp hàng đợi mà không phải nạp và parse cả payload."""
    has_red_flag: Mapped[bool] = mapped_column(default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    payload: Mapped[dict] = mapped_column(JSON)


class ApprovalRecordRow(Base):
    """Quyết định duyệt cuối cùng. Sự tồn tại của dòng này là CỔNG CHẶN của
    `GET /cases/{id}/result` - chưa có dòng thì bệnh nhân không thấy nội dung xử trí."""

    __tablename__ = "approval_records"

    case_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("triage_cases.case_id"), primary_key=True
    )
    approved_by: Mapped[int] = mapped_column(Integer)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    final_priority: Mapped[str] = mapped_column(String(32), index=True)


class AuditLogRow(Base):
    """Nhật ký hành động của điều dưỡng. CHỈ THÊM, không sửa không xoá - đó là điều làm nó có giá trị.

    KHÔNG khai `ForeignKey` sang `triage_cases`: audit phải sống lâu hơn case. Nếu sau này có chính
    sách xoá dữ liệu lâm sàng theo thời hạn, dấu vết "ai đã quyết định gì" vẫn phải ở lại."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String(64), index=True)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(32), index=True)
    old_value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    new_value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
