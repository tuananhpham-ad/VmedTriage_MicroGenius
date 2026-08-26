"""GoongProvider - geocode + tìm bệnh viện qua Goong Maps (goong.io).

Endpoint đã xác nhận qua docs.goong.io (2026-08-25), KHÔNG phải đoán:
  - Geocode:            GET {base}/Geocode?api_key=...&address=...        (forward)
                         GET {base}/Geocode?api_key=...&latlng=lat,lng     (reverse)
  - Place/AutoComplete:  GET {base}/Place/AutoComplete?api_key=...&input=...&location=lat,lng
                          &radius=<km>&limit=...
  - Place/Detail:        GET {base}/Place/Detail?api_key=...&place_id=...

GOONG KHÔNG CÓ NEARBY-SEARCH THEO CATEGORY (không có tham số kiểu `type=hospital` như Google Places).
`find_nearby_hospitals` vì vậy phải tự ghép: AutoComplete tìm theo từ khoá y tế + location bias, rồi
gọi Detail cho TỪNG kết quả để lấy toạ độ (AutoComplete không trả lat/lng trực tiếp, chỉ có
`description`/`place_id`) - tức 1 lượt tốn 1 + N request. Quan trọng cho quota free 1.000/ngày
(`Settings.goong_base_url`) - `hospital_lookup_max_results` mặc định thấp (5) chính vì lý do này.

Chưa kiểm chứng chất lượng kết quả AutoComplete với từ khoá tiếng Việt ở toạ độ thật quy mô lớn - test
tay với vài toạ độ HN/TP.HCM trước khi coi provider này "xong" (xem plan/ADR-010)."""

from __future__ import annotations

import logging

from src.config import get_settings
from src.services.hospital_lookup.distance import haversine_km
from src.services.hospital_lookup.models import GeocodeResult, HospitalCandidate, LookupFailure

logger = logging.getLogger("vmedtriage.hospital_lookup")

_TIMEOUT_SECONDS = 15.0
_USER_AGENT = "VMedTriage-HospitalLookup/1.0"
_SEARCH_KEYWORD = "bệnh viện"


def _geocode_via(param_name: str, param_value: str) -> GeocodeResult | LookupFailure:
    import httpx

    settings = get_settings()
    api_key = settings.goong_api_key.strip()
    if not api_key:
        return LookupFailure("goong_api_key chưa cấu hình")

    try:
        response = httpx.get(
            f"{settings.goong_base_url}/Geocode",
            params={"api_key": api_key, param_name: param_value},
            timeout=_TIMEOUT_SECONDS,
            headers={"User-Agent": _USER_AGENT},
        )
    except Exception as error:
        return LookupFailure(f"Goong Geocode không gọi được ({type(error).__name__})")
    if response.status_code != 200:
        return LookupFailure(f"Goong Geocode HTTP {response.status_code}")

    results = response.json().get("results") or []
    if not results:
        return LookupFailure("Goong Geocode không tìm thấy địa chỉ này", not_found=True)
    location = results[0].get("geometry", {}).get("location", {})
    if "lat" not in location or "lng" not in location:
        return LookupFailure("Goong Geocode thiếu geometry.location trong response")
    return GeocodeResult(
        lat=location["lat"],
        lng=location["lng"],
        formatted_address=results[0].get("formatted_address", ""),
    )


def geocode(address: str) -> GeocodeResult | LookupFailure:
    return _geocode_via("address", address)


def reverse_geocode(lat: float, lng: float) -> GeocodeResult | LookupFailure:
    return _geocode_via("latlng", f"{lat},{lng}")


def _search_place_ids(lat: float, lng: float, radius_km: int, limit: int) -> list[str] | LookupFailure:
    """AutoComplete theo từ khoá y tế + location bias -> danh sách `place_id` ứng viên."""
    import httpx

    settings = get_settings()
    try:
        response = httpx.get(
            f"{settings.goong_base_url}/Place/AutoComplete",
            params={
                "api_key": settings.goong_api_key.strip(),
                "input": _SEARCH_KEYWORD,
                "location": f"{lat},{lng}",
                "radius": radius_km,
                "limit": limit,
            },
            timeout=_TIMEOUT_SECONDS,
            headers={"User-Agent": _USER_AGENT},
        )
    except Exception as error:
        return LookupFailure(f"Goong AutoComplete không gọi được ({type(error).__name__})")
    if response.status_code != 200:
        return LookupFailure(f"Goong AutoComplete HTTP {response.status_code}")

    predictions = response.json().get("predictions") or []
    return [item["place_id"] for item in predictions if item.get("place_id")]


def _place_detail(place_id: str) -> tuple[str, str, float, float] | None:
    """`(name, formatted_address, lat, lng)` hoặc `None` nếu lấy chi tiết thất bại - một `place_id`
    lỗi không được làm hỏng cả danh sách, chỉ bị bỏ qua (log cảnh báo)."""
    import httpx

    settings = get_settings()
    try:
        response = httpx.get(
            f"{settings.goong_base_url}/Place/Detail",
            params={"api_key": settings.goong_api_key.strip(), "place_id": place_id},
            timeout=_TIMEOUT_SECONDS,
            headers={"User-Agent": _USER_AGENT},
        )
    except Exception as error:
        logger.warning("hospital_lookup.goong_detail_failed place_id=%s reason=%s", place_id, type(error).__name__)
        return None
    if response.status_code != 200:
        logger.warning("hospital_lookup.goong_detail_http_error place_id=%s status=%s", place_id, response.status_code)
        return None

    result = response.json().get("result") or {}
    location = result.get("geometry", {}).get("location", {})
    if "lat" not in location or "lng" not in location:
        return None
    return result.get("name", ""), result.get("formatted_address", ""), location["lat"], location["lng"]


def find_nearby_hospitals(lat: float, lng: float, radius_km: int) -> tuple[HospitalCandidate, ...] | LookupFailure:
    settings = get_settings()
    if not settings.goong_api_key.strip():
        return LookupFailure("goong_api_key chưa cấu hình")

    place_ids = _search_place_ids(lat, lng, radius_km, settings.hospital_lookup_max_results)
    if isinstance(place_ids, LookupFailure):
        return place_ids
    if not place_ids:
        return ()  # bán kính này không có kết quả - KHÔNG phải lỗi, để tầng UI báo "thử địa chỉ khác"

    candidates: list[HospitalCandidate] = []
    for place_id in place_ids:
        detail = _place_detail(place_id)
        if detail is None:
            continue
        name, address, hosp_lat, hosp_lng = detail
        candidates.append(
            HospitalCandidate(
                place_id=place_id,
                name=name,
                address=address,
                lat=hosp_lat,
                lng=hosp_lng,
                distance_km=haversine_km(lat, lng, hosp_lat, hosp_lng),
            )
        )

    candidates.sort(key=lambda item: item.distance_km)
    return tuple(candidates)
