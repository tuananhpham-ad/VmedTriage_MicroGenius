"""Kho cache gợi ý bệnh viện gần nhất, lưu bằng SQLite (`hospital_suggestions`).

API công khai (`get`/`upsert`) theo đúng khuôn `case_store.py`/`approval_store.py`: một record Pydantic
là hình dạng dữ liệu mà phần còn lại của hệ thống thấy, ORM row chỉ là cách lưu qua restart. Không có
lớp duyệt nào ở đây (xem ADR-010) - `upsert` ghi đè trực tiếp, không có trạng thái pending/approved."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from src.database import session_scope
from src.models.hospital_suggestion import HospitalSuggestionRow


class HospitalCandidateView(BaseModel):
    """Bản Pydantic của `src.services.hospital_lookup.models.HospitalCandidate` - tách riêng vì store
    không nên phụ thuộc ngược vào gói `hospital_lookup` (dataclass đó là kiểu nội bộ của việc GỌI
    provider, không phải kiểu để LƯU/serialize)."""

    place_id: str
    name: str
    address: str
    lat: float
    lng: float
    distance_km: float
    phone: str | None = None


class HospitalSuggestionRecord(BaseModel):
    case_id: str
    requested_by: int | None
    requested_at: datetime
    location_source: str
    patient_lat: float
    patient_lng: float
    address_text: str | None
    provider: str
    hospitals: list[HospitalCandidateView]
    updated_at: datetime


class SqliteHospitalSuggestionStore:
    def get(self, case_id: str) -> HospitalSuggestionRecord | None:
        with session_scope() as session:
            row = session.get(HospitalSuggestionRow, case_id)
            return self._to_record(row) if row else None

    def upsert(self, record: HospitalSuggestionRecord) -> HospitalSuggestionRecord:
        with session_scope() as session:
            row = session.get(HospitalSuggestionRow, record.case_id)
            if row is None:
                row = HospitalSuggestionRow(case_id=record.case_id)
                session.add(row)
            row.requested_by = record.requested_by
            row.requested_at = record.requested_at
            row.location_source = record.location_source
            row.patient_lat = record.patient_lat
            row.patient_lng = record.patient_lng
            row.address_text = record.address_text
            row.provider = record.provider
            row.suggestions_json = [item.model_dump(mode="json") for item in record.hospitals]
            row.updated_at = record.updated_at
        return record

    def _to_record(self, row: HospitalSuggestionRow) -> HospitalSuggestionRecord:
        return HospitalSuggestionRecord(
            case_id=row.case_id,
            requested_by=row.requested_by,
            requested_at=row.requested_at,
            location_source=row.location_source,
            patient_lat=row.patient_lat,
            patient_lng=row.patient_lng,
            address_text=row.address_text,
            provider=row.provider,
            hospitals=[HospitalCandidateView.model_validate(item) for item in row.suggestions_json],
            updated_at=row.updated_at,
        )


hospital_suggestion_store = SqliteHospitalSuggestionStore()
