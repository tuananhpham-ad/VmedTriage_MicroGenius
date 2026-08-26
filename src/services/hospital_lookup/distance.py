"""Khoảng cách đường chim bay giữa hai toạ độ - dùng chung cho cả 3 provider để số liệu so sánh được
với nhau khi đổi nhà cung cấp qua config.

Vì sao cần hàm riêng dù có provider tự trả khoảng cách: Goong `Place/AutoComplete` là text search có
location bias, KHÔNG đảm bảo sort theo khoảng cách thật - `providers/goong.py` phải tự tính rồi sắp
lại. Google/OSM cũng tính lại bằng đúng công thức này thay vì tin số của từng bên, để danh sách nhất
quán bất kể đang dùng provider nào.
"""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

_EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Khoảng cách đường chim bay (km). Sai số ~0.5% so với khoảng cách thật trên mặt cầu - đủ để sắp
    xếp/hiển thị "gần nhất", KHÔNG dùng để ước lượng thời gian di chuyển (đường đi thật luôn dài hơn)."""
    lat1_r, lng1_r, lat2_r, lng2_r = radians(lat1), radians(lng1), radians(lat2), radians(lng2)
    dlat = lat2_r - lat1_r
    dlng = lng2_r - lng1_r
    a = sin(dlat / 2) ** 2 + cos(lat1_r) * cos(lat2_r) * sin(dlng / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * asin(sqrt(a))
