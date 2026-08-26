"""`providers/goong.py` - mock `httpx` bằng `monkeypatch.setattr`, không dùng respx (đúng pattern
`tests/test_source_support/test_search.py`)."""

from __future__ import annotations

import httpx
import pytest

from src.config import get_settings
from src.services.hospital_lookup.models import GeocodeResult, HospitalCandidate, LookupFailure
from src.services.hospital_lookup.providers import goong


class _Response:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict:
        return self._payload


@pytest.fixture(autouse=True)
def _goong_key(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "goong_api_key", "test-goong-key")
    monkeypatch.setattr(settings, "hospital_lookup_max_results", 5)
    return settings


# --- geocode -------------------------------------------------------------------------------------


def test_geocode_returns_result_on_200(monkeypatch):
    payload = {
        "results": [{"formatted_address": "91 Trung Kính, Cầu Giấy, Hà Nội", "geometry": {"location": {"lat": 21.01, "lng": 105.79}}}]
    }
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: _Response(payload))

    result = goong.geocode("91 Trung Kính, Cầu Giấy, Hà Nội")

    assert result == GeocodeResult(lat=21.01, lng=105.79, formatted_address="91 Trung Kính, Cầu Giấy, Hà Nội")


def test_geocode_missing_key_returns_failure_without_network_call(monkeypatch):
    called = {"count": 0}

    def fake_get(*args, **kwargs):
        called["count"] += 1
        return _Response({})

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(get_settings(), "goong_api_key", "")

    result = goong.geocode("địa chỉ bất kỳ")

    assert isinstance(result, LookupFailure)
    assert called["count"] == 0


def test_geocode_empty_results_is_not_found(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: _Response({"results": []}))

    result = goong.geocode("địa chỉ không tồn tại")

    assert isinstance(result, LookupFailure)
    assert result.not_found is True


def test_geocode_non_200_is_not_not_found(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: _Response({}, status_code=500))

    result = goong.geocode("bất kỳ")

    assert isinstance(result, LookupFailure)
    assert result.not_found is False


def test_geocode_network_error_returns_failure(monkeypatch):
    def fake_get(*args, **kwargs):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(httpx, "get", fake_get)

    result = goong.geocode("bất kỳ")

    assert isinstance(result, LookupFailure)
    assert result.not_found is False


def test_reverse_geocode_uses_latlng_param(monkeypatch):
    captured: dict = {}

    def fake_get(url, *, params, timeout, headers):
        captured.update(url=url, params=params)
        return _Response({"results": [{"formatted_address": "x", "geometry": {"location": {"lat": 1.0, "lng": 2.0}}}]})

    monkeypatch.setattr(httpx, "get", fake_get)

    goong.reverse_geocode(1.0, 2.0)

    assert captured["params"]["latlng"] == "1.0,2.0"


# --- find_nearby_hospitals (AutoComplete + Detail) ------------------------------------------------


def test_find_nearby_hospitals_missing_key_returns_failure(monkeypatch):
    monkeypatch.setattr(get_settings(), "goong_api_key", "")

    result = goong.find_nearby_hospitals(21.0, 105.8, 5)

    assert isinstance(result, LookupFailure)


def test_find_nearby_hospitals_empty_predictions_returns_empty_tuple(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: _Response({"predictions": []}))

    result = goong.find_nearby_hospitals(21.0, 105.8, 5)

    assert result == ()


def test_find_nearby_hospitals_autocomplete_http_error_returns_failure(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: _Response({}, status_code=503))

    result = goong.find_nearby_hospitals(21.0, 105.8, 5)

    assert isinstance(result, LookupFailure)


def test_find_nearby_hospitals_composes_autocomplete_and_detail(monkeypatch):
    """1 lượt = 1 AutoComplete + N Detail - đây là điểm khác biệt lớn nhất so với Google/OSM."""
    calls: list[str] = []

    def fake_get(url, *, params, timeout, headers):
        calls.append(url)
        if url.endswith("/Place/AutoComplete"):
            return _Response({"predictions": [{"place_id": "p1"}, {"place_id": "p2"}]})
        assert url.endswith("/Place/Detail")
        detail_by_id = {
            "p1": {"name": "Bệnh viện A", "formatted_address": "Địa chỉ A", "geometry": {"location": {"lat": 21.001, "lng": 105.801}}},
            "p2": {"name": "Bệnh viện B", "formatted_address": "Địa chỉ B", "geometry": {"location": {"lat": 21.10, "lng": 105.90}}},
        }
        return _Response({"result": detail_by_id[params["place_id"]]})

    monkeypatch.setattr(httpx, "get", fake_get)

    result = goong.find_nearby_hospitals(21.0, 105.8, 5)

    autocomplete_calls = [url for url in calls if url.endswith("/Place/AutoComplete")]
    detail_calls = [url for url in calls if url.endswith("/Place/Detail")]
    assert len(autocomplete_calls) == 1
    assert len(detail_calls) == 2
    assert isinstance(result, tuple)
    assert [item.name for item in result] == ["Bệnh viện A", "Bệnh viện B"]  # sort theo khoảng cách tăng dần
    assert all(isinstance(item, HospitalCandidate) for item in result)


def test_find_nearby_hospitals_skips_place_ids_whose_detail_call_fails(monkeypatch):
    def fake_get(url, *, params, timeout, headers):
        if url.endswith("/Place/AutoComplete"):
            return _Response({"predictions": [{"place_id": "broken"}, {"place_id": "ok"}]})
        if params["place_id"] == "broken":
            return _Response({}, status_code=500)
        return _Response(
            {"result": {"name": "Bệnh viện C", "formatted_address": "Địa chỉ C", "geometry": {"location": {"lat": 21.02, "lng": 105.82}}}}
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    result = goong.find_nearby_hospitals(21.0, 105.8, 5)

    assert len(result) == 1
    assert result[0].name == "Bệnh viện C"
