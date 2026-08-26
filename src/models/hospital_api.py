"""Request/response cho `/cases/{case_id}/hospital-suggestions` (patient-only, xem ADR-010)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class HospitalSuggestionRequest(BaseModel):
    """Body của POST. Cần ĐÚNG MỘT trong hai: toạ độ (ưu tiên, từ GPS trình duyệt) hoặc
    `address_text` (fallback khi bệnh nhân từ chối quyền vị trí/thiết bị không hỗ trợ) - thiếu cả
    hai thì Pydantic tự trả 422, router không cần tự kiểm lại."""

    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    address_text: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def _require_location_or_address(self) -> HospitalSuggestionRequest:
        has_coords = self.latitude is not None and self.longitude is not None
        if not has_coords and not (self.address_text or "").strip():
            raise ValueError("Cần gửi latitude+longitude hoặc address_text")
        return self


class HospitalCandidateResponse(BaseModel):
    place_id: str
    name: str
    address: str
    lat: float
    lng: float
    distance_km: float
    phone: str | None = None


class HospitalSuggestionResponse(BaseModel):
    case_id: str
    provider: str
    address_text: str
    patient_lat: float
    patient_lng: float
    """Toạ độ đã dùng để tra cứu (GPS thẳng hoặc kết quả geocode từ `address_text`) - frontend cần
    để vẽ marker vị trí bệnh nhân trên bản đồ, không chỉ hiển thị danh sách."""
    requested_at: datetime
    hospitals: list[HospitalCandidateResponse]
