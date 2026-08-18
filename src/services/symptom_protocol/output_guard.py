"""L5 `output_guard` — kiểm câu do model viết TRƯỚC khi gửi cho người bệnh. KHÔNG model.

Đây là tầng an toàn cuối. Renderer bị giới hạn bởi `ResponsePlan`, nhưng "bị giới hạn bởi prompt"
không phải một bảo đảm - prompt là lời đề nghị, guard mới là ràng buộc. Fail thì rơi về
`script_hint` tất định: câu khô hơn nhưng chắc chắn nằm trong checklist đã duyệt.

Năm kiểm tra theo §6.5, và một giới hạn được ghi rõ thay vì giấu đi:

1. số dấu hỏi nằm trong hạn mức của plan;
2. không nêu tên bệnh / hướng điều trị;
3. không hỏi lại field ĐÃ BIẾT ngoài `missing_fields`;
4. markdown an toàn với streaming;
5. không rỗng.

**Giới hạn đã biết:** kiểm tra 3 chỉ bắt được trường hợp câu hỏi NHẮC ĐÚNG nhãn field. Không có
cách tất định nào để khẳng định "câu này không hỏi gì ngoài `next_cluster`" chỉ bằng văn bản - muốn
chắc thì phải kiểm ở tầng dữ liệu (lượt sau field ngoài cụm có bị điền không), và đó là việc của
eval chứ không phải của guard. Ghi ra đây để không ai đọc guard này rồi tưởng nó bảo đảm điều đó.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.services.symptom_protocol import stage_machine
from src.services.symptom_protocol.dialogue import ResponsePlan
from src.services.symptom_protocol.models import QuestionCluster
from src.services.symptom_protocol.protocol import SymptomProtocol

VIOLATION_EMPTY = "empty"
VIOLATION_TOO_MANY_QUESTIONS = "too_many_questions"
VIOLATION_NOT_A_QUESTION = "not_a_question"
VIOLATION_DIAGNOSIS = "diagnosis_or_treatment"
VIOLATION_ASKS_KNOWN_FIELD = "asks_known_field"
VIOLATION_UNSAFE_MARKDOWN = "unsafe_markdown"


# Tên bệnh: hệ thống KHÔNG chẩn đoán (CLAUDE.md nguyên tắc 2), nên mọi tên bệnh trong câu hỏi đều
# đáng ngờ. Ngoại lệ được xử lý bằng CƠ CHẾ chứ không bằng danh sách: tên bệnh có trong chính
# `script_hint` của cụm đang hỏi thì được phép (fever Q4-07 hỏi "xung quanh có ai bị SXHD/cúm/sởi/
# tay chân miệng không" - đó là bối cảnh phơi nhiễm, không phải chẩn đoán).
# CÔNG KHAI (không `_`): `reducer.certainty_of` dùng lại đúng danh sách này để nhận ra một lời phủ
# định là phủ định TÊN BỆNH chứ không phải phủ định triệu chứng. Hai bản sao lệch nhau nghĩa là một
# tên bệnh chặn được ở đầu ra nhưng vẫn xoá được hồ sơ ở đầu vào.
DISEASE_NAMES: tuple[str, ...] = (
    "sốt xuất huyết", "sxhd", "cúm", "covid", "viêm phổi", "viêm màng não", "sởi",
    "tay chân miệng", "thương hàn", "sốt rét", "đột quỵ", "nhồi máu", "nhiễm trùng huyết",
    "viêm ruột thừa", "viêm dạ dày", "hen suyễn", "lao phổi", "viêm gan",
)

# Hướng điều trị/kê đơn: KHÔNG có ngoại lệ theo `script_hint`. Checklist được phép HỎI người bệnh
# đang dùng thuốc gì ("có đang dùng kháng sinh không"), nhưng không bao giờ được KHUYÊN dùng thuốc.
# Vì thế mẫu ở đây là mẫu MỆNH LỆNH/KHUYÊN, không phải tên thuốc.
_TREATMENT_ADVICE: tuple[str, ...] = (
    "bạn nên uống", "nên uống thuốc", "hãy uống", "bạn hãy dùng", "nên dùng thuốc", "kê đơn",
    "liều dùng", "bạn bị bệnh", "có thể bạn bị", "tôi nghĩ bạn bị", "chẩn đoán là",
    "khả năng cao là", "đây là dấu hiệu của bệnh",
)

# Markdown an toàn khi stream: output đi qua `/chat/stream` nên phải hợp lệ THEO TỪNG MẨU. Mọi cú
# pháp cần một ký tự ĐÓNG ở cuối đều hỏng khi người bệnh mới nhận được nửa câu - đậm/nghiêng/code
# hiện ra dưới dạng `**` trần. Gạch đầu dòng và xuống dòng thì an toàn vì chúng đóng bằng newline.
_UNSAFE_MARKDOWN = re.compile(r"\*\*|__|```|~~|\|\s*-{3,}|^#{1,6}\s", re.MULTILINE)


@dataclass(slots=True)
class GuardResult:
    ok: bool
    violations: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ok


_REJECTIONS: dict[str, int] = {}


def rejection_counts() -> dict[str, int]:
    """Đếm theo loại vi phạm - metric "tỉ lệ bị `output_guard` chặn" của §12.

    Guard chặn nhiều là tín hiệu prompt sai, KHÔNG phải tín hiệu guard tốt: mỗi lần chặn là một lượt
    người bệnh nhận câu khô hơn."""
    return dict(sorted(_REJECTIONS.items()))


def reset_rejection_counts() -> None:
    _REJECTIONS.clear()


def check(
    text: str,
    *,
    plan: ResponsePlan,
    protocol: SymptomProtocol,
    cluster: QuestionCluster,
    answers: dict[str, object],
) -> GuardResult:
    """Câu này có được phép gửi cho người bệnh không."""
    violations: list[str] = []
    stripped = (text or "").strip()

    if not stripped:
        violations.append(VIOLATION_EMPTY)
        return _record(GuardResult(ok=False, violations=violations))

    question_marks = stripped.count("?")
    if question_marks == 0:
        violations.append(VIOLATION_NOT_A_QUESTION)
    elif question_marks > max(plan.max_questions, _MIN_QUESTION_ALLOWANCE):
        violations.append(VIOLATION_TOO_MANY_QUESTIONS)

    lowered = stripped.casefold()
    allowed = (cluster.script_hint or "").casefold()
    if any(name in lowered and name not in allowed for name in DISEASE_NAMES):
        violations.append(VIOLATION_DIAGNOSIS)
    if any(phrase in lowered for phrase in _TREATMENT_ADVICE):
        violations.append(VIOLATION_DIAGNOSIS)

    if _asks_a_known_field(protocol, plan, answers, lowered):
        violations.append(VIOLATION_ASKS_KNOWN_FIELD)

    if _UNSAFE_MARKDOWN.search(stripped):
        violations.append(VIOLATION_UNSAFE_MARKDOWN)

    return _record(GuardResult(ok=not violations, violations=violations))


_MIN_QUESTION_ALLOWANCE = 2
"""§6.5 nói "đúng 1-2 dấu hỏi", nên trần không bao giờ thấp hơn 2 kể cả với plan một ý.

Đo trên transcript thật: một câu hỏi tiếng Việt tự nhiên rất hay có dấu hỏi thứ hai ở vế xác nhận
("...phải không ạ?"). Ép trần về 1 làm guard chặn những câu hoàn toàn hợp lệ, và mỗi lần chặn là một
lượt người bệnh nhận `script_hint` khô - tức là mất đúng thứ P3 vừa làm ra."""

_DISTINCTIVE_LABEL_WORDS = 3
"""Nhãn phải có ít nhất chừng này từ mới được dùng để dò.

Ngưỡng 2 đã thử và BỎ: nhãn hai từ như "Loại sốt" xuất hiện tự nhiên trong câu hỏi hợp lệ, đo được
tỉ lệ chặn nhầm đáng kể trên transcript thật với `deepseek-chat`. Kiểm tra này vốn là lưới an toàn
PHỤ - lưới chính là `missing_fields` trong prompt và việc reducer không cho `unknown` ghi đè giá trị
đã có - nên nó phải nghiêng về BỎ SÓT hơn là chặn nhầm."""


def _asks_a_known_field(
    protocol: SymptomProtocol,
    plan: ResponsePlan,
    answers: dict[str, object],
    lowered: str,
) -> bool:
    """Câu hỏi có nhắc tới nhãn của một field ĐÃ có căn cứ và KHÔNG nằm trong `missing_fields` không."""
    for key, value in answers.items():
        if key in plan.missing_fields or key not in protocol.fields_by_key:
            continue
        if not stage_machine.is_filled(value):
            continue
        label = protocol.fields_by_key[key].label.casefold()
        if len(label.split()) < _DISTINCTIVE_LABEL_WORDS:
            continue
        if label in lowered:
            return True
    return False


def _record(result: GuardResult) -> GuardResult:
    for violation in result.violations:
        _REJECTIONS[violation] = _REJECTIONS.get(violation, 0) + 1
    return result
