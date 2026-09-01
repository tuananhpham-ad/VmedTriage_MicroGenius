"""OpenStreetMapProvider - geocode qua Nominatim, tìm bệnh viện qua Overpass API.

Endpoint:
  - Nominatim search (forward):  GET {nominatim_base}/search?q=...&format=jsonv2&limit=1
  - Nominatim reverse:            GET {nominatim_base}/reverse?lat=...&lon=...&format=jsonv2
  - Photon (geocoder dự phòng):   GET {photon_base}/api?q=...  |  {photon_base}/reverse?lat=..&lon=..
  - Overpass (nearby hospital):   POST {overpass_base}   (nhiều endpoint, ngăn cách bằng dấu phẩy)
                                   body: data=[out:json][timeout:25];
                                         nwr(around:<mét>,<lat>,<lng>)["amenity"="hospital"];out center;

NOMINATIM USAGE POLICY bắt buộc User-Agent định danh thật cho server công cộng
(nominatim.openstreetmap.org) - request nặc danh dễ bị chặn IP. `osm_contact_email` (config) dựng
User-Agent; rỗng thì provider tự tắt giống thiếu API key, tôn trọng ToS thay vì gửi request nặc danh
(xem `_user_agent`).

SERVER CÔNG CỘNG GIỚI HẠN CỨNG 1 REQUEST/GIÂY và ToS cấm dùng cho hệ thống/production quy mô lớn -
provider này là PHƯƠNG ÁN DỰ PHÒNG FREE cuối cùng (đổi qua bằng HOSPITAL_LOOKUP_PROVIDER=osm), không
phải lựa chọn cho traffic thật lâu dài trừ khi tự host Nominatim/Overpass riêng.

PHOTON LÀ FALLBACK CHỈ CHO BƯỚC GEOCODE, không thay Overpass (Photon không tra được bệnh viện quanh
một điểm). Chỉ kích hoạt khi Nominatim gọi hỏng hoặc trả khác 200 - Nominatim tìm thấy 0 kết quả thì
coi là "địa chỉ không tồn tại", KHÔNG hỏi Photon lại, tránh hai nguồn trả hai đáp án khác nhau cho
cùng một địa chỉ.

Way/relation trong Overpass không có `lat`/`lon` phẳng - `out center;` thêm sẵn `center.lat/center.lon`,
dùng trường đó khi node không có toạ độ trực tiếp."""

from __future__ import annotations

import time

from src.config import get_settings
from src.services.hospital_lookup.distance import haversine_km
from src.services.hospital_lookup.models import GeocodeResult, HospitalCandidate, LookupFailure

_TIMEOUT_SECONDS = 20.0
# Overpass quá tải thường "treo" tới hết timeout chứ không trả lỗi ngay. Chờ đủ 20s ở TỪNG endpoint
# rồi mới đổi mirror thì tổng thời gian vọt lên hàng phút - bệnh nhân bỏ cuộc trước khi có kết quả.
# 12s đủ cho một truy vấn bán kính 5 km trên mirror khoẻ (đo thực tế 5-14s), và cắt sớm mirror chết.
_OVERPASS_TIMEOUT_SECONDS = 12.0
_OVERPASS_ROUNDS = 2
_OVERPASS_BACKOFF_SECONDS = 2.0
_OVERPASS_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


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
        return _photon_geocode(address, user_agent) or LookupFailure(
            f"Nominatim search không gọi được ({type(error).__name__})"
        )
    if response.status_code != 200:
        return _photon_geocode(address, user_agent) or LookupFailure(
            f"Nominatim search HTTP {response.status_code}"
        )

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
        return _photon_reverse(lat, lng, user_agent) or LookupFailure(
            f"Nominatim reverse không gọi được ({type(error).__name__})"
        )
    if response.status_code != 200:
        return _photon_reverse(lat, lng, user_agent) or LookupFailure(
            f"Nominatim reverse HTTP {response.status_code}"
        )

    body = response.json() or {}
    if "lat" not in body or "lon" not in body:
        return LookupFailure("Nominatim reverse không ra kết quả", not_found=True)
    return GeocodeResult(lat=float(body["lat"]), lng=float(body["lon"]), formatted_address=body.get("display_name", ""))


def _photon_feature(base_url: str, path: str, params: dict, user_agent: str) -> GeocodeResult | None:
    """Gọi Photon và đọc feature đầu tiên. Trả None khi tắt fallback/gọi hỏng/không có kết quả -
    người gọi giữ nguyên thông báo lỗi gốc của Nominatim, không nuốt mất nguyên nhân thật."""
    import httpx

    if not base_url.strip():
        return None
    try:
        response = httpx.get(
            f"{base_url}{path}", params=params, timeout=_TIMEOUT_SECONDS, headers={"User-Agent": user_agent}
        )
    except Exception:
        return None
    if response.status_code != 200:
        return None

    features = (response.json() or {}).get("features") or []
    if not features:
        return None
    # GeoJSON: toạ độ theo thứ tự [lng, lat] - NGƯỢC với Nominatim, đừng đảo nhầm.
    lng, lat = features[0]["geometry"]["coordinates"]
    return GeocodeResult(lat=float(lat), lng=float(lng), formatted_address=_photon_label(features[0]["properties"]))


def _photon_label(props: dict) -> str:
    """Photon không có `display_name` sẵn như Nominatim - ghép lại từ các field rời."""
    parts = [props.get(key) for key in ("name", "street", "district", "city", "state", "country")]
    return ", ".join(str(part) for part in parts if part)


def _photon_geocode(address: str, user_agent: str) -> GeocodeResult | None:
    return _photon_feature(get_settings().osm_photon_base_url, "/api", {"q": address, "limit": 1}, user_agent)


def _photon_reverse(lat: float, lng: float, user_agent: str) -> GeocodeResult | None:
    base_url = get_settings().osm_photon_base_url
    return _photon_feature(base_url, "/reverse", {"lat": lat, "lon": lng, "limit": 1}, user_agent)


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
    # Server Overpass công cộng rất hay 429 (quá rate-limit theo IP) / 504 (quá tải) - đo thực tế
    # overpass-api.de có lúc hỏng 3/3 lượt liên tiếp. Đây là lỗi TẠM THỜI của HẠ TẦNG, không phải
    # query sai, nên: thử lần lượt từng endpoint trong `osm_overpass_base_url` (danh sách ngăn cách
    # bằng dấu phẩy), rồi lặp lại cả danh sách thêm một vòng nữa với backoff. Endpoint nào trả 200
    # thì dừng ngay - vòng sau chỉ chạy khi TẤT CẢ đều hỏng.
    endpoints = [url.strip() for url in settings.osm_overpass_base_url.split(",") if url.strip()]
    if not endpoints:
        return LookupFailure("osm_overpass_base_url chưa cấu hình")

    response = None
    last_error: Exception | None = None
    last_status: int | None = None
    for round_index in range(_OVERPASS_ROUNDS):
        if round_index:
            time.sleep(_OVERPASS_BACKOFF_SECONDS)
        for endpoint in endpoints:
            try:
                response = httpx.post(
                    endpoint,
                    data={"data": overpass_query},
                    timeout=_OVERPASS_TIMEOUT_SECONDS,
                    headers={"User-Agent": user_agent},
                )
            except Exception as error:
                response, last_error = None, error
                continue
            if response.status_code not in _OVERPASS_RETRY_STATUS:
                break
            last_status = response.status_code
            response = None
        if response is not None:
            break

    if response is None:
        detail = f"HTTP {last_status}" if last_status else type(last_error).__name__
        return LookupFailure(f"Overpass không gọi được ({detail})")
    if response.status_code != 200:
        return LookupFailure(f"Overpass HTTP {response.status_code}")

    elements = response.json().get("elements") or []
    candidates = [_to_candidate(element, origin_lat=lat, origin_lng=lng) for element in elements]
    valid = sorted((c for c in candidates if c is not None), key=lambda item: item.distance_km)
    return tuple(valid[: settings.hospital_lookup_max_results])
