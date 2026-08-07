from __future__ import annotations

import re

from src.models.schemas import ActorRole, ConversationQualityFlag, TriageCase

# Heuristic rule-based, KHÔNG phải LLM: mục tiêu là rẻ, nhanh, chạy mỗi turn mà không cần gọi model.
# Đây chỉ là GỢI Ý, không có quyền chặn tuyệt đối - xem ghi chú an toàn trong TriagePipeline/case_approval.
MIN_MESSAGE_LENGTH = 3
MAX_ASK_ROUNDS_BEFORE_LOW_QUALITY = 4  # ~2x ALLOWED_ASKS trong case_flow.py, đủ dư địa cho hội thoại thật
_WORD_CHAR_RE = re.compile(r"[^\W\d_]", re.UNICODE)


class QualityGuard:
    """Đánh giá chất lượng hội thoại để quyết định có nên suppress khỏi hàng đợi điều dưỡng hay không.

    Nguyên tắc an toàn (đã thống nhất trong thiết kế): kết quả của guard này CHỈ được đọc bởi
    case_approval.list_queue() và LUÔN bị bỏ qua khi case có red-flag - guard này không được gọi/kiểm
    tra red-flag, và không tự ý thay đổi CaseStatus. Nó chỉ gắn nhãn quan sát được, quyết định
    suppress nằm ở một chỗ duy nhất (list_queue) để dễ audit và tránh 2 nơi tranh nhau quyết định.
    """

    def assess(self, triage_case: TriageCase) -> ConversationQualityFlag:
        patient_messages = [
            message.content for message in triage_case.conversation if message.role == ActorRole.PATIENT
        ]
        if not patient_messages:
            return ConversationQualityFlag.NORMAL

        if self._looks_like_repeated_nonsense(patient_messages):
            return ConversationQualityFlag.LOW_QUALITY

        if self._too_many_unanswered_rounds(triage_case):
            return ConversationQualityFlag.LOW_QUALITY

        return ConversationQualityFlag.NORMAL

    def _looks_like_repeated_nonsense(self, patient_messages: list[str]) -> bool:
        latest = patient_messages[-1].strip()
        if len(latest) < MIN_MESSAGE_LENGTH:
            return True

        letters = _WORD_CHAR_RE.findall(latest)
        if not letters:
            return True  # toàn ký tự đặc biệt/số, không có chữ cái nào

        # Cùng một câu lặp lại nhiều lần liên tiếp thường là spam/troll, không phải mô tả triệu chứng mới.
        if len(patient_messages) >= 3 and len(set(message.strip().casefold() for message in patient_messages[-3:])) == 1:
            return True

        return False

    def _too_many_unanswered_rounds(self, triage_case: TriageCase) -> bool:
        # Nếu đã hỏi đi hỏi lại rất nhiều lần mà vẫn chưa đủ checklist, nhiều khả năng bệnh nhân
        # không hợp tác/không trả lời đúng trọng tâm câu hỏi.
        if not triage_case.field_ask_counts:
            return False
        return max(triage_case.field_ask_counts.values()) > MAX_ASK_ROUNDS_BEFORE_LOW_QUALITY


quality_guard = QualityGuard()
