"""OpenStreetMapProvider - geocode qua Nominatim, tìm bệnh viện qua Overpass API.

Endpoint:
  - Nominatim search (forward):  GET {nominatim_base}/search?q=...&format=jsonv2&limit=1
  - Nominatim reverse:            GET {nominatim_base}/reverse?lat=...&lon=...&format=jsonv2
  - Overpass (nearby hospital):   POST {overpass_base}
                                   body: data=[out:json][timeout:25];
                                         nwr(around:<mét>,<lat>,<lng>)["amenity"="hospital"];out center;

NOMINATIM USAGE POLICY bắt buộc User-Agent định danh thật cho server công cộng
(nominatim.openstreetmap.org) - request nặc danh dễ bị chặn IP. `osm_contact_email` (config) dựng
User-Agent; rỗng thì provider tự tắt giống thiếu API key, tôn trọng ToS thay vì gửi request nặc danh
(xem `_user_agent`).

SERVER CÔNG CỘNG GIỚI HẠN CỨNG 1 REQUEST/GIÂY và ToS cấm dùng cho hệ thống/production quy mô lớn -
provider này là PHƯƠNG ÁN DỰ PHÒNG FREE cuối cùng (đổi qua bằng HOSPITAL_LOOKUP_PROVIDER=osm), không
phải lựa chọn cho traffic thật lâu dài trừ khi tự host Nominatim/Overpass riêng.

Way/relation trong Overpass không có `lat`/`lon` phẳng - `out center;` thêm sẵn `center.lat/center.lon`,
dùng trường đó khi node không có toạ độ trực tiếp."""

from __future__ import annotations

from src.config import get_settings
from src.services.hospital_lookup.distance import haversine_km
from src.services.hospital_lookup.models import GeocodeResult, HospitalCandidate, LookupFailure

_TIMEOUT_SECONDS = 20.0


def _user_agent() -> str | None:
    email = get_settings().osm_contact_email.strip()
    return f"VMedTriage/1.0 (contact: {email})" if email else None


def geocode(address: str) -> GeocodeResult | LookupFailure:
    import httpx

    user_agent = _user_agent()
    if not user_agent:
        return LookupFailure("osm_contact_email chưa cấu hình")

    settings = get_settings()
    try:
        response = httpx.get(
            f"{settings.osm_nominatim_base_url}/search",
            params={"q": address, "format": "jsonv2", "limit": 1},
            timeout=_TIMEOUT_SECONDS,
            headers={"User-Agent": user_agent},
        )
    except Exception as error:
        return LookupFailure(f"Nominatim search không gọi được ({type(error).__name__})")
    if response.status_code != 200:
        return LookupFailure(f"Nominatim search HTTP {response.status_code}")

    results = response.json() or []
    if not results:
        return LookupFailure("Nominatim không tìm thấy địa chỉ này", not_found=True)
    item = results[0]
    return GeocodeResult(lat=float(item["lat"]), lng=float(item["lon"]), formatted_address=item.get("display_name", ""))


def reverse_geocode(lat: float, lng: float) -> GeocodeResult | LookupFailure:
    import httpx

    user_agent = _user_agent()
    if not user_agent:
        return LookupFailure("osm_contact_email chưa cấu hình")

    settings = get_settings()
    try:
        response = httpx.get(
            f"{settings.osm_nominatim_base_url}/reverse",
            params={"lat": lat, "lon": lng, "format": "jsonv2"},
            timeout=_TIMEOUT_SECONDS,
            headers={"User-Agent": user_agent},
        )
    except Exception as error:
        return LookupFailure(f"Nominatim reverse không gọi được ({type(error).__name__})")
    if response.status_code != 200:
        return LookupFailure(f"Nominatim reverse HTTP {response.status_code}")

    body = response.json() or {}
    if "lat" not in body or "lon" not in body:
        return LookupFailure("Nominatim reverse không ra kết quả", not_found=True)
    return GeocodeResult(lat=float(body["lat"]), lng=float(body["lon"]), formatted_address=body.get("display_name", ""))


def _compose_address(tags: dict[str, str]) -> str:
    """OSM thường không có `addr:full` sẵn - tự ghép từ các field chuẩn nếu thiếu."""
    parts = [tags[key] for key in ("addr:housenumber", "addr:street", "addr:city") if tags.get(key)]
    return ", ".join(parts)


def _to_candidate(element: dict, *, origin_lat: float, origin_lng: float) -> HospitalCandidate | None:
    center = element.get("center") or {}
    node_lat = element.get("lat", center.get("lat"))
    node_lng = element.get("lon", center.get("lon"))
    if node_lat is None or node_lng is None:
        return None
    tags = element.get("tags") or {}
    return HospitalCandidate(
        place_id=str(element.get("id", "")),
        name=tags.get("name") or "(chưa có tên trên OpenStreetMap)",
        address=tags.get("addr:full") or _compose_address(tags),
        lat=node_lat,
        lng=node_lng,
        distance_km=haversine_km(origin_lat, origin_lng, node_lat, node_lng),
        phone=tags.get("phone"),
    )


def find_nearby_hospitals(lat: float, lng: float, radius_km: int) -> tuple[HospitalCandidate, ...] | LookupFailure:
    import httpx

    user_agent = _user_agent()
    if not user_agent:
        return LookupFailure("osm_contact_email chưa cấu hình")

    settings = get_settings()
    overpass_query = (
        f'[out:json][timeout:25];nwr(around:{radius_km * 1000},{lat},{lng})["amenity"="hospital"];out center;'
    )
    try:
        response = httpx.post(
            settings.osm_overpass_base_url,
            data={"data": overpass_query},
            timeout=_TIMEOUT_SECONDS,
            headers={"User-Agent": user_agent},
        )
    except Exception as error:
        return LookupFailure(f"Overpass không gọi được ({type(error).__name__})")
    if response.status_code != 200:
        return LookupFailure(f"Overpass HTTP {response.status_code}")

    elements = response.json().get("elements") or []
    candidates = [_to_candidate(element, origin_lat=lat, origin_lng=lng) for element in elements]
    valid = sorted((c for c in candidates if c is not None), key=lambda item: item.distance_km)
    return tuple(valid[: settings.hospital_lookup_max_results])
