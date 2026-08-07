from __future__ import annotations

from src.config import (
    DETECT_SOURCE_LABEL,
    FOLLOW_UP_QUESTIONS,
    GROUNDING_SOURCE_LABEL,
    REQUIRED_FIELDS_BY_SYMPTOM_GROUP,
    get_settings,
)
from src.models.schemas import CaseStatus, SummaryField, TriageCase
from src.services.case_store import case_store
from src.services.quality_guard import quality_guard
from src.services.triage_pipeline import triage_pipeline

# Cho phép hỏi lại tối đa 1 lần cho mỗi field còn thiếu (tổng cộng 2 lượt: lượt hỏi đầu + 1 lần hỏi lại),
# sau đó đánh dấu field đó "Thiếu thông tin" và không chặn luồng hội thoại nữa.
ALLOWED_ASKS = 2
_LOW_CONFIDENCE_KEY = "_low_confidence"
_LOW_CONFIDENCE_QUESTION = "Bạn có thể mô tả lại triệu chứng chính rõ hơn không?"


class EmptyMessageError(ValueError):
    """Input rỗng/không hợp lệ - KHÔNG để agent tự suy diễn."""


class CaseNotFoundError(ValueError):
    pass


class CaseAccessDeniedError(PermissionError):
    pass


def _clean_message(message: str) -> str:
    stripped = (message or "").strip()
    if not stripped:
        raise EmptyMessageError("Nội dung tin nhắn không được để trống.")
    return stripped


async def start_case(message: str, patient_id: int) -> TriageCase:
    """Feature #1: POST /cases - tạo case mới, agent detect nhóm triệu chứng ngay từ tin đầu."""
    cleaned = _clean_message(message)
    triage_case = await triage_pipeline.handle_patient_message(cleaned)
    triage_case.patient_id = patient_id
    return _finalize_turn(triage_case)


async def continue_case(case_id: str, message: str, patient_id: int) -> TriageCase:
    """Feature #1: POST /cases/{id}/responses - tiếp tục hội thoại đã có."""
    existing = case_store.get(case_id)
    if not existing:
        raise CaseNotFoundError("Không tìm thấy case.")
    if existing.patient_id is not None and existing.patient_id != patient_id:
        raise CaseAccessDeniedError("Bạn không có quyền gửi tin nhắn cho case này.")

    cleaned = _clean_message(message)
    triage_case = await triage_pipeline.handle_patient_message(cleaned, case_id=case_id)
    triage_case.patient_id = existing.patient_id if existing.patient_id is not None else patient_id
    triage_case.field_ask_counts = dict(existing.field_ask_counts)
    return _finalize_turn(triage_case)


def _finalize_turn(triage_case: TriageCase) -> TriageCase:
    """Áp dụng logic 'hỏi lại tối đa 1 lần', gắn nguồn detect/grounding, và sinh summary_fields."""
    validation = triage_case.validation
    red_flags = triage_case.red_flags

    active_questions: list[str] = []
    if not red_flags and validation is not None:
        for field in validation.missing_fields:
            count = triage_case.field_ask_counts.get(field, 0) + 1
            triage_case.field_ask_counts[field] = count
            if count <= ALLOWED_ASKS:
                question = FOLLOW_UP_QUESTIONS.get(field, f"Bạn có thể cung cấp thêm thông tin về '{field}' không?")
                active_questions.append(question)

        if validation.low_confidence:
            count = triage_case.field_ask_counts.get(_LOW_CONFIDENCE_KEY, 0) + 1
            triage_case.field_ask_counts[_LOW_CONFIDENCE_KEY] = count
            if count <= ALLOWED_ASKS:
                active_questions.append(_LOW_CONFIDENCE_QUESTION)

    summary_ready = bool(red_flags) or not active_questions
    triage_case.next_message = active_questions[0] if active_questions else None
    triage_case.summary_ready = summary_ready

    # Sau khi đủ field bắt buộc HOẶC phát hiện red-flag -> đẩy vào hàng đợi chờ duyệt.
    # NEEDS_MORE_INFO cũng được coi như đang thu thập lại: bệnh nhân vừa trả lời câu hỏi điều dưỡng
    # chỉ định (case_approval.ask_more), lượt tiếp theo phải quay lại vào hàng đợi bình thường.
    if summary_ready and triage_case.status in (CaseStatus.COLLECTING_INFORMATION, CaseStatus.NEEDS_MORE_INFO):
        triage_case.status = CaseStatus.NEEDS_NURSE_REVIEW if red_flags else CaseStatus.AWAITING_APPROVAL

    triage_case.summary_fields = _build_summary_fields(triage_case)
    # Chỉ gắn nhãn - quyết định suppress khỏi hàng đợi nằm ở case_approval.list_queue(), nơi red-flag
    # luôn được ưu tiên tuyệt đối bất kể quality_flag nói gì.
    triage_case.quality_flag = quality_guard.assess(triage_case)

    if triage_case.summary:
        triage_case.summary.detect_source = DETECT_SOURCE_LABEL
        triage_case.summary.grounding_source = GROUNDING_SOURCE_LABEL
    if triage_case.triage_proposal:
        triage_case.triage_proposal.detect_source = DETECT_SOURCE_LABEL
        triage_case.triage_proposal.grounding_source = GROUNDING_SOURCE_LABEL

    return case_store.save(triage_case)


def _build_summary_fields(triage_case: TriageCase) -> list[SummaryField]:
    """Feature #5: phiếu tóm tắt có cấu trúc - field không map được -> is_missing=true, KHÔNG bịa giá trị."""
    if not triage_case.structured_data:
        return []

    data = triage_case.structured_data
    required_fields = REQUIRED_FIELDS_BY_SYMPTOM_GROUP.get(
        data.symptom_group,
        REQUIRED_FIELDS_BY_SYMPTOM_GROUP[get_settings().default_symptom_group],
    )

    fields: list[SummaryField] = []
    for field in required_fields:
        label = FOLLOW_UP_QUESTIONS.get(field, field)
        is_missing = field not in data.fields
        value = None if is_missing else data.fields.get(field)
        fields.append(SummaryField(label=label, value=value, is_missing=is_missing))
    return fields
