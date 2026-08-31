"""`providers/openstreetmap.py` - mock `httpx` bằng `monkeypatch.setattr`.

Chú ý riêng cho provider này: KHÔNG được gọi mạng khi `osm_contact_email` rỗng (Nominatim Usage
Policy cấm request nặc danh) - test đó là bài quan trọng nhất trong file."""

from __future__ import annotations

import httpx
import pytest

from src.config import get_settings
from src.services.hospital_lookup.models import GeocodeResult, HospitalCandidate, LookupFailure
from src.services.hospital_lookup.providers import openstreetmap


class _Response:
    def __init__(self, payload, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _osm_contact(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "osm_contact_email", "dev@example.com")
    monkeypatch.setattr(settings, "hospital_lookup_max_results", 5)
    return settings


def test_geocode_sends_identifying_user_agent(monkeypatch):
    captured: dict = {}

    def fake_get(url, *, params, timeout, headers):
        captured.update(url=url, params=params, headers=headers)
        return _Response([{"lat": "21.01", "lon": "105.79", "display_name": "Hà Nội"}])

    monkeypatch.setattr(httpx, "get", fake_get)

    result = openstreetmap.geocode("Hà Nội")

    assert result == GeocodeResult(lat=21.01, lng=105.79, formatted_address="Hà Nội")
    assert "dev@example.com" in captured["headers"]["User-Agent"]


def test_geocode_missing_contact_email_returns_failure_without_network_call(monkeypatch):
    called = {"count": 0}

    def fake_get(*args, **kwargs):
        called["count"] += 1
        return _Response([])

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(get_settings(), "osm_contact_email", "")

    result = openstreetmap.geocode("bất kỳ")

    assert isinstance(result, LookupFailure)
    assert called["count"] == 0


def test_geocode_empty_results_is_not_found(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: _Response([]))

    result = openstreetmap.geocode("địa chỉ không tồn tại")

    assert isinstance(result, LookupFailure)
    assert result.not_found is True


def test_geocode_http_error_is_not_not_found(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: _Response([], status_code=500))

    result = openstreetmap.geocode("bất kỳ")

    assert isinstance(result, LookupFailure)
    assert result.not_found is False


def test_geocode_network_error_returns_failure(monkeypatch):
    def fake_get(*args, **kwargs):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(httpx, "get", fake_get)

    result = openstreetmap.geocode("bất kỳ")

    assert isinstance(result, LookupFailure)


def test_find_nearby_hospitals_missing_contact_email_returns_failure(monkeypatch):
    monkeypatch.setattr(get_settings(), "osm_contact_email", "")

    result = openstreetmap.find_nearby_hospitals(21.0, 105.8, 5)

    assert isinstance(result, LookupFailure)


def test_find_nearby_hospitals_uses_post_with_meters_radius(monkeypatch):
    captured: dict = {}

    def fake_post(url, *, data, timeout, headers):
        captured.update(url=url, data=data)
        return _Response({"elements": []})

    monkeypatch.setattr(httpx, "post", fake_post)

    openstreetmap.find_nearby_hospitals(21.0, 105.8, radius_km=5)

    assert "around:5000,21.0,105.8" in captured["data"]["data"]  # km -> mét
    assert '"amenity"="hospital"' in captured["data"]["data"]


def test_find_nearby_hospitals_reads_node_lat_lon_directly(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *args, **kwargs: _Response(
            {"elements": [{"id": 1, "lat": 21.001, "lon": 105.801, "tags": {"name": "Bệnh viện Node"}}]}
        ),
    )

    result = openstreetmap.find_nearby_hospitals(21.0, 105.8, 5)

    assert len(result) == 1
    assert result[0].name == "Bệnh viện Node"
    assert isinstance(result[0], HospitalCandidate)


def test_find_nearby_hospitals_reads_way_center_when_no_direct_latlon(monkeypatch):
    """`out center;` thêm `center.lat/center.lon` cho way/relation - không có lat/lon phẳng."""
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *args, **kwargs: _Response(
            {
                "elements": [
                    {"id": 2, "center": {"lat": 21.002, "lon": 105.802}, "tags": {"name": "Bệnh viện Way"}}
                ]
            }
        ),
    )

    result = openstreetmap.find_nearby_hospitals(21.0, 105.8, 5)

    assert len(result) == 1
    assert result[0].name == "Bệnh viện Way"


def test_find_nearby_hospitals_skips_elements_without_any_coordinates(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *args, **kwargs: _Response({"elements": [{"id": 3, "tags": {"name": "Không toạ độ"}}]}),
    )

    result = openstreetmap.find_nearby_hospitals(21.0, 105.8, 5)

    assert result == ()


def test_find_nearby_hospitals_composes_address_when_addr_full_missing(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *args, **kwargs: _Response(
            {
                "elements": [
                    {
                        "id": 4,
                        "lat": 21.001,
                        "lon": 105.801,
                        "tags": {"name": "X", "addr:housenumber": "91", "addr:street": "Trung Kính", "addr:city": "Hà Nội"},
                    }
                ]
            }
        ),
    )

    result = openstreetmap.find_nearby_hospitals(21.0, 105.8, 5)

    assert result[0].address == "91, Trung Kính, Hà Nội"


def test_find_nearby_hospitals_http_error_returns_failure(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: _Response({}, status_code=500))

    result = openstreetmap.find_nearby_hospitals(21.0, 105.8, 5)

    assert isinstance(result, LookupFailure)
