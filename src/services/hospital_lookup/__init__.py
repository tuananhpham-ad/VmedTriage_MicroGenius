"""Gợi ý bệnh viện gần nhất cho bệnh nhân (patient-only, xem ADR-010 trong `docs/context/decisions.md`).

Tách khỏi `src/source_support/` vì đó là domain "trích dẫn y văn" (allowlist domain, guard nội dung,
index cosine) - hoàn toàn khác nghiệp vụ ở đây: gọi API bản đồ/toạ độ để tìm địa điểm gần một vị trí.

`lookup_service.py` là ranh giới công khai duy nhất; `providers/` chứa 3 implementation
(Goong/Google Maps/OpenStreetMap) cùng chữ ký hàm, chọn qua `Settings.hospital_lookup_provider`.
"""
