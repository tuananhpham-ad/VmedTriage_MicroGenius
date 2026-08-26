"""`/cases/{case_id}/hospital-suggestions` - patient-only, KHÔNG có bước duyệt điều dưỡng (ADR-010).

Mock ở tầng `hospital_suggestion.suggest_hospitals_for_case` (đã import thẳng vào namespace router,
đúng pattern `monkeypatch.setattr(routes.graph_triage_service, ...)` ở `test_routes.py`) - cơ chế
gọi Goong/Google/OSM thật đã có test riêng ở `tests/test_services/test_hospital_lookup/`."""

from __future__ import annotations

import pytest

from src.api.routers import hospital_suggestion
from src.services.hospital_lookup.lookup_service import (
    AddressGeocodeFailedError,
    HospitalSuggestionResult,
    ProviderNotConfiguredError,
    ProviderRequestFailedError,
)
from src.services.hospital_lookup.models import HospitalCandidate

pytestmark = pytest.mark.asyncio

_HOSPITAL = HospitalCandidate(
    place_id="p1", name="Bệnh viện Bạch Mai", address="78 Giải Phóng, Hà Nội", lat=21.0, lng=105.8, distance_km=1.2
)


def _fake_result(**overrides) -> HospitalSuggestionResult:
    defaults = dict(
        patient_lat=21.0, patient_lng=105.8, address_text="78 Giải Phóng, Hà Nội", provider="goong", hospitals=(_HOSPITAL,)
    )
    defaults.update(overrides)
    return HospitalSuggestionResult(**defaults)


async def _create_case(client, patient_headers) -> str:
    response = await client.post(
        "/api/v1/chat", json={"message": "Tôi bị sốt."}, headers=patient_headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["case_id"]


async def test_post_returns_hospitals_directly_without_review_step(client, patient_headers, monkeypatch):
    case_id = await _create_case(client, patient_headers)
    monkeypatch.setattr(hospital_suggestion, "suggest_hospitals_for_case", lambda query: _fake_result())

    response = await client.post(
        f"/api/v1/cases/{case_id}/hospital-suggestions", json={"latitude": 21.0, "longitude": 105.8}, headers=patient_headers
    )

    assert response.status_code == 200, response.text
    body = response.json()
    # Không có "status"/"pending" nào - ADR-010 chốt bệnh nhân thấy trực tiếp, không qua duyệt.
    assert "status" not in body
    assert body["hospitals"][0]["name"] == "Bệnh viện Bạch Mai"
    assert body["provider"] == "goong"
    # patient_lat/patient_lng PHẢI có trong response - frontend (renderHospitalMap, patient.js) cần
    # để vẽ marker vị trí bệnh nhân trên bản đồ. Từng thiếu thật (response model quên khai 2 field
    # này khi thêm bản đồ), gãy thành "Invalid LatLng object: (undefined, undefined)" ở Leaflet.
    assert body["patient_lat"] == 21.0
    assert body["patient_lng"] == 105.8


async def test_get_returns_previously_cached_result(client, patient_headers, monkeypatch):
    case_id = await _create_case(client, patient_headers)
    monkeypatch.setattr(hospital_suggestion, "suggest_hospitals_for_case", lambda query: _fake_result())
    await client.post(
        f"/api/v1/cases/{case_id}/hospital-suggestions", json={"latitude": 21.0, "longitude": 105.8}, headers=patient_headers
    )

    response = await client.get(f"/api/v1/cases/{case_id}/hospital-suggestions", headers=patient_headers)

    assert response.status_code == 200
    assert response.json()["hospitals"][0]["name"] == "Bệnh viện Bạch Mai"


async def test_get_without_prior_request_returns_404(client, patient_headers):
    case_id = await _create_case(client, patient_headers)

    response = await client.get(f"/api/v1/cases/{case_id}/hospital-suggestions", headers=patient_headers)

    assert response.status_code == 404


async def test_other_patient_cannot_access_case(client, patient_headers):
    """Đúng kỹ thuật `test_routes.py` (case "stolen"): sửa thẳng `patient_id` trên case đã lưu thay vì
    dựng thêm một tài khoản thật - rẻ và tường minh hơn, vẫn chạm đúng nhánh cần kiểm."""
    from src.services.stores.case_store import case_store

    case_id = await _create_case(client, patient_headers)
    stolen = case_store.get(case_id)
    stolen.patient_id = (stolen.patient_id or 0) + 999
    case_store.save(stolen)

    response = await client.post(
        f"/api/v1/cases/{case_id}/hospital-suggestions", json={"latitude": 21.0, "longitude": 105.8}, headers=patient_headers
    )

    assert response.status_code == 403


async def test_missing_location_and_address_returns_422(client, patient_headers):
    case_id = await _create_case(client, patient_headers)

    response = await client.post(f"/api/v1/cases/{case_id}/hospital-suggestions", json={}, headers=patient_headers)

    assert response.status_code == 422


async def test_provider_not_configured_returns_503(client, patient_headers, monkeypatch):
    case_id = await _create_case(client, patient_headers)

    def raise_not_configured(query):
        raise ProviderNotConfiguredError("goong_api_key chưa cấu hình")

    monkeypatch.setattr(hospital_suggestion, "suggest_hospitals_for_case", raise_not_configured)

    response = await client.post(
        f"/api/v1/cases/{case_id}/hospital-suggestions", json={"latitude": 21.0, "longitude": 105.8}, headers=patient_headers
    )

    assert response.status_code == 503


async def test_provider_request_failed_returns_503(client, patient_headers, monkeypatch):
    case_id = await _create_case(client, patient_headers)

    def raise_failed(query):
        raise ProviderRequestFailedError("Goong sập")

    monkeypatch.setattr(hospital_suggestion, "suggest_hospitals_for_case", raise_failed)

    response = await client.post(
        f"/api/v1/cases/{case_id}/hospital-suggestions", json={"latitude": 21.0, "longitude": 105.8}, headers=patient_headers
    )

    assert response.status_code == 503


async def test_address_geocode_failed_returns_422(client, patient_headers, monkeypatch):
    case_id = await _create_case(client, patient_headers)

    def raise_geocode_failed(query):
        raise AddressGeocodeFailedError("không tìm thấy địa chỉ này")

    monkeypatch.setattr(hospital_suggestion, "suggest_hospitals_for_case", raise_geocode_failed)

    response = await client.post(
        f"/api/v1/cases/{case_id}/hospital-suggestions",
        json={"address_text": "địa chỉ không tồn tại trên đời"},
        headers=patient_headers,
    )

    assert response.status_code == 422


async def test_route_requires_bearer_token(client, patient_headers):
    case_id = await _create_case(client, patient_headers)

    response = await client.post(
        f"/api/v1/cases/{case_id}/hospital-suggestions", json={"latitude": 21.0, "longitude": 105.8}
    )

    assert response.status_code == 401


async def test_nurse_cannot_access_this_patient_only_endpoint(client, patient_headers, nurse_headers):
    """Khẳng định đúng phạm vi đã chốt (ADR-010): CHỈ patient, không có vai trò nurse ở đây."""
    case_id = await _create_case(client, patient_headers)

    response = await client.post(
        f"/api/v1/cases/{case_id}/hospital-suggestions", json={"latitude": 21.0, "longitude": 105.8}, headers=nurse_headers
    )

    assert response.status_code == 403
