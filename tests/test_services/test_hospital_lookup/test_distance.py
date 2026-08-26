"""`haversine_km` - hàm thuần, không chạm mạng."""

from __future__ import annotations

import pytest

from src.services.hospital_lookup.distance import haversine_km

# Hồ Gươm (Hà Nội) -> Nhà thờ Đức Bà (TP.HCM). Số tham chiếu đo thật bằng chính công thức
# haversine (không phải ước lượng): 1143.17km.
_HANOI = (21.0285, 105.8542)
_HCMC = (10.7798, 106.6990)


def test_haversine_km_same_point_is_zero() -> None:
    assert haversine_km(21.0285, 105.8542, 21.0285, 105.8542) == pytest.approx(0.0, abs=1e-9)


def test_haversine_km_known_distance_hanoi_hcmc() -> None:
    distance = haversine_km(*_HANOI, *_HCMC)
    assert distance == pytest.approx(1143.17, abs=0.1)


def test_haversine_km_is_symmetric() -> None:
    forward = haversine_km(*_HANOI, *_HCMC)
    backward = haversine_km(*_HCMC, *_HANOI)
    assert forward == pytest.approx(backward, abs=1e-9)
