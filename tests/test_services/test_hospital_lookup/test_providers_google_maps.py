"""`providers/google_maps.py` - mock `httpx` bằng `monkeypatch.setattr`."""

from __future__ import annotations

import httpx
import pytest

from src.config import get_settings
from src.services.hospital_lookup.models import GeocodeResult, HospitalCandidate, LookupFailure
from src.services.hospital_lookup.providers import google_maps


class _Response:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict:
        return self._payload


@pytest.fixture(autouse=True)
def _google_key(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "google_maps_api_key", "test-google-key")
    monkeypatch.setattr(settings, "hospital_lookup_max_results", 5)
    return settings


def test_geocode_returns_result_on_200(monkeypatch):
    payload = {"results": [{"formatted_address": "1 Main St", "geometry": {"location": {"lat": 21.01, "lng": 105.79}}}]}
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: _Response(payload))

    result = google_maps.geocode("1 Main St")

    assert result == GeocodeResult(lat=21.01, lng=105.79, formatted_address="1 Main St")


def test_geocode_missing_key_returns_failure_without_network_call(monkeypatch):
    called = {"count": 0}

    def fake_get(*args, **kwargs):
        called["count"] += 1
        return _Response({})

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(get_settings(), "google_maps_api_key", "")

    result = google_maps.geocode("bất kỳ")

    assert isinstance(result, LookupFailure)
    assert called["count"] == 0


def test_geocode_empty_results_is_not_found(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: _Response({"results": []}))

    result = google_maps.geocode("địa chỉ không tồn tại")

    assert isinstance(result, LookupFailure)
    assert result.not_found is True


def test_geocode_http_error_is_not_not_found(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: _Response({}, status_code=500))

    result = google_maps.geocode("bất kỳ")

    assert isinstance(result, LookupFailure)
    assert result.not_found is False


def test_find_nearby_hospitals_sends_radius_in_meters_and_type_hospital(monkeypatch):
    captured: dict = {}

    def fake_get(url, *, params, timeout):
        captured.update(url=url, params=params)
        return _Response({"results": []})

    monkeypatch.setattr(httpx, "get", fake_get)

    google_maps.find_nearby_hospitals(21.0, 105.8, radius_km=5)

    assert captured["params"]["radius"] == 5000  # km -> mét
    assert captured["params"]["type"] == "hospital"
    assert captured["params"]["location"] == "21.0,105.8"


def test_find_nearby_hospitals_returns_one_request_worth_of_candidates(monkeypatch):
    """Khác Goong: Google có filter category thật nên KHÔNG cần gọi Detail riêng cho từng kết quả."""
    calls = {"count": 0}

    def fake_get(url, *, params, timeout):
        calls["count"] += 1
        return _Response(
            {
                "results": [
                    {
                        "place_id": "g1",
                        "name": "Bệnh viện Gần",
                        "vicinity": "Địa chỉ gần",
                        "geometry": {"location": {"lat": 21.001, "lng": 105.801}},
                    },
                    {
                        "place_id": "g2",
                        "name": "Bệnh viện Xa",
                        "vicinity": "Địa chỉ xa",
                        "geometry": {"location": {"lat": 21.5, "lng": 106.2}},
                    },
                ]
            }
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    result = google_maps.find_nearby_hospitals(21.0, 105.8, 5)

    assert calls["count"] == 1
    assert [item.name for item in result] == ["Bệnh viện Gần", "Bệnh viện Xa"]
    assert all(isinstance(item, HospitalCandidate) for item in result)


def test_find_nearby_hospitals_skips_results_without_geometry(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *args, **kwargs: _Response({"results": [{"place_id": "broken", "name": "Thiếu toạ độ"}]}),
    )

    result = google_maps.find_nearby_hospitals(21.0, 105.8, 5)

    assert result == ()


def test_find_nearby_hospitals_missing_key_returns_failure(monkeypatch):
    monkeypatch.setattr(get_settings(), "google_maps_api_key", "")

    result = google_maps.find_nearby_hospitals(21.0, 105.8, 5)

    assert isinstance(result, LookupFailure)


def test_find_nearby_hospitals_network_error_returns_failure(monkeypatch):
    def fake_get(*args, **kwargs):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(httpx, "get", fake_get)

    result = google_maps.find_nearby_hospitals(21.0, 105.8, 5)

    assert isinstance(result, LookupFailure)
