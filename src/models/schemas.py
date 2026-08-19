from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


# Vai trò của người/hệ thống gửi một tin nhắn trong hội thoại triage.
class ActorRole(str, Enum):
    PATIENT = "patient"
    NURSE = "nurse"
    SYSTEM = "system"


# Trạng thái vòng đời của một case, từ lúc bắt đầu thu thập triệu chứng đến khi điều dưỡng xử lý xong.
class CaseStatus(str, Enum):
    COLLECTING_INFORMATION = "collecting_information"
    NEEDS_NURSE_REVIEW = "needs_nurse_review"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    # Điều dưỡng cần thêm thông tin trước khi quyết định (action ask_more) - quay lại hội thoại,
    # khác COLLECTING_INFORMATION ban đầu vì câu hỏi lần này do điều dưỡng chỉ định, không phải checklist.
    NEEDS_MORE_INFO = "needs_more_info"
    # Điều dưỡng từ chối xử lý vì lý do KHÔNG liên quan đến độ chính xác AI (vd: bệnh nhân đã được
    # xử lý offline). Tách khỏi REJECTED (vốn không phân biệt lý do) để không lẫn vào thống kê accuracy.
    WITHDRAWN = "withdrawn"


# Hành động điều dưỡng có thể thực hiện khi duyệt một case (human-in-the-loop).
# Escalate không phải hành động riêng: đổi mức ưu tiên lên Emergency chỉ là một trường hợp của edit.
class HITLAction(str, Enum):
    APPROVE = "approve"
    EDIT = "edit"
    REJECT = "reject"
    ASK_MORE = "ask_more"


# Mức ưu tiên hiển thị trong hàng đợi điều dưỡng (khác với TriagePriority lâm sàng).
class QueuePriority(str, Enum):
    STANDARD = "standard"
    HIGH = "high"


# Lý do điều dưỡng reject một case (Feature #2 mở rộng). BẮT BUỘC chọn để tách tín hiệu: chỉ
# AI_INCORRECT mới được tính vào thống kê độ chính xác AI-điều dưỡng, hai lý do còn lại KHÔNG phải
# tín hiệu AI đúng/sai nên không được lẫn vào accuracy scoring.
class RejectReasonCode(str, Enum):
    ALREADY_HANDLED_OFFLINE = "already_handled_offline"
    AI_INCORRECT = "ai_incorrect"
    OTHER = "other"


# Nhãn chất lượng hội thoại do quality guard gán mỗi turn (không có quyền chặn tuyệt đối - xem
# quality_guard - ĐÃ GỠ). low_quality chỉ ảnh hưởng việc case có bị suppress khỏi hàng đợi
# điều dưỡng hay không, KHÔNG BAO GIỜ chặn/ghi đè red-flag escalation.
class ConversationQualityFlag(str, Enum):
    NORMAL = "normal"
    LOW_QUALITY = "low_quality"


# Mức độ ưu tiên xử trí lâm sàng do triage engine đề xuất.
class TriagePriority(str, Enum):
    EMERGENCY = "Emergency"
    URGENT = "Urgent"
    ROUTINE = "Routine"
    SELF_CARE = "Self-care"
    MANUAL_REVIEW = "Manual review"


# Một tin nhắn trong lịch sử hội thoại của case (từ bệnh nhân, điều dưỡng hoặc hệ thống).
class ConversationMessage(BaseModel):
    role: ActorRole
    content: str = Field(..., min_length=1)


# Dữ liệu triệu chứng đã được semantic mapper trích xuất có cấu trúc từ tin nhắn tự do.
class StructuredSymptomData(BaseModel):
    symptom_group: str = "general"
    fields: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: str = "semantic_mapper"


# Một vấn đề cụ thể (mâu thuẫn, thiếu dữ liệu...) phát hiện được khi validate structured data.
class ValidationIssue(BaseModel):
    code: str
    message: str
    field: str | None = None


# Kết quả tổng hợp của bước checklist validation, gồm các field còn thiếu và câu hỏi cần hỏi thêm.
class ValidationResult(BaseModel):
    is_valid: bool
    missing_fields: list[str] = Field(default_factory=list)
    contradictions: list[ValidationIssue] = Field(default_factory=list)
    low_confidence: bool = False
    follow_up_questions: list[str] = Field(default_factory=list)


# Một dấu hiệu nguy hiểm (red flag) được red-flag layer phát hiện, dùng để ưu tiên đẩy case lên khẩn cấp.
class RedFlagFinding(BaseModel):
    code: str
    label: str
    matched_fields: list[str] = Field(default_factory=list)


# Đề xuất mức ưu tiên xử trí do triage engine sinh ra, luôn cần điều dưỡng duyệt trước khi có hiệu lực.
class TriageProposal(BaseModel):
    priority: TriagePriority
    protocol_id: str | None = None
    reason: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    requires_manual_review: bool = True
    detect_source: str = Field(
        default="",
        description="Nguồn dùng để phát hiện/gợi ý triệu chứng (mô phỏng nội bộ, KHÔNG dùng để kết luận mức độ ưu tiên).",
    )
    grounding_source: str = Field(
        default="",
        description="Nguồn dùng để 'ground' kết luận mức độ ưu tiên (mô phỏng nội bộ theo Bộ Y tế VN/WHO).",
    )


# Một dòng dữ liệu trong phiếu tóm tắt hiển thị cho điều dưỡng (nhãn + giá trị, đánh dấu nếu còn thiếu).
class SummaryField(BaseModel):
    label: str
    value: Any | None = None
    is_missing: bool = False


# Phiếu tóm tắt bàn giao cho điều dưỡng: gộp triệu chứng, red flag và đề xuất ưu tiên vào một khối duy nhất.
class HandoffSummary(BaseModel):
    """Phiếu bàn giao, schema **PHẲNG** (ADR-006). Việc nhóm thành 5 khối I/S/B/A/R xảy ra ở
    RENDERER (`isbar.py`), không ở đây - lồng schema lại thì `NurseQueueItem` và UI W-07 phải sửa
    theo mà không được gì thêm.

    Đây là `summary_json` của ADR-006. Bản văn xuôi (`summary_text`) đọc **cùng một snapshot** và
    nằm ở `HandoffSummary.narrative` - đó là điều kiện duy nhất khiến hai output không mâu thuẫn."""

    chief_complaint: str
    onset: str | None = None
    severity: str | int | None = None
    associated_symptoms: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    red_flags: list[RedFlagFinding] = Field(default_factory=list)
    proposed_priority: TriagePriority | None = None
    protocol_reason: str = ""
    detect_source: str = ""
    grounding_source: str = ""

    # --- ADR-006: 5 trường ISBAR còn thiếu ------------------------------------------------------
    age: str | None = None
    sex: str | None = None
    allergies: str | None = None
    """Đúng semantics 3 giá trị của reducer: `"true"` / `"false"` / `"unknown"`. KHÔNG thêm kiểu mới
    - "chưa ai hỏi về dị ứng" và "người bệnh nói không dị ứng" là hai dữ kiện khác nhau, và một
    `bool | None` gộp mất đúng distinction đó."""
    comorbidities: list[str] = Field(default_factory=list)
    """**Liệt kê TẤT CẢ** (ADR-006 mục 5). Template gợi ý lọc "bệnh có liên quan" - đó là giao một
    phán đoán lâm sàng cho LLM, và lọc sai thì điều dưỡng không có cách nào biết cái gì đã bị giấu."""
    current_medications: list[str] = Field(default_factory=list)

    # --- §4.2: ba nguồn cùng ghi vào một ô thì phải truy được ô đó đến từ đâu --------------------
    provisional_priority: TriagePriority | None = None
    """Mức do rule engine tính TRONG hội thoại. `proposed_priority` giữ nguyên nghĩa *đề xuất*
    (`docs/prd.md:65` FR-05); trường này là mức tạm thời để đối chiếu."""
    priority_source: str = ""
    """`"rule_engine"` | `"downstream"` | `"nurse_edited"`. Không có nó thì ba nguồn cùng ghi vào một
    ô và không ai truy được ô đó đến từ đâu."""

    # --- §4.7 + §7.2 mục 4: ba lý do dừng phải ra ba phiếu PHÂN BIỆT ĐƯỢC -----------------------
    is_complete: bool = True
    """`False` = phiên đóng vì người bệnh bỏ dở / không hợp tác, KHÔNG phải vì đã hỏi đủ. Điều dưỡng
    cần biết ca này thiếu thông tin vì lý do nào - `missing_information` một mình không nói được
    điều đó (một phiên hỏi đủ vẫn có thể còn field `unknown` vì người bệnh không biết)."""
    stop_reason: str = ""
    """Mã dừng ổn định của `stage_machine.StopReason`."""

    # --- ADR-006: khối [R], viết như ĐỀ XUẤT chứ không như việc đã làm --------------------------
    proposed_action: str = ""
    """Thay cho `AI Action` của template. *"AI Action: Khuyên bệnh nhân đến bệnh viện ngay"* đọc theo
    mặt chữ thì AI đã khuyên bệnh nhân TRƯỚC khi điều dưỡng duyệt - ngược `CLAUDE.md` nguyên tắc 1."""
    approval_status: str = "pending_nurse_review"
    narrative: str = ""
    """`summary_text` của ADR-006: văn xuôi do LLM viết lại, để lưu DB và làm memory. Rỗng khi chưa
    sinh (không gọi LLM) - phiếu vẫn đọc được đầy đủ bằng các trường có cấu trúc ở trên."""
    red_flag_agreement: dict[str, Any] = Field(default_factory=dict)
    """Bản đối chiếu ba nhánh red-flag (§4.1). **DỮ LIỆU, không phải quyết định** - không dòng code
    nào đọc nó để đổi `proposed_priority`. `model_only` là danh sách ứng viên mở rộng rule."""
    raw_conversation: list[str] = Field(default_factory=list)
    """Toàn văn câu trả lời của người bệnh (§4.3). Điều dưỡng đã có khối này trên UI; đưa vào JSON để
    bản xuất ra cũng có."""


# Một mục trong hàng đợi điều dưỡng, gộp mọi thông tin cần thiết để duyệt một case mà không cần tra lại nơi khác.
class NurseQueueItem(BaseModel):
    case_id: str
    queue_priority: QueuePriority
    status: CaseStatus
    summary: HandoffSummary
    structured_data: StructuredSymptomData
    validation: ValidationResult
    triage_proposal: TriageProposal | None = None


# Một lần điều dưỡng sửa MỘT trường của phiếu bàn giao (§4.4 `_guidance/what_to_do_next.md`).
class NurseFieldEdit(BaseModel):
    """Lớp OVERLAY - bản ghi do hệ thống sinh KHÔNG bao giờ bị ghi đè.

    Lý do không sửa thẳng vào `TriageCase.summary`/`red_flags`: nếu có sự cố, câu hỏi đầu tiên sẽ là
    "hệ thống có bắt được không, và ai đã bỏ nó đi". Ghi đè làm mất `generated_value` là mất luôn
    khả năng trả lời câu đó.

    `field` là ĐƯỜNG DẪN có tiền tố (`red_flags.RF-07`, `summary.onset`) chứ không phải tên trường
    trần: điều dưỡng sửa được cả trường của phiếu lẫn từng red flag, và hai không gian tên đó có mã
    trùng nhau được.
    """

    field: str
    generated_value: Any | None = None
    """Giá trị hệ thống sinh ra, chốt ở LẦN SỬA ĐẦU TIÊN và không đổi sau đó. Sửa hai lần liên tiếp
    thì `generated_value` vẫn là giá trị của AI, không phải giá trị điều dưỡng đặt ở lần đầu."""
    current_value: Any | None = None
    edited_by: str = ""
    edited_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reason: str = ""
    """BẮT BUỘC khi hạ một red flag. Đây là ma sát CỐ Ý: hạ một cảnh báo an toàn không được là một cú
    click."""
    notice_already_sent: bool = False
    """Ca đã hiển thị thông điệp cấp cứu TĨNH cho bệnh nhân trước khi lần sửa này xảy ra.

    §4.4 mục 4 - một việc không rút lại được: hạ cờ về sau chỉ đổi phiếu và luồng xử trí, KHÔNG xoá
    được cái người bệnh đã đọc. Ghi lại ở đây để UI nói rõ điều đó tại chỗ, thay vì để điều dưỡng
    tưởng mình vừa thu hồi một cảnh báo."""


# Một trường điều dưỡng muốn sửa, dạng client gửi lên. Không có `generated_value`/`edited_at`: hai
# trường đó do server điền, để client không thể khai lại "AI vốn nói thế này".
class NurseFieldEditRequest(BaseModel):
    field: str = Field(..., min_length=1, max_length=200)
    value: Any | None = None
    reason: str = Field(default="", max_length=1000)


# Trạng thái đầy đủ của một ca triage, là "nguồn sự thật" được lưu trong case_store xuyên suốt hội thoại nhiều lượt.
class TriageCase(BaseModel):
    case_id: str = Field(default_factory=lambda: str(uuid4()))
    conversation: list[ConversationMessage] = Field(default_factory=list)
    structured_data: StructuredSymptomData | None = None
    validation: ValidationResult | None = None
    red_flags: list[RedFlagFinding] = Field(default_factory=list)
    triage_proposal: TriageProposal | None = None
    summary: HandoffSummary | None = None
    queue_item: NurseQueueItem | None = None
    status: CaseStatus = CaseStatus.COLLECTING_INFORMATION
    patient_visible_response: str | None = None
    nurse_feedback: str | None = None
    reviewed_by_id: int | None = None
    reviewed_by_name: str | None = None
    reviewed_at: datetime | None = None
    patient_id: int | None = Field(default=None, description="Chủ sở hữu case (id bệnh nhân đã đăng nhập)")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    field_ask_counts: dict[str, int] = Field(default_factory=dict)
    next_message: str | None = Field(
        default=None, description="Câu hỏi/phản hồi tiếp theo của agent, null nếu đã đủ thông tin"
    )
    summary_ready: bool = False
    summary_fields: list[SummaryField] = Field(default_factory=list)
    nurse_field_edits: list[NurseFieldEdit] = Field(default_factory=list)
    """Lớp overlay của điều dưỡng (§4.4). Đọc phiếu ĐÚNG là: bản do hệ thống sinh, rồi áp overlay
    lên trên. Không có đường nào xoá bản gốc."""
    queued_at: datetime | None = None
    """Lúc ca vào hàng đợi điều dưỡng - mốc BẮT ĐẦU của đồng hồ SLA (ADR-007). Chỉ đặt MỘT LẦN."""
    first_opened_at: datetime | None = None
    """Lúc một điều dưỡng MỞ ca. Mốc DỪNG của đồng hồ SLA - không phải lúc duyệt xong: mở ca là lúc
    có người thật nhìn thấy nó, và đó mới là thứ SLA an toàn quan tâm."""
    emergency_notice_sent: bool = False
    """Thông điệp cấp cứu TĨNH đã được hiển thị cho bệnh nhân. Một chiều - đã bật thì không tắt, vì
    nó ghi lại một SỰ KIỆN đã xảy ra chứ không phải trạng thái hiện tại của ca."""
    graph_decision: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Kết luận cuối của agent quyết định trong src/graph_triage/ (LogReg + PhoBERT + evidence "
            "graph -> LLM). Ý kiến tham khảo THỨ HAI cho điều dưỡng. TUYỆT ĐỐI không được gán vào "
            "TriageProposal.priority hay RedFlagFinding - ProtocolTriageEngine/RedFlagSafetyLayer "
            "vẫn là nguồn quyết định mức ưu tiên duy nhất."
        ),
    )
    quality_flag: ConversationQualityFlag = Field(
        default=ConversationQualityFlag.NORMAL,
        description="Nhãn chất lượng hội thoại. HIỆN KHÔNG AI GÁN - `quality_guard` đã bị gỡ cùng luồng Gen 2 (2026-08-16). Giữ trường để dữ liệu cũ đọc lại được và để cơ chế suppress hàng đợi nối lại được mà không phải migrate.",
    )


# Request body của endpoint chat gốc: tin nhắn bệnh nhân + case_id nếu tiếp tục hội thoại đã có.
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000, description="Patient message")
    case_id: str | None = Field(default=None, description="Existing triage case id")


# Một bước trong pipeline trace, dùng để trả về cho client thấy pipeline đã chạy qua những giai đoạn nào.
class PipelineTraceStage(BaseModel):
    stage: str
    title: str
    output: dict[str, Any] = Field(default_factory=dict)


# Response trả về cho bệnh nhân sau mỗi lượt chat, kèm dữ liệu nội bộ (analysis, pipeline_trace) để debug/hiển thị nurse.
class ChatResponse(BaseModel):
    case_id: str
    response: str = Field(..., description="Patient-safe response")
    status: CaseStatus
    analysis: str = Field(default="", description="Internal pipeline summary")
    structured_data: StructuredSymptomData | None = None
    validation: ValidationResult | None = None
    red_flags: list[RedFlagFinding] = Field(default_factory=list)
    triage_proposal: TriageProposal | None = None
    summary: HandoffSummary | None = None
    pipeline_trace: list[PipelineTraceStage] = Field(default_factory=list)
    requires_human_approval: bool = True


# Request body khi điều dưỡng duyệt một case (approve/edit/reject/escalate/ask_more).
class NurseReviewRequest(BaseModel):
    action: HITLAction
    approved_response: str | None = None
    edited_priority: TriagePriority | None = None
    nurse_notes: str | None = None
    field_edits: list[NurseFieldEditRequest] = Field(default_factory=list)
    """Sửa trường của phiếu, KỂ CẢ red flag (§4.4). Đi kèm mọi hành động chứ không riêng `EDIT`:
    điều dưỡng sửa một trường rồi vẫn duyệt là luồng bình thường nhất."""
    ask_more_question: str | None = None
    # Chỉ dùng khi action=REJECT. Là MÃ chứ không phải ghi chú tự do vì nó là đầu vào của thống kê
    # độ chính xác AI-vs-điều dưỡng: chỉ `ai_incorrect` được tính, `already_handled_offline`/`other`
    # bị loại khỏi phép đo ngay từ nguồn. Không bắt buộc để không vỡ client cũ.
    reject_reason_code: RejectReasonCode | None = None


# Response trả về sau khi điều dưỡng duyệt case, xác nhận trạng thái mới và nội dung sẽ gửi cho bệnh nhân.
class NurseReviewResponse(BaseModel):
    case_id: str
    status: CaseStatus
    patient_visible_response: str | None = None
