"""Value object dùng chung giữa 3 provider gợi ý bệnh viện gần nhất (xem ADR-010).

Tách riêng khỏi từng provider để `lookup_service.py` không cần biết provider nào đang chạy - mọi
provider chuẩn hoá response của mình (Goong/Google/OSM có shape hoàn toàn khác nhau) về đúng các
kiểu này NGAY tại provider, không rò hình dạng riêng lên tầng trên.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GeocodeResult:
    """Toạ độ + địa chỉ chuẩn hoá, kết quả của `geocode()`/`reverse_geocode()`."""

    lat: float
    lng: float
    formatted_address: str


@dataclass(frozen=True, slots=True)
class HospitalCandidate:
    """Một cơ sở y tế ứng viên, đã tính khoảng cách tới vị trí tra cứu."""

    place_id: str
    name: str
    address: str
    lat: float
    lng: float
    distance_km: float
    phone: str | None = None


@dataclass(frozen=True, slots=True)
class LookupFailure:
    """Vì sao một lời gọi provider không ra kết quả. KHÔNG raise - xem docstring từng module provider,
    đúng nguyên tắc best-effort của `src/source_support/fetching.py`/`search.py`.

    `not_found` phân biệt hai loại thất bại khác hẳn nhau ở tầng router (`lookup_service.py` map
    sang mã HTTP): `True` = provider trả lời HỢP LỆ nhưng không có kết quả (địa chỉ không tồn tại/
    gõ sai - lỗi của người dùng, 422); `False` (mặc định) = lỗi cấu hình/mạng/HTTP - lỗi của hệ
    thống hoặc nhà cung cấp, không phải của địa chỉ đã nhập (503)."""

    reason: str
    not_found: bool = False
