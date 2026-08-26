"""`lookup_service.py` - orchestration + exception domain. Mock ở tầng module provider
(`goong.geocode`/`goong.find_nearby_hospitals`...), không chạm `httpx` - đó là việc của
`test_providers_*.py`."""

from __future__ import annotations

import pytest

from src.config import get_settings
from src.services.hospital_lookup import lookup_service
from src.services.hospital_lookup.models import GeocodeResult, HospitalCandidate, LookupFailure
from src.services.hospital_lookup.providers import google_maps, goong, openstreetmap


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    """Cấu hình đủ cả 3 provider - test tự chọn provider nào đang hoạt động qua
    `hospital_lookup_provider`, không phụ thuộc .env của máy chạy test."""
    settings = get_settings()
    monkeypatch.setattr(settings, "goong_api_key", "k")
    monkeypatch.setattr(settings, "google_maps_api_key", "k")
    monkeypatch.setattr(settings, "osm_contact_email", "dev@example.com")
    monkeypatch.setattr(settings, "hospital_lookup_provider", "goong")
    monkeypatch.setattr(settings, "hospital_lookup_radius_km", 5)
    return settings


_HOSPITAL = HospitalCandidate(place_id="p1", name="Bệnh viện A", address="Địa chỉ A", lat=21.0, lng=105.8, distance_km=0.5)


def test_uses_coordinates_directly_without_geocoding(monkeypatch):
    geocode_called = {"count": 0}
    monkeypatch.setattr(goong, "geocode", lambda address: geocode_called.__setitem__("count", geocode_called["count"] + 1))
    monkeypatch.setattr(goong, "find_nearby_hospitals", lambda lat, lng, radius_km: (_HOSPITAL,))

    result = lookup_service.suggest_hospitals_for_case(
        lookup_service.HospitalLookupQuery(latitude=21.0, longitude=105.8, address_text=None)
    )

    assert geocode_called["count"] == 0
    assert result.patient_lat == 21.0
    assert result.patient_lng == 105.8
    assert result.hospitals == (_HOSPITAL,)
    assert result.provider == "goong"


def test_geocodes_when_only_address_given(monkeypatch):
    monkeypatch.setattr(goong, "geocode", lambda address: GeocodeResult(lat=21.5, lng=106.0, formatted_address="Địa chỉ chuẩn hoá"))
    monkeypatch.setattr(goong, "find_nearby_hospitals", lambda lat, lng, radius_km: (_HOSPITAL,))

    result = lookup_service.suggest_hospitals_for_case(
        lookup_service.HospitalLookupQuery(latitude=None, longitude=None, address_text="91 Trung Kính")
    )

    assert result.patient_lat == 21.5
    assert result.patient_lng == 106.0
    assert result.address_text == "Địa chỉ chuẩn hoá"


def test_raises_address_geocode_failed_when_nothing_given():
    with pytest.raises(lookup_service.AddressGeocodeFailedError):
        lookup_service.suggest_hospitals_for_case(
            lookup_service.HospitalLookupQuery(latitude=None, longitude=None, address_text=None)
        )


def test_raises_address_geocode_failed_when_geocode_not_found(monkeypatch):
    monkeypatch.setattr(goong, "geocode", lambda address: LookupFailure("không tìm thấy", not_found=True))

    with pytest.raises(lookup_service.AddressGeocodeFailedError):
        lookup_service.suggest_hospitals_for_case(
            lookup_service.HospitalLookupQuery(latitude=None, longitude=None, address_text="địa chỉ rác")
        )


def test_raises_provider_request_failed_when_geocode_network_error(monkeypatch):
    monkeypatch.setattr(goong, "geocode", lambda address: LookupFailure("lỗi mạng", not_found=False))

    with pytest.raises(lookup_service.ProviderRequestFailedError):
        lookup_service.suggest_hospitals_for_case(
            lookup_service.HospitalLookupQuery(latitude=None, longitude=None, address_text="địa chỉ bất kỳ")
        )


def test_raises_provider_request_failed_when_nearby_search_fails(monkeypatch):
    monkeypatch.setattr(goong, "find_nearby_hospitals", lambda lat, lng, radius_km: LookupFailure("Goong sập"))

    with pytest.raises(lookup_service.ProviderRequestFailedError):
        lookup_service.suggest_hospitals_for_case(
            lookup_service.HospitalLookupQuery(latitude=21.0, longitude=105.8, address_text=None)
        )


def test_raises_not_configured_before_calling_provider(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "goong_api_key", "")
    called = {"count": 0}
    monkeypatch.setattr(goong, "find_nearby_hospitals", lambda *a, **k: called.__setitem__("count", called["count"] + 1))

    with pytest.raises(lookup_service.ProviderNotConfiguredError):
        lookup_service.suggest_hospitals_for_case(
            lookup_service.HospitalLookupQuery(latitude=21.0, longitude=105.8, address_text=None)
        )
    assert called["count"] == 0


@pytest.mark.parametrize(
    ("provider_name", "module"),
    [("goong", goong), ("google", google_maps), ("osm", openstreetmap)],
)
def test_dispatches_to_configured_provider_module(monkeypatch, provider_name, module):
    settings = get_settings()
    monkeypatch.setattr(settings, "hospital_lookup_provider", provider_name)
    monkeypatch.setattr(module, "find_nearby_hospitals", lambda lat, lng, radius_km: (_HOSPITAL,))

    result = lookup_service.suggest_hospitals_for_case(
        lookup_service.HospitalLookupQuery(latitude=21.0, longitude=105.8, address_text=None)
    )

    assert result.provider == provider_name
    assert result.hospitals == (_HOSPITAL,)
