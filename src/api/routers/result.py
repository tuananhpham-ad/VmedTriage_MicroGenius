from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from src.models.case_api import CaseResultResponse, DisclaimerResponse
from src.services.engines.priority_labels import priority_label_vi
from src.services.stores.approval_store import approval_store
from src.services.stores.case_store import case_store

router = APIRouter(tags=["Feature 4 - Disclaimer & Kết quả cho bệnh nhân"])

DISCLAIMER_TEXT = (
    "VMedTriage là công cụ hỗ trợ khai thác triệu chứng và gợi ý mức độ ưu tiên khám bệnh. "
    "Đây KHÔNG PHẢI là bác sĩ và KHÔNG THAY THẾ cho việc thăm khám, tư vấn hoặc chẩn đoán y tế "
    "chuyên môn. Mọi kết luận của hệ thống đều phải được điều dưỡng/bác sĩ xem xét và duyệt trước "
    "khi gửi tới bạn. Nếu bạn đang gặp tình huống nguy hiểm đến tính mạng (đau ngực dữ dội, khó thở "
    "nặng, chảy máu không cầm được, mất ý thức, co giật...), hãy gọi cấp cứu 115 hoặc đến ngay cơ sở "
    "y tế gần nhất, không chờ hệ thống phản hồi."
)

_GUIDANCE_BY_PRIORITY: dict[str, str] = {
    "Emergency": "Đây là mức Cấp cứu: hãy đến ngay cơ sở cấp cứu gần nhất hoặc gọi 115.",
    "Urgent": "Đây là mức Khám sớm: bạn nên đến khám trong vài giờ tới.",
    "Routine": "Đây là mức Khám sớm: bạn có thể sắp xếp khám trong 1-2 ngày tới.",
    "Self-care": "Đây là mức Tự theo dõi: bạn có thể theo dõi tại nhà và tái khám nếu triệu chứng nặng hơn.",
    "Manual review": "Trường hợp của bạn cần được nhân viên y tế đánh giá trực tiếp.",
}


@router.get("/disclaimer", response_model=DisclaimerResponse)
async def get_disclaimer() -> DisclaimerResponse:
    """Nội dung disclaimer tĩnh - công cụ không thay thế bác sĩ."""
    return DisclaimerResponse(text=DISCLAIMER_TEXT)


@router.get("/cases/{case_id}/result", response_model=CaseResultResponse)
async def get_case_result(case_id: str, request: Request) -> CaseResultResponse:
    """Patient-only, kiểm tra ownership. Chỉ trả nội dung xử trí chi tiết khi đã được duyệt."""
    triage_case = case_store.get(case_id)
    if not triage_case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy case")

    current_user_id = int(request.state.auth.sub)
    if triage_case.patient_id != current_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bạn không có quyền xem kết quả của case này")

    red_flag = bool(triage_case.red_flags)
    approval = approval_store.get(case_id)

    if approval and approval.final_priority:
        return CaseResultResponse(
            case_id=case_id,
            is_approved=True,
            red_flag=red_flag,
            message="Kết quả đã được điều dưỡng duyệt.",
            final_priority=approval.final_priority,
            priority_label_vi=priority_label_vi(approval.final_priority),
            summary=triage_case.summary,
            summary_fields=triage_case.summary_fields,
            guidance=_GUIDANCE_BY_PRIORITY.get(
                approval.final_priority, "Vui lòng liên hệ cơ sở y tế để được tư vấn thêm."
            ),
        )

    # Chưa duyệt: TUYỆT ĐỐI không lộ nội dung xử trí chi tiết, chỉ trả trạng thái + thời gian chờ ước tính.
    # red_flag vẫn được trả sớm để hiển thị banner khẩn cấp ngay.
    return CaseResultResponse(
        case_id=case_id,
        is_approved=False,
        red_flag=red_flag,
        message="Hồ sơ của bạn đang chờ điều dưỡng xem xét và duyệt kết quả.",
        estimated_wait_minutes=5 if red_flag else 30,
    )
