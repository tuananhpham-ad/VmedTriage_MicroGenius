"""`/cases/{case_id}/hospital-suggestions` - gợi ý bệnh viện gần nhất, PATIENT-ONLY (xem ADR-010).

CHỈ 2 endpoint, KHÔNG có bước duyệt của điều dưỡng - ngoại lệ có phạm vi HẸP với ADR-002 (HITL bắt
buộc 100%), chỉ áp dụng cho tính năng này (xem docstring `src/models/hospital_suggestion.py`).

⚠️ Route phải được khai báo TƯỜNG MINH trong `src/middleware/auth.py::ROUTE_POLICIES`. Middleware đó
fail-open: thiếu dòng khai báo nghĩa là route mở public không cần token, không phải "mặc định từ
chối" (xem comment ở `ROUTE_POLICIES`)."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status

from src.models.hospital_api import HospitalCandidateResponse, HospitalSuggestionRequest, HospitalSuggestionResponse
from src.models.schemas import TriageCase
from src.services.hospital_lookup.lookup_service import (
    AddressGeocodeFailedError,
    HospitalLookupQuery,
    ProviderNotConfiguredError,
    ProviderRequestFailedError,
    suggest_hospitals_for_case,
)
from src.services.stores.approval_store import AuditLogEntry, approval_store
from src.services.stores.case_store import case_store
from src.services.stores.hospital_suggestion_store import (
    HospitalCandidateView,
    HospitalSuggestionRecord,
    hospital_suggestion_store,
)

router = APIRouter(tags=["Gợi ý bệnh viện gần nhất"])


def _case_owned_by(case_id: str, request: Request) -> int:
    """404 nếu case không tồn tại, 403 nếu không phải chủ case - đúng pattern `result.py::get_case_result`.
    Trả về `patient_id` (int) của người gọi khi hợp lệ."""
    triage_case: TriageCase | None = case_store.get(case_id)
    if not triage_case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy case")
    current_user_id = int(request.state.auth.sub)
    if triage_case.patient_id != current_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bạn không có quyền truy cập case này")
    return current_user_id


def _to_response(case_id: str, record: HospitalSuggestionRecord) -> HospitalSuggestionResponse:
    return HospitalSuggestionResponse(
        case_id=case_id,
        provider=record.provider,
        address_text=record.address_text or "",
        patient_lat=record.patient_lat,
        patient_lng=record.patient_lng,
        requested_at=record.requested_at,
        hospitals=[HospitalCandidateResponse(**item.model_dump()) for item in record.hospitals],
    )


@router.post("/cases/{case_id}/hospital-suggestions", response_model=HospitalSuggestionResponse)
async def request_hospital_suggestions(
    case_id: str, body: HospitalSuggestionRequest, request: Request
) -> HospitalSuggestionResponse:
    """Tra cứu qua nhà cung cấp đang cấu hình (`Settings.hospital_lookup_provider`) và trả THẲNG danh
    sách bệnh viện trong response - không có trạng thái "chờ duyệt" (xem docstring module)."""
    current_user_id = _case_owned_by(case_id, request)

    try:
        result = suggest_hospitals_for_case(
            HospitalLookupQuery(latitude=body.latitude, longitude=body.longitude, address_text=body.address_text)
        )
    except ProviderNotConfiguredError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    except ProviderRequestFailedError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    except AddressGeocodeFailedError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error

    now = datetime.now(timezone.utc)
    record = HospitalSuggestionRecord(
        case_id=case_id,
        requested_by=current_user_id,
        requested_at=now,
        location_source="gps" if body.latitude is not None else "manual_address",
        patient_lat=result.patient_lat,
        patient_lng=result.patient_lng,
        address_text=result.address_text,
        provider=result.provider,
        hospitals=[HospitalCandidateView(**asdict(item)) for item in result.hospitals],
        updated_at=now,
    )
    hospital_suggestion_store.upsert(record)
    # Không có bước duyệt để audit "ai duyệt" (ADR-010) - nhưng vẫn ghi "bệnh nhân đã xem gợi ý gì,
    # lúc nào" phục vụ nguyên tắc bảo vệ PII/PHI #5 (CLAUDE.md). Tái dùng audit_log chung, không tạo
    # bảng audit riêng cho tính năng này.
    approval_store.log(
        AuditLogEntry(case_id=case_id, actor=str(current_user_id), action="hospital_suggestion_requested")
    )
    return _to_response(case_id, record)


@router.get("/cases/{case_id}/hospital-suggestions", response_model=HospitalSuggestionResponse)
async def get_hospital_suggestions(case_id: str, request: Request) -> HospitalSuggestionResponse:
    """Đọc lại cache đã lưu - KHÔNG gọi lại provider (giữ quota, xem `src/config.py`)."""
    _case_owned_by(case_id, request)
    record = hospital_suggestion_store.get(case_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Chưa có yêu cầu gợi ý bệnh viện nào cho case này"
        )
    return _to_response(case_id, record)
