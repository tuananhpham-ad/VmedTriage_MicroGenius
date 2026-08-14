"""Chuyển `Session` của agent (`symptom_protocol/session.py`) thành `TriageCase` của luồng case/HITL
(`src/models/schemas.py`) - cho MỌI protocol, không riêng fever.

VÌ SAO CẦN LỚP NÀY: agent vốn là luồng demo độc lập - có API riêng (`/api/v1/fever/*`) nhưng KHÔNG
tạo case, nên không màn hình điều dưỡng nào thấy được nó. Khi `/api/v1/chat` chuyển sang chạy agent
thay cho pipeline rule-based cũ, toàn bộ phần còn lại của sản phẩm (hàng đợi điều dưỡng, lịch sử bệnh
nhân, duyệt/HITL) vẫn đọc `case_store` như cũ - lớp này là chỗ duy nhất dịch giữa hai mô hình dữ
liệu, để không phải sửa gì bên `src/services/stores/` hay màn hình điều dưỡng.

BA ĐIỀU KHÔNG ĐƯỢC PHÁ:
1. `case_id` DÙNG LUÔN `session_id` của agent - một phiên hội thoại là một case, không cần bảng ánh
   xạ phụ và không bao giờ lệch nhau.
2. Đây là hàm THUẦN (pure): đọc `Session`, trả `TriageCase` mới. Không gọi LLM, không ghi store,
   không đọc thời gian ngoài `updated_at`. Mọi quyết định lâm sàng đã do `rule_engine` chốt xong
   trước khi vào đây - lớp này TUYỆT ĐỐI không được tự suy ra mức độ khẩn cấp nào.
3. Mọi thứ đặc thù bệnh đọc từ `protocol`, KHÔNG ghi cứng. Bản đầu ghi cứng field/nhãn của fever nên
   một ca đau ngực vẫn được gửi đi kèm `symptom_group="fever"` và chief complaint "Sốt" - đó là sai
   DỮ LIỆU (bên triage huấn luyện trên đó), không phải sai hiển thị.
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
from src.services.symptom_protocol import registry
from src.services.symptom_protocol.protocol import SymptomProtocol
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


def _summary_keys(protocol: SymptomProtocol) -> tuple[str, ...]:
    return tuple(key for key, spec in protocol.fields_by_key.items() if spec.tier in _SUMMARY_TIERS)


def _missing_fields(protocol: SymptomProtocol, answers: dict[str, object]) -> list[str]:
    return [key for key in _summary_keys(protocol) if not _is_filled(answers.get(key))]


def _symptom_field_values(protocol: SymptomProtocol, answers: dict[str, object]) -> dict[str, object]:
    """JSON phẳng các trường triệu chứng cho bên triage (model xác suất) - MỌI field của protocol đều
    có mặt, kể cả field chưa hỏi tới.

    KHÔNG lọc theo `_is_filled` như trước: model cần phân biệt "đã hỏi, người bệnh xác nhận KHÔNG có"
    (`"false"`) với "chưa hỏi tới" (`"unknown"`). Lọc bỏ field chưa điền làm hai trạng thái này biến
    mất y như nhau, và làm số khoá của JSON đổi theo từng phiên - model không biết field vắng mặt là
    do chưa hỏi hay do không thuộc protocol này.

    Khoá là FIELD KEY, KHÔNG phải `FieldSpec.label`: nhãn tiếng Việt là để hiển thị cho điều dưỡng,
    sửa chữ trong checklist sẽ làm hỏng feature phía model.

    Giá trị giữ nguyên dạng đã chuẩn hoá của agent - `"true"`/`"false"`/`"unknown"` cho tri-state, mã
    enum (`alert`, `none_gt_6h`) cho enum, số cho `temp_c`/`fever_duration_days`. `_coerce_enum` +
    `FieldSpec.allowed_values` đã chặn giá trị tiếng Việt tự do từ trước khi vào `answers`.
    """
    values: dict[str, object] = {}
    for key in protocol.fields_by_key:
        value = answers.get(key)
        values[key] = value if _is_filled(value) else "unknown"
    return values


def _status_for(session: Session) -> CaseStatus:
    if session.state is SessionState.EMERGENCY:
        return CaseStatus.ESCALATED
    if session.state is SessionState.COLLECTING:
        return CaseStatus.COLLECTING_INFORMATION
    # AWAITING_CONFIRMATION (bệnh nhân chưa xác nhận phiếu) và CONFIRMED (đã xác nhận) đều là "chờ
    # điều dưỡng duyệt" dưới góc nhìn case - việc bệnh nhân xác nhận phiếu KHÔNG phải một bước duyệt.
    return CaseStatus.NEEDS_NURSE_REVIEW


def _red_flags(protocol: SymptomProtocol, session: Session) -> list[RedFlagFinding]:
    return [
        RedFlagFinding(code=code, label=protocol.reason_code_labels.get(code, code), matched_fields=[])
        for code in session.reason_codes
    ]


def _chief_complaint(protocol: SymptomProtocol, answers: dict[str, object]) -> str:
    """Than phiền chính, ƯU TIÊN lời người bệnh tự nói. Chỉ rơi về nhãn mặc định của protocol khi
    người bệnh chưa mô tả - không bao giờ suy ra than phiền từ tên protocol."""
    if protocol.chief_complaint_field:
        stated = answers.get(protocol.chief_complaint_field)
        if _is_filled(stated):
            return str(stated)
    severity = answers.get(protocol.severity_field) if protocol.severity_field else None
    if protocol.default_chief_complaint and _is_filled(severity) and protocol.severity_field == "temp_c":
        return f"{protocol.default_chief_complaint} {severity}°C"
    return protocol.default_chief_complaint or "Chưa rõ triệu chứng chính"


def _summary_fields(protocol: SymptomProtocol, answers: dict[str, object]) -> list[SummaryField]:
    rows = []
    for key in _summary_keys(protocol):
        value = answers.get(key)
        filled = _is_filled(value)
        rows.append(SummaryField(label=protocol.fields_by_key[key].label, value=value if filled else None, is_missing=not filled))
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


def _triage_proposal(protocol: SymptomProtocol, session: Session) -> TriageProposal | None:
    """CHỈ sinh đề xuất khi rule engine đã chốt (`triage_level`). Trong lúc còn đang hỏi, không có
    đề xuất nào cả - không được đoán trước rồi hiển thị cho điều dưỡng."""
    if not session.triage_level:
        return None
    return TriageProposal(
        priority=_PRIORITY_BY_LEVEL.get(session.triage_level, TriagePriority.MANUAL_REVIEW),
        protocol_id=protocol.name,
        reason=", ".join(session.triggered_rules) or session.stop_reason or "",
        confidence=0.0,
        requires_manual_review=True,
        detect_source=f"symptom_intake_agent/{protocol.name} (LLM extraction theo cụm)",
        grounding_source=f"rule catalog của protocol {protocol.name} (rule engine thuần, không LLM)",
    )


def _summary(protocol: SymptomProtocol, session: Session, answers: dict[str, object]) -> HandoffSummary:
    onset = answers.get(protocol.onset_field) if protocol.onset_field else None
    severity = answers.get(protocol.severity_field) if protocol.severity_field else None
    return HandoffSummary(
        chief_complaint=_chief_complaint(protocol, answers),
        onset=str(onset) if _is_filled(onset) else None,
        severity=severity if _is_filled(severity) else None,
        associated_symptoms=[
            protocol.fields_by_key[key].label
            for key, value in answers.items()
            if key in protocol.fields_by_key and value == "true"
        ],
        missing_information=_missing_fields(protocol, answers),
        red_flags=_red_flags(protocol, session),
        proposed_priority=_PRIORITY_BY_LEVEL.get(session.triage_level or "", None),
        protocol_reason=", ".join(session.triggered_rules),
        detect_source=f"symptom_intake_agent/{protocol.name}",
        grounding_source=f"rule catalog của protocol {protocol.name}",
    )


def to_triage_case(session: Session, *, patient_id: int | None, previous: TriageCase | None = None) -> TriageCase:
    """Dựng lại `TriageCase` từ trạng thái HIỆN TẠI của phiên agent.

    `previous` chỉ dùng để giữ lại phần do ĐIỀU DƯỠNG ghi (`nurse_feedback`, `reviewed_by_*`) và mốc
    `created_at` - agent không biết gì về những thứ đó, dựng lại từ đầu mỗi lượt sẽ xoá mất."""
    protocol = registry.protocol_for(session.protocol_name)
    answers = dict(session.answers)
    status = _status_for(session)
    missing = _missing_fields(protocol, answers)
    is_collecting = status is CaseStatus.COLLECTING_INFORMATION

    structured_data = StructuredSymptomData(
        symptom_group=protocol.name,
        fields=_symptom_field_values(protocol, answers),
        missing_fields=missing,
        confidence=0.0,
        source=f"symptom_intake_agent/{protocol.name}",
    )
    validation = ValidationResult(
        is_valid=not is_collecting,
        missing_fields=missing,
        contradictions=[],
        low_confidence=not session.llm_used_last_turn,
        follow_up_questions=[session.last_question] if session.last_question else [],
    )
    summary = _summary(protocol, session, answers)
    proposal = _triage_proposal(protocol, session)

    return TriageCase(
        case_id=session.session_id,
        conversation=_conversation(session),
        structured_data=structured_data,
        validation=validation,
        red_flags=_red_flags(protocol, session),
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
            else protocol.emergency_message
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
        summary_fields=_summary_fields(protocol, answers),
    )
