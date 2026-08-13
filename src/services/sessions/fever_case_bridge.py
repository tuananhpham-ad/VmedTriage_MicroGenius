"""Chuyển `Session` của agent fever (`symptom_protocol/session.py`) thành `TriageCase` của luồng
case/HITL (`src/models/schemas.py`).

VÌ SAO CẦN LỚP NÀY: agent fever vốn là luồng demo độc lập - có API riêng (`/api/v1/fever/*`) nhưng
KHÔNG tạo case, nên không màn hình điều dưỡng nào thấy được nó. Khi `/api/v1/chat` chuyển sang chạy
agent fever thay cho pipeline rule-based cũ, toàn bộ phần còn lại của sản phẩm (hàng đợi điều dưỡng,
lịch sử bệnh nhân, duyệt/HITL) vẫn đọc `case_store` như cũ - lớp này là chỗ duy nhất dịch giữa hai
mô hình dữ liệu, để không phải sửa gì bên `src/services/stores/` hay màn hình điều dưỡng.

HAI ĐIỀU KHÔNG ĐƯỢC PHÁ:
1. `case_id` DÙNG LUÔN `session_id` của agent - một phiên hội thoại là một case, không cần bảng ánh
   xạ phụ và không bao giờ lệch nhau.
2. Đây là hàm THUẦN (pure): đọc `Session`, trả `TriageCase` mới. Không gọi LLM, không ghi store,
   không đọc thời gian ngoài `updated_at`. Mọi quyết định lâm sàng đã do `rule_engine` chốt xong
   trước khi vào đây - lớp này TUYỆT ĐỐI không được tự suy ra mức độ khẩn cấp nào.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.models.schemas import (
    ActorRole,
    CaseStatus,
    ConversationMessage,
    HandoffSummary,
    NurseQueueItem,
    QueuePriority,
    RedFlagFinding,
    StructuredSymptomData,
    SummaryField,
    TriageCase,
    TriagePriority,
    TriageProposal,
    ValidationResult,
)
from src.services.checklists.fever_checklist import FIELDS_BY_KEY
from src.services.engines.fever_protocol import EMERGENCY_MESSAGE, REASON_CODE_LABELS
from src.services.symptom_protocol.session import Session, SessionState

# `triage_level` của rule engine -> `TriagePriority` hiển thị. EARLY_VISIT ánh xạ sang "Urgent"
# ("Khám sớm" trong UI) - đúng nghĩa nhất trong 5 mức có sẵn của thang hiện tại.
_PRIORITY_BY_LEVEL: dict[str, TriagePriority] = {
    "EMERGENCY": TriagePriority.EMERGENCY,
    "EARLY_VISIT": TriagePriority.URGENT,
    "SELF_CARE": TriagePriority.SELF_CARE,
}

# Chỉ field M0/M1 mới được tính là "còn thiếu" và mới lên phiếu tóm tắt. Tier C/O/H là thông tin bổ
# trợ - đưa hết lên phiếu chỉ làm điều dưỡng phải đọc 101 dòng để tìm 20 dòng có ý nghĩa.
_SUMMARY_TIERS = frozenset({"M0", "M1"})

_UNSET = (None, "", "unknown")


def _is_filled(value: object) -> bool:
    return value not in _UNSET


def _summary_keys() -> tuple[str, ...]:
    return tuple(key for key, spec in FIELDS_BY_KEY.items() if spec.tier in _SUMMARY_TIERS)


def _missing_fields(answers: dict[str, object]) -> list[str]:
    return [key for key in _summary_keys() if not _is_filled(answers.get(key))]


def _status_for(session: Session) -> CaseStatus:
    if session.state is SessionState.EMERGENCY:
        return CaseStatus.ESCALATED
    if session.state is SessionState.COLLECTING:
        return CaseStatus.COLLECTING_INFORMATION
    # AWAITING_CONFIRMATION (bệnh nhân chưa xác nhận phiếu) và CONFIRMED (đã xác nhận) đều là "chờ
    # điều dưỡng duyệt" dưới góc nhìn case - việc bệnh nhân xác nhận phiếu KHÔNG phải một bước duyệt.
    return CaseStatus.NEEDS_NURSE_REVIEW


def _red_flags(session: Session) -> list[RedFlagFinding]:
    return [
        RedFlagFinding(code=code, label=REASON_CODE_LABELS.get(code, code), matched_fields=[])
        for code in session.reason_codes
    ]


def _chief_complaint(answers: dict[str, object]) -> str:
    temp = answers.get("temp_c")
    if _is_filled(temp):
        return f"Sốt {temp}°C"
    return "Sốt"


def _summary_fields(answers: dict[str, object]) -> list[SummaryField]:
    rows = []
    for key in _summary_keys():
        value = answers.get(key)
        filled = _is_filled(value)
        rows.append(SummaryField(label=FIELDS_BY_KEY[key].label, value=value if filled else None, is_missing=not filled))
    return rows


def _conversation(session: Session) -> list[ConversationMessage]:
    messages = []
    for turn in session.conversation:
        content = (turn.get("content") or "").strip()
        if not content:
            continue  # ConversationMessage yêu cầu min_length=1
        role = ActorRole.PATIENT if turn.get("role") == "user" else ActorRole.SYSTEM
        messages.append(ConversationMessage(role=role, content=content))
    return messages


def _triage_proposal(session: Session) -> TriageProposal | None:
    """CHỈ sinh đề xuất khi rule engine đã chốt (`triage_level`). Trong lúc còn đang hỏi, không có
    đề xuất nào cả - không được đoán trước rồi hiển thị cho điều dưỡng."""
    if not session.triage_level:
        return None
    return TriageProposal(
        priority=_PRIORITY_BY_LEVEL.get(session.triage_level, TriagePriority.MANUAL_REVIEW),
        protocol_id="fever",
        reason=", ".join(session.triggered_rules) or session.stop_reason or "",
        confidence=0.0,
        requires_manual_review=True,
        detect_source="fever_intake_agent (LLM extraction theo cụm)",
        grounding_source="fever-knowledge-model.md §6.1 (rule engine thuần, không LLM)",
    )


def _summary(session: Session, answers: dict[str, object]) -> HandoffSummary:
    return HandoffSummary(
        chief_complaint=_chief_complaint(answers),
        onset=str(answers["fever_onset_at"]) if _is_filled(answers.get("fever_onset_at")) else None,
        severity=answers.get("temp_c") if _is_filled(answers.get("temp_c")) else None,
        associated_symptoms=[
            FIELDS_BY_KEY[key].label
            for key, value in answers.items()
            if key in FIELDS_BY_KEY and value == "true"
        ],
        missing_information=_missing_fields(answers),
        red_flags=_red_flags(session),
        proposed_priority=_PRIORITY_BY_LEVEL.get(session.triage_level or "", None),
        protocol_reason=", ".join(session.triggered_rules),
        detect_source="fever_intake_agent",
        grounding_source="fever-knowledge-model.md §6.1",
    )


def to_triage_case(session: Session, *, patient_id: int | None, previous: TriageCase | None = None) -> TriageCase:
    """Dựng lại `TriageCase` từ trạng thái HIỆN TẠI của phiên agent.

    `previous` chỉ dùng để giữ lại phần do ĐIỀU DƯỠNG ghi (`nurse_feedback`, `reviewed_by_*`) và mốc
    `created_at` - agent không biết gì về những thứ đó, dựng lại từ đầu mỗi lượt sẽ xoá mất."""
    answers = dict(session.answers)
    status = _status_for(session)
    missing = _missing_fields(answers)
    is_collecting = status is CaseStatus.COLLECTING_INFORMATION

    structured_data = StructuredSymptomData(
        symptom_group="fever",
        fields={key: value for key, value in answers.items() if _is_filled(value)},
        missing_fields=missing,
        confidence=0.0,
        source="fever_intake_agent",
    )
    validation = ValidationResult(
        is_valid=not is_collecting,
        missing_fields=missing,
        contradictions=[],
        low_confidence=not session.llm_used_last_turn,
        follow_up_questions=[session.last_question] if session.last_question else [],
    )
    summary = _summary(session, answers)
    proposal = _triage_proposal(session)

    return TriageCase(
        case_id=session.session_id,
        conversation=_conversation(session),
        structured_data=structured_data,
        validation=validation,
        red_flags=_red_flags(session),
        triage_proposal=proposal,
        summary=summary,
        queue_item=(
            None
            if is_collecting
            else NurseQueueItem(
                case_id=session.session_id,
                queue_priority=(
                    QueuePriority.HIGH if status is CaseStatus.ESCALATED else QueuePriority.STANDARD
                ),
                status=status,
                summary=summary,
                structured_data=structured_data,
                validation=validation,
                triage_proposal=proposal,
            )
        ),
        status=status,
        # Lúc đang hỏi, "phản hồi cho bệnh nhân" chính là câu hỏi kế tiếp của agent. Khi chốt đỏ thì
        # là thông điệp cấp cứu cố định (KHÔNG do LLM sinh, đúng P0-5). Ngoài hai trường hợp đó thì
        # không có gì hiển thị cho bệnh nhân trước khi điều dưỡng duyệt.
        patient_visible_response=(
            session.last_question
            if is_collecting
            else EMERGENCY_MESSAGE
            if status is CaseStatus.ESCALATED
            else None
        ),
        nurse_feedback=previous.nurse_feedback if previous else None,
        reviewed_by_id=previous.reviewed_by_id if previous else None,
        reviewed_by_name=previous.reviewed_by_name if previous else None,
        reviewed_at=previous.reviewed_at if previous else None,
        patient_id=patient_id,
        created_at=previous.created_at if previous else session.created_at,
        updated_at=datetime.now(timezone.utc),
        next_message=session.last_question or None,
        # `summary_ready` = "phiếu đã chốt, xin bệnh nhân xác nhận" nên chỉ bật khi hết hỏi. Nhưng
        # `summary_fields` thì luôn dựng: cột "Thông tin cần làm rõ" của bệnh nhân cần nhãn tiếng
        # Việt ngay từ lượt đầu - nếu để rỗng, UI rơi về `missing_fields` là danh sách key thô
        # (`fever_onset_at`, `urine_output`...), đọc không hiểu gì.
        summary_ready=not is_collecting,
        summary_fields=_summary_fields(answers),
    )
