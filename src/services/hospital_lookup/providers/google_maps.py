"""GoogleMapsProvider - geocode + tìm bệnh viện qua Google Maps Platform.

Endpoint chuẩn (Google Maps Platform, ổn định lâu dài):
  - Geocoding:            GET https://maps.googleapis.com/maps/api/geocode/json?address=...&key=...
                           GET https://maps.googleapis.com/maps/api/geocode/json?latlng=lat,lng&key=...
  - Places Nearby Search:  GET https://maps.googleapis.com/maps/api/place/nearbysearch/json
                            ?location=lat,lng&radius=<mét>&type=hospital&key=...

Có filter category thật (`type=hospital`) nên CHỈ 1 request/lượt tìm - khác Goong phải tự ghép
AutoComplete + Detail (xem `providers/goong.py`). Đổi lại cần bật billing (thẻ tín dụng quốc tế) trên
Google Cloud Console; free tier ~5.000 call/SKU/tháng (so sánh chi tiết ở ADR-010).

Bán kính API này nhận theo MÉT - khác Goong (km) và phải nhân `radius_km * 1000` khi gọi."""

from __future__ import annotations

from src.config import get_settings
from src.services.hospital_lookup.distance import haversine_km
from src.services.hospital_lookup.models import GeocodeResult, HospitalCandidate, LookupFailure

_TIMEOUT_SECONDS = 15.0
_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
_NEARBY_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"


def _geocode_via(params: dict[str, str]) -> GeocodeResult | LookupFailure:
    import httpx

    settings = get_settings()
    api_key = settings.google_maps_api_key.strip()
    if not api_key:
        return LookupFailure("google_maps_api_key chưa cấu hình")

    try:
        response = httpx.get(_GEOCODE_URL, params={**params, "key": api_key}, timeout=_TIMEOUT_SECONDS)
    except Exception as error:
        return LookupFailure(f"Google Geocoding không gọi được ({type(error).__name__})")
    if response.status_code != 200:
        return LookupFailure(f"Google Geocoding HTTP {response.status_code}")

    results = response.json().get("results") or []
    if not results:
        return LookupFailure("Google Geocoding không tìm thấy địa chỉ này", not_found=True)
    location = results[0].get("geometry", {}).get("location", {})
    if "lat" not in location or "lng" not in location:
        return LookupFailure("Google Geocoding thiếu geometry.location trong response")
    return GeocodeResult(
        lat=location["lat"], lng=location["lng"], formatted_address=results[0].get("formatted_address", "")
    )


def geocode(address: str) -> GeocodeResult | LookupFailure:
    return _geocode_via({"address": address})


def reverse_geocode(lat: float, lng: float) -> GeocodeResult | LookupFailure:
    return _geocode_via({"latlng": f"{lat},{lng}"})


def _to_candidate(item: dict, *, origin_lat: float, origin_lng: float) -> HospitalCandidate | None:
    location = item.get("geometry", {}).get("location") or {}
    if "lat" not in location or "lng" not in location:
        return None
    return HospitalCandidate(
        place_id=item.get("place_id", ""),
        name=item.get("name", ""),
        address=item.get("vicinity", ""),
        lat=location["lat"],
        lng=location["lng"],
        distance_km=haversine_km(origin_lat, origin_lng, location["lat"], location["lng"]),
    )


def find_nearby_hospitals(lat: float, lng: float, radius_km: int) -> tuple[HospitalCandidate, ...] | LookupFailure:
    import httpx

    settings = get_settings()
    api_key = settings.google_maps_api_key.strip()
    if not api_key:
        return LookupFailure("google_maps_api_key chưa cấu hình")

    try:
        response = httpx.get(
            _NEARBY_URL,
            params={"location": f"{lat},{lng}", "radius": radius_km * 1000, "type": "hospital", "key": api_key},
            timeout=_TIMEOUT_SECONDS,
        )
    except Exception as error:
        return LookupFailure(f"Google Nearby Search không gọi được ({type(error).__name__})")
    if response.status_code != 200:
        return LookupFailure(f"Google Nearby Search HTTP {response.status_code}")

    results = response.json().get("results") or []
    candidates = [_to_candidate(item, origin_lat=lat, origin_lng=lng) for item in results]
    valid = sorted((c for c in candidates if c is not None), key=lambda item: item.distance_km)
    return tuple(valid[: settings.hospital_lookup_max_results])
