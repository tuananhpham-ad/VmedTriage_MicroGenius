"""Chọn nhà cung cấp gợi ý bệnh viện gần nhất theo cấu hình, orchestrate geocode + tìm bệnh viện.

Tầng nghiệp vụ duy nhất mà router gọi tới - ranh giới duy nhất biết tới cả 3 module provider
(`providers/goong.py`, `providers/google_maps.py`, `providers/openstreetmap.py`). Ba module đó cùng
chữ ký hàm (`geocode`, `reverse_geocode`, `find_nearby_hospitals`), y hệt cách `source_support/
search.py` chọn backend tìm kiếm - đổi provider là đổi biến môi trường `HOSPITAL_LOOKUP_PROVIDER`,
không sửa gì ở đây hay ở router (`src/api/routers/hospital_suggestion.py`).

Provider module KHÔNG raise (trả `LookupFailure` khi lỗi) - lookup_service mới là nơi biến "chưa
cấu hình"/"geocode không ra kết quả"/"lỗi mạng" thành exception domain để router map sang đúng mã
HTTP (503 cho lỗi hệ thống, 422 cho lỗi có thể sửa được bằng cách nhập lại địa chỉ)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.config import get_settings
from src.services.hospital_lookup.models import GeocodeResult, HospitalCandidate, LookupFailure
from src.services.hospital_lookup.providers import google_maps, goong, openstreetmap


class _ProviderModule(Protocol):
    """Chữ ký hàm chung mà cả 3 module provider phải có - dùng để type hint tham số module, không
    phải để ép provider thành class (chúng vẫn là module với hàm top-level, xem `providers/__init__.py`)."""

    def geocode(self, address: str) -> GeocodeResult | LookupFailure: ...
    def find_nearby_hospitals(
        self, lat: float, lng: float, radius_km: int
    ) -> tuple[HospitalCandidate, ...] | LookupFailure: ...


_PROVIDER_MODULES: dict[str, _ProviderModule] = {"goong": goong, "google": google_maps, "osm": openstreetmap}

# Kiểm cấu hình bắt buộc TRƯỚC khi gọi provider, thay vì suy luận từ `LookupFailure.reason` (so
# chuỗi là giòn, dễ vỡ khi câu chữ đổi). Cũng tránh tốn một lượt gọi hàm vô ích khi rõ ràng sẽ hỏng.
_CONFIG_CHECKS = {
    "goong": lambda settings: bool(settings.goong_api_key.strip()),
    "google": lambda settings: bool(settings.google_maps_api_key.strip()),
    "osm": lambda settings: bool(settings.osm_contact_email.strip()),
}


class HospitalLookupError(Exception):
    """Gốc cho mọi lỗi domain của gói `hospital_lookup`."""


class ProviderNotConfiguredError(HospitalLookupError):
    """Provider đang chọn (`Settings.hospital_lookup_provider`) thiếu cấu hình bắt buộc."""


class ProviderRequestFailedError(HospitalLookupError):
    """Provider đã cấu hình nhưng lời gọi thất bại (mạng/HTTP/response bất thường) - lỗi hệ thống,
    không phải lỗi của địa chỉ người dùng nhập."""


class AddressGeocodeFailedError(HospitalLookupError):
    """Không quy đổi được địa chỉ text sang toạ độ (địa chỉ không tồn tại/gõ sai), hoặc bệnh nhân
    không gửi cả toạ độ lẫn địa chỉ - lỗi người dùng có thể tự sửa bằng cách nhập lại."""


@dataclass(frozen=True, slots=True)
class HospitalLookupQuery:
    latitude: float | None
    longitude: float | None
    address_text: str | None


@dataclass(frozen=True, slots=True)
class HospitalSuggestionResult:
    patient_lat: float
    patient_lng: float
    address_text: str
    provider: str
    hospitals: tuple[HospitalCandidate, ...]


def suggest_hospitals_for_case(query: HospitalLookupQuery) -> HospitalSuggestionResult:
    settings = get_settings()
    provider_name = settings.hospital_lookup_provider
    if not _CONFIG_CHECKS[provider_name](settings):
        raise ProviderNotConfiguredError(f"Nhà cung cấp '{provider_name}' chưa được cấu hình")
    provider = _PROVIDER_MODULES[provider_name]

    lat, lng = query.latitude, query.longitude
    address_text = (query.address_text or "").strip()
    if lat is None or lng is None:
        if not address_text:
            raise AddressGeocodeFailedError("Cần gửi toạ độ hoặc địa chỉ để tra cứu")
        lat, lng, address_text = _geocode_or_raise(provider, address_text)

    hospitals = provider.find_nearby_hospitals(lat, lng, settings.hospital_lookup_radius_km)
    if isinstance(hospitals, LookupFailure):
        raise ProviderRequestFailedError(hospitals.reason)

    return HospitalSuggestionResult(
        patient_lat=lat, patient_lng=lng, address_text=address_text, provider=provider_name, hospitals=hospitals
    )


def _geocode_or_raise(provider: _ProviderModule, address_text: str) -> tuple[float, float, str]:
    geocoded = provider.geocode(address_text)
    if isinstance(geocoded, LookupFailure):
        if geocoded.not_found:
            raise AddressGeocodeFailedError(geocoded.reason)
        raise ProviderRequestFailedError(geocoded.reason)
    return geocoded.lat, geocoded.lng, geocoded.formatted_address
