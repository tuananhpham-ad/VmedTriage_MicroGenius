"""Duyệt HITL — nguồn sự thật DUY NHẤT cho mọi quyết định của điều dưỡng.

Trước đây có HAI đường duyệt song song và chúng ghi vào hai chỗ khác nhau:

- `hitl_review` (đường SPA gọi) sửa `TriageCase.status`, KHÔNG ghi audit;
- `case_approval` (đường đúng đặc tả Feature #2) ghi `ApprovalStatusRecord` + `AuditLogEntry`,
  nhưng SPA không gọi.

Hệ quả đo được: một case tạo bởi `/chat` rồi duyệt bằng `/approve` thì `approval_store` có bản ghi
còn `TriageCase.status` đứng yên, và ngược lại. Không có cách nào nhìn vào một case mà biết chắc nó
đã được duyệt hay chưa - trong một hệ mà toàn bộ ràng buộc an toàn dựa trên đúng câu hỏi đó.

Giờ chỉ còn một đường: mọi hành động đi qua `review()`, và `review()` ghi CẢ HAI - trạng thái case
lẫn dấu vết audit. `case_approval.py` cùng router `/queue` đã bị gỡ.

Ba thứ được giữ lại nguyên vẹn từ `case_approval` vì chúng là yêu cầu đặc tả, không phải chi tiết
cài đặt:

1. `ApprovalStatusRecord.final_priority` - cổng chặn của `GET /cases/{id}/result`. Bệnh nhân không
   thấy nội dung xử trí cho tới khi trường này có giá trị.
2. `AuditLogEntry` cho MỌI hành động, kèm `old_value`/`new_value` để truy được ai đổi mức nào.
3. `reason_code` khi từ chối. Chỉ `ai_incorrect` được tính vào thống kê độ chính xác AI-vs-điều
   dưỡng; `already_handled_offline` và `other` bị loại khỏi phép đo NGAY TỪ NGUỒN, nên phải ghi mã
   chứ không ghi một chuỗi ghi chú tự do.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.models.schemas import (
    ActorRole,
    CaseStatus,
    ConversationMessage,
    HITLAction,
    NurseFieldEdit,
    NurseFieldEditRequest,
    NurseReviewRequest,
    NurseReviewResponse,
    TriageCase,
    TriagePriority,
)
from src.services.stores.approval_store import ApprovalStatusRecord, AuditLogEntry, approval_store
from src.services.stores.case_store import case_store

# Hành động không chốt mức ưu tiên nên KHÔNG sinh `ApprovalStatusRecord`: hỏi thêm là đưa case về
# trạng thái đang thu thập, từ chối là dừng hẳn - cả hai đều không phải "đã duyệt kết quả".
_ACTIONS_THAT_SETTLE_PRIORITY = frozenset({HITLAction.APPROVE, HITLAction.EDIT})

RED_FLAG_PREFIX = "red_flags."
"""Tiền tố đường dẫn của một red flag trong `NurseFieldEdit.field` (`red_flags.RF-07`)."""

_FALSY_VALUES = (None, False, "", "false", "False", 0, "no", "không")
"""Giá trị đọc là "hạ cờ này xuống". Rộng có chủ đích: client gửi `false`, `"false"` hay `null` đều
là cùng một ý định, và bỏ sót một dạng ở đây nghĩa là bỏ qua đúng cái ma sát cố ý của §4.4 mục 3."""


def _is_lowering(value: object) -> bool:
    return any(value is item or value == item for item in _FALSY_VALUES)


class HumanReviewService:
    def review(
        self,
        case_id: str,
        request: NurseReviewRequest,
        *,
        nurse_id: int | None = None,
        nurse_name: str | None = None,
    ) -> NurseReviewResponse:
        triage_case = case_store.get(case_id)
        if not triage_case:
            raise ValueError("Case not found.")

        priority_before = self._current_priority(triage_case)
        # Sửa trường chạy TRƯỚC hành động: hạ một red flag mà thiếu lý do phải làm hỏng cả lời gọi,
        # không được để hành động `approve` đi qua rồi mới báo lỗi phần sửa.
        field_edits = self._apply_field_edits(triage_case, request, nurse_id)

        match request.action:
            case HITLAction.APPROVE:
                self._approve(triage_case, request)
            case HITLAction.EDIT:
                self._edit(triage_case, request)
            case HITLAction.REJECT:
                triage_case.status = CaseStatus.REJECTED
                triage_case.patient_visible_response = None
            case HITLAction.ASK_MORE:
                self._ask_more(triage_case, request)

        if nurse_id is not None:
            triage_case.reviewed_by_id = nurse_id
            triage_case.reviewed_by_name = nurse_name
            triage_case.reviewed_at = datetime.now(timezone.utc)
            # Ghi chú nội bộ không được lộ sang lịch sử bệnh nhân. Chỉ phản hồi
            # đã được gửi cho bệnh nhân mới được dùng như feedback hiển thị.
            triage_case.nurse_feedback = triage_case.patient_visible_response

        case_store.save(triage_case)
        self._record(triage_case, request, nurse_id, priority_before)
        self._record_field_edits(triage_case, field_edits, nurse_id)
        return NurseReviewResponse(
            case_id=triage_case.case_id,
            status=triage_case.status,
            patient_visible_response=triage_case.patient_visible_response,
        )

    # --- overlay sửa trường của điều dưỡng -----------------------------------------------------

    def _apply_field_edits(
        self, triage_case: TriageCase, request: NurseReviewRequest, nurse_id: int | None,
    ) -> list[NurseFieldEdit]:
        """Ghi bản sửa của điều dưỡng vào lớp OVERLAY - KHÔNG ghi đè bản do hệ thống sinh (§4.4).

        Điều dưỡng là người có thẩm quyền lâm sàng cao nhất trong luồng này, nên họ sửa được MỌI
        trường của phiếu, red flag bao gồm. Đừng nhầm việc này với `Session.escalation_lock`: khoá
        đó chặn MODEL tự hạ escalation TRONG phiên và không được nới: nó nằm ở
        `symptom_protocol/session.py`, và đường duyệt này không hề chạm tới `Session` - nó chỉ đọc
        `TriageCase` trong `case_store`. Hai khái niệm bị gộp làm một trước đây; tách chúng ra chính
        là nội dung của §4.4.

        Một ràng buộc CÓ ma sát cố ý: hạ một red flag phải kèm lý do. Đó là loại ma sát duy nhất
        được giữ trong toàn mục này."""
        if not request.field_edits:
            return []
        actor = str(nurse_id) if nurse_id is not None else "unknown"
        applied: list[NurseFieldEdit] = []
        for edit in request.field_edits:
            if edit.field.startswith(RED_FLAG_PREFIX) and _is_lowering(edit.value) and not edit.reason.strip():
                raise ValueError(
                    "Hạ một dấu hiệu nguy hiểm phải kèm lý do - vui lòng ghi rõ căn cứ lâm sàng."
                )
            applied.append(
                NurseFieldEdit(
                    field=edit.field,
                    generated_value=self._generated_value(triage_case, edit),
                    current_value=edit.value,
                    edited_by=actor,
                    reason=edit.reason.strip(),
                    # Đã gửi cảnh báo cho bệnh nhân rồi thì lần sửa này KHÔNG thu hồi được nó.
                    notice_already_sent=triage_case.emergency_notice_sent,
                )
            )
        triage_case.nurse_field_edits.extend(applied)
        return applied

    def _generated_value(self, triage_case: TriageCase, edit: NurseFieldEditRequest) -> object | None:
        """Giá trị GỐC do hệ thống sinh, chốt ở lần sửa đầu tiên của trường đó.

        Sửa lần thứ hai KHÔNG được lấy giá trị điều dưỡng đặt ở lần đầu làm `generated_value` - làm
        thế thì sau hai lần sửa, phiếu đọc ra như thể AI vốn đã nói điều điều dưỡng vừa viết. Cùng
        lý do `_current_priority` phải đọc `approval_store` trước."""
        for existing in triage_case.nurse_field_edits:
            if existing.field == edit.field:
                return existing.generated_value
        return self._read_generated(triage_case, edit.field)

    def _read_generated(self, triage_case: TriageCase, path: str) -> object | None:
        """Đọc giá trị hệ thống sinh theo đường dẫn của `NurseFieldEdit.field`.

        Chỉ hiểu hai không gian tên đang có ý nghĩa lâm sàng (`red_flags.<mã>`, `summary.<trường>`).
        Đường dẫn lạ trả `None` chứ không ném lỗi: overlay vẫn phải ghi được bản sửa và vẫn phải ghi
        audit - mất một `generated_value` còn hơn mất cả bản ghi điều dưỡng vừa tạo."""
        if path.startswith(RED_FLAG_PREFIX):
            code = path[len(RED_FLAG_PREFIX):]
            return any(flag.code == code for flag in triage_case.red_flags)
        if path.startswith("summary.") and triage_case.summary is not None:
            return getattr(triage_case.summary, path[len("summary."):], None)
        return None

    def _record_field_edits(
        self, triage_case: TriageCase, edits: list[NurseFieldEdit], nurse_id: int | None,
    ) -> None:
        """Mỗi trường sửa là MỘT dòng audit riêng, kèm `old_value`/`new_value`.

        Không gộp vào dòng audit của hành động duyệt: câu hỏi cần trả lời được sau sự cố là "ai đã
        bỏ dấu hiệu nào đi vì lý do gì", mà một dòng ghi cả năm trường thì không trả lời được."""
        actor = str(nurse_id) if nurse_id is not None else "unknown"
        for edit in edits:
            approval_store.log(
                AuditLogEntry(
                    case_id=triage_case.case_id,
                    actor=actor,
                    action=f"edit_field:{edit.field}",
                    old_value=str(edit.generated_value),
                    new_value=str(edit.current_value),
                    reason=edit.reason or None,
                )
            )

    # --- dấu vết duyệt -------------------------------------------------------------------------

    def _current_priority(self, triage_case: TriageCase) -> str:
        """Mức ưu tiên ĐANG có hiệu lực: quyết định đã duyệt trước đó, nếu chưa thì đề xuất của AI.

        Phải đọc `approval_store` trước chứ không đọc thẳng `triage_proposal`: khi điều dưỡng sửa
        mức hai lần liên tiếp, `old_value` của lần thứ hai là mức điều dưỡng đặt ở lần đầu, không
        phải mức AI đề xuất ban đầu."""
        existing = approval_store.get(triage_case.case_id)
        if existing is not None:
            return existing.final_priority
        if triage_case.triage_proposal:
            return triage_case.triage_proposal.priority.value
        return TriagePriority.MANUAL_REVIEW.value

    def _record(
        self,
        triage_case: TriageCase,
        request: NurseReviewRequest,
        nurse_id: int | None,
        priority_before: str,
    ) -> None:
        actor = str(nurse_id) if nurse_id is not None else "unknown"
        priority_after = self._settled_priority(triage_case, request, priority_before)

        if request.action in _ACTIONS_THAT_SETTLE_PRIORITY:
            approval_store.upsert(
                ApprovalStatusRecord(
                    case_id=triage_case.case_id,
                    approved_by=nurse_id or 0,
                    approved_at=datetime.now(timezone.utc),
                    final_priority=priority_after,
                )
            )

        approval_store.log(
            AuditLogEntry(
                case_id=triage_case.case_id,
                actor=actor,
                action=request.action.value,
                old_value=priority_before,
                new_value=priority_after,
                reason=self._reason_for(request),
            )
        )

    def _settled_priority(
        self, triage_case: TriageCase, request: NurseReviewRequest, priority_before: str,
    ) -> str:
        if request.edited_priority is not None:
            return request.edited_priority.value
        if triage_case.triage_proposal:
            return triage_case.triage_proposal.priority.value
        return priority_before

    def _reason_for(self, request: NurseReviewRequest) -> str | None:
        """Lý do ghi vào audit. Từ chối thì ghi MÃ (đầu vào của thống kê), còn lại ghi ghi chú tự do."""
        if request.action is HITLAction.REJECT and request.reject_reason_code is not None:
            return request.reject_reason_code.value
        if request.action is HITLAction.ASK_MORE:
            return request.ask_more_question
        return request.nurse_notes

    # --- hành động -----------------------------------------------------------------------------

    def _approve(self, triage_case: TriageCase, request: NurseReviewRequest) -> None:
        if not request.approved_response:
            raise ValueError("approved_response is required when approving a case.")

        triage_case.status = CaseStatus.APPROVED
        triage_case.patient_visible_response = request.approved_response
        triage_case.conversation.append(
            ConversationMessage(role=ActorRole.NURSE, content=request.approved_response)
        )

    def _edit(self, triage_case: TriageCase, request: NurseReviewRequest) -> None:
        if not request.approved_response:
            raise ValueError("approved_response is required when editing a case.")

        if request.edited_priority and triage_case.triage_proposal:
            triage_case.triage_proposal.priority = request.edited_priority

        triage_case.status = CaseStatus.APPROVED
        triage_case.patient_visible_response = request.approved_response
        triage_case.conversation.append(
            ConversationMessage(role=ActorRole.NURSE, content=request.approved_response)
        )

    def _ask_more(self, triage_case: TriageCase, request: NurseReviewRequest) -> None:
        if not request.ask_more_question:
            raise ValueError("ask_more_question is required when asking for more information.")

        triage_case.status = CaseStatus.NEEDS_MORE_INFO
        triage_case.patient_visible_response = request.ask_more_question
        triage_case.conversation.append(
            ConversationMessage(role=ActorRole.NURSE, content=request.ask_more_question)
        )


human_review_service = HumanReviewService()
