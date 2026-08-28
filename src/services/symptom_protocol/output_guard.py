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


PREFIX_SAFE_TAIL = 32
"""Số ký tự CUỐI phải giữ lại chưa phát khi stream, để `check_prefix` luôn nhìn thấy trọn cụm cấm.

Cụm dài nhất trong `DISEASE_NAMES` + `_TREATMENT_ADVICE` là 24 ký tự ("đây là dấu hiệu của bệnh").
Không giữ lại đuôi thì một cụm bị cắt đôi giữa hai mẩu sẽ phát nửa đầu ra màn hình TRƯỚC khi có đủ
chữ để nhận ra nó - đúng thứ guard sinh ra để chặn, chỉ chậm hơn một mẩu. 32 là 24 cộng biên."""


def check_prefix(
    text: str,
    *,
    plan: ResponsePlan,
    protocol: SymptomProtocol,
    cluster: QuestionCluster,
    answers: dict[str, object],
) -> GuardResult:
    """Phần guard chạy được trên câu MỚI VIẾT DỞ, để stream từng chữ mà không phát ra thứ chưa kiểm.

    HAI LOẠI VI PHẠM, và sự khác nhau giữa chúng là toàn bộ lý do hàm này tồn tại:

    - **ĐƠN ĐIỆU** - đã vi phạm thì viết thêm bao nhiêu cũng không hết: xuất hiện tên bệnh, xuất hiện
      lời khuyên điều trị, hỏi lại field đã biết, markdown không an toàn, thừa dấu hỏi. Cả năm đều
      dựa trên "có chứa", mà tập con chuỗi thì chỉ nở ra chứ không co lại. Phát hiện được trên tiền
      tố, và phát hiện rồi thì kết luận đã chốt - không cần chờ hết câu.
    - **CHỈ BIẾT KHI XONG** - `VIOLATION_EMPTY` và `VIOLATION_NOT_A_QUESTION`. Một câu mới viết được
      nửa thì đương nhiên chưa có dấu hỏi; kết tội nó ở đây là chặn mọi câu ngay từ chữ đầu tiên.

    Điều quan trọng là loại thứ hai KHÔNG PHẢI vi phạm an toàn lâm sàng - chúng nói về HÌNH DẠNG câu.
    Nên bỏ chúng khỏi vòng kiểm tiền tố không nới lỏng gì về an toàn: mọi thứ có thể gây hại cho người
    bệnh đều nằm ở loại đơn điệu và vẫn bị chặn TRƯỚC khi chữ nào lên màn hình. `check()` đầy đủ vẫn
    chạy lại trên câu hoàn chỉnh như cũ.

    KHÔNG VIẾT LẠI LUẬT Ở ĐÂY. Hàm dùng đúng các hằng và hàm mà `check()` dùng: hai định nghĩa "câu
    này có được gửi không" lệch nhau là cách chắc chắn nhất để mở lại đúng lỗ hổng cả module này tồn
    tại để bịt."""
    violations: list[str] = []
    stripped = (text or "").strip()
    if not stripped:
        return _record_free(GuardResult(ok=True))

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
    if stripped.count("?") > max(plan.max_questions, _MIN_QUESTION_ALLOWANCE):
        violations.append(VIOLATION_TOO_MANY_QUESTIONS)

    if not violations:
        return _record_free(GuardResult(ok=True))
    return _record(GuardResult(ok=False, violations=violations))


def _record_free(result: GuardResult) -> GuardResult:
    """Tiền tố sạch KHÔNG được ghi vào sổ đếm.

    `check_prefix` chạy mỗi mẩu stream, tức hàng chục lần cho MỘT câu. Đếm chúng như những lần kiểm
    độc lập sẽ làm loãng tỉ lệ "bị guard chặn" của §12 tới mức vô nghĩa - mẫu số phình theo tốc độ
    token của provider chứ không theo số câu."""
    return result


VIOLATION_REASSURANCE = "reassurance"
"""Câu trấn an: "không sao đâu", "bạn yên tâm", "không nguy hiểm".

Đây là vi phạm RIÊNG của lane phi lâm sàng và là vi phạm dễ bị bỏ qua nhất, vì nó không trông giống
một lỗi - nó trông giống sự tử tế. Nhưng "không sao đâu" là một KẾT LUẬN lâm sàng mặc áo thân thiện:
hệ thống chưa hỏi gì, chưa có snapshot nào, và vẫn nói người bệnh ổn.

`non_clinical` docstring đã ghi điều này thành ràng buộc 3 từ đầu; ở đây nó được thi hành bằng code
thay vì bằng một dòng trong prompt."""

_REASSURANCE: tuple[str, ...] = (
    "không sao đâu", "không sao cả", "chắc không sao", "bạn yên tâm", "cứ yên tâm",
    "không nguy hiểm", "không đáng lo", "không có gì đáng lo", "bình thường thôi",
    "không cần lo", "chuyện nhỏ", "ổn mà", "bạn ổn",
)

VIOLATION_TOO_LONG = "too_long"

_CHITCHAT_MAX_CHARS = 400
"""Trần độ dài câu trả lời phi lâm sàng. Một lượt tán gẫu dài 5 đoạn là dấu hiệu model đang tự nghĩ
ra nội dung, và nội dung nó nghĩ ra thì không ai kiểm."""


def check_chitchat(text: str) -> GuardResult:
    """Câu trả lời cho lượt PHI LÂM SÀNG có được phép gửi cho người bệnh không (§4.10).

    Khác `check()` ở ba điểm, và cả ba đều vì lane này không có cụm câu hỏi nào để đối chiếu:

    1. **Không có ngoại lệ theo `script_hint`.** `check()` cho phép tên bệnh xuất hiện nếu chính cụm
       đang hỏi đã nhắc tới nó (câu hỏi phơi nhiễm). Ở đây không có cụm nào, nên mọi tên bệnh đều là
       model tự nghĩ ra.
    2. **Bắt buộc có dấu hỏi.** Trả lời rồi im lặng nghĩa là phiên đứng yên và người bệnh phải tự
       nghĩ ra việc tiếp theo. Mọi câu của lane này phải kéo về hướng lâm sàng.
    3. **Cấm trấn an** - xem `VIOLATION_REASSURANCE`.
    """
    violations: list[str] = []
    stripped = (text or "").strip()
    if not stripped:
        return _record(GuardResult(ok=False, violations=[VIOLATION_EMPTY]))

    lowered = stripped.casefold()
    if "?" not in stripped:
        violations.append(VIOLATION_NOT_A_QUESTION)
    if any(name in lowered for name in DISEASE_NAMES):
        violations.append(VIOLATION_DIAGNOSIS)
    if any(phrase in lowered for phrase in _TREATMENT_ADVICE):
        violations.append(VIOLATION_DIAGNOSIS)
    if any(phrase in lowered for phrase in _REASSURANCE):
        violations.append(VIOLATION_REASSURANCE)
    if _UNSAFE_MARKDOWN.search(stripped):
        violations.append(VIOLATION_UNSAFE_MARKDOWN)
    if len(stripped) > _CHITCHAT_MAX_CHARS:
        violations.append(VIOLATION_TOO_LONG)

    return _record(GuardResult(ok=not violations, violations=violations))


VIOLATION_INVENTED_DENIAL = "invented_denial"
"""Bản văn xuôi nói người bệnh PHỦ NHẬN một field đang là `unknown` - chưa ai hỏi tới.

Đây là lỗi im lặng nguy hiểm nhất của bản tóm tắt và nó ĐÃ xảy ra thật (xem
`summary_render.narrative_invents_denials`). Tách khỏi `VIOLATION_UNGROUNDED` vì hai lỗi khác nhau:
"ungrounded" là văn xuôi nói thứ không có trong hồ sơ, còn cái này là văn xuôi nói ĐÚNG field nhưng
SAI CỰC - và cái thứ hai nguy hiểm hơn hẳn vì nó đọc rất thuyết phục."""

VIOLATION_UNGROUNDED = "ungrounded_narrative"
"""Bản văn xuôi không được field nào trong hồ sơ đỡ - xem `check_narrative`."""

_NARRATIVE_ADVICE: tuple[str, ...] = (
    "nên uống", "nên dùng", "nên đi khám", "nên tới", "nên đến", "cần uống", "cần dùng",
    "khuyên", "chỉ định", "điều trị bằng", "kê", "liều",
)
"""Lời khuyên xử trí ở NGÔI THỨ BA - dạng mà một bản tóm tắt viết ra.

Không dùng lại `_TREATMENT_ADVICE` được: danh sách đó viết ở ngôi thứ hai ("bạn nên uống") vì nó
nhắm CÂU HỎI gửi thẳng cho người bệnh. Bản tóm tắt thì viết "Người bệnh nên uống paracetamol" - cùng
một vi phạm, không khớp một cụm từ nào. Hai văn cảnh, hai danh sách; gộp lại thì một trong hai luôn
có lỗ."""


def check_narrative(
    text: str, *, grounded: bool = True, invented_denials: tuple[str, ...] = (),
) -> GuardResult:
    """Guard cho VĂN XUÔI tóm tắt (§4.3 chế độ (a)), khác `check` vốn viết cho CÂU HỎI.

    Không dùng lại `check` được, và đó không phải chuyện hình thức: `check` bắt buộc văn bản phải có
    dấu hỏi (`VIOLATION_NOT_A_QUESTION`) và đếm trần số ý hỏi. Một bản tóm tắt hợp lệ **không có câu
    hỏi nào** - chạy nó qua `check` thì mọi bản tóm tắt đều bị chặn, và cách "sửa" nhanh nhất là nới
    `check`, tức là làm hỏng guard của câu hỏi.

    Ba kiểm tra GIỮ NGUYÊN vì chúng không dính gì tới việc văn bản là câu hỏi hay không - và chúng
    mới là phần an toàn thật: không nêu tên bệnh, không khuyên xử trí, không markdown lạ.

    `grounded` do caller tính bằng `summary_render.narrative_is_grounded` (đối chứng với bản render
    theo field). Nhận vào chứ không tự tính: guard không được biết gì về protocol/snapshot, nếu
    không nó thành tầng thứ hai đọc hồ sơ và có cơ hội lệch khỏi tầng thứ nhất."""
    violations: list[str] = []
    stripped = (text or "").strip()
    if not stripped:
        return _record(GuardResult(ok=False, violations=[VIOLATION_EMPTY]))

    lowered = stripped.casefold()
    if any(name in lowered for name in DISEASE_NAMES):
        violations.append(VIOLATION_DIAGNOSIS)
    if any(phrase in lowered for phrase in (*_TREATMENT_ADVICE, *_NARRATIVE_ADVICE)):
        violations.append(VIOLATION_DIAGNOSIS)
    if _UNSAFE_MARKDOWN.search(stripped):
        violations.append(VIOLATION_UNSAFE_MARKDOWN)
    if not grounded:
        violations.append(VIOLATION_UNGROUNDED)
    if invented_denials:
        violations.append(VIOLATION_INVENTED_DENIAL)

    return _record(GuardResult(ok=not violations, violations=violations))


_MIN_QUESTION_ALLOWANCE = 2
"""§6.5 nói "đúng 1-2 dấu hỏi", nên trần không bao giờ thấp hơn 2 kể cả với plan một ý.

Đo trên transcript thật: một câu hỏi tiếng Việt tự nhiên rất hay có dấu hỏi thứ hai ở vế xác nhận
("...phải không ạ?"). Ép trần về 1 làm guard chặn những câu hoàn toàn hợp lệ, và mỗi lần chặn là một
lượt người bệnh nhận `script_hint` khô - tức là mất đúng thứ P3 vừa làm ra."""

_DISTINCTIVE_LABEL_WORDS = 2
"""Nhãn phải có ít nhất chừng này từ mới được dùng để dò.

Lần quay lại ngưỡng 2 này (F10 Fix D) có một căn cứ mà lần thử trước không có: sau khi lên 5 nhóm
triệu chứng, nhãn của những field ĐẶC TRƯNG NHẤT lại đúng là nhãn hai từ - "Đau ngực", "Khó thở",
"Đau đầu". Ngưỡng 3 làm chính chúng VÔ HÌNH với lưới cuối cùng, tức lưới tắt đúng ở các field hay bị
hỏi lại nhất (`chest_pain` nằm trong cả `CP-01` lẫn `CP-03`, nên nó là field bị hỏi lại nhiều nhất).

Lý do bỏ ngưỡng 2 lần trước - "Loại sốt" chặn nhầm - vẫn có thật, nên nó được xử lý riêng bằng
`_GENERIC_LABEL_WORDS` thay vì bằng một ngưỡng đếm từ quét đều. Kiểm tra này vẫn là lưới an toàn PHỤ
(lưới chính là `missing_fields` trong prompt và việc reducer không cho `unknown` ghi đè giá trị đã
có), nhưng "nghiêng về bỏ sót" không được phép có nghĩa là bỏ sót đúng năm field trung tâm."""

_GENERIC_LABEL_WORDS: frozenset[str] = frozenset({"loại", "mức", "kiểu", "tình", "thông", "diễn"})
"""Từ mở đầu khiến một nhãn hai từ mất tính đặc trưng.

"Loại sốt", "Kiểu đau" mô tả một THUỘC TÍNH của triệu chứng, nên chúng xuất hiện tự nhiên trong câu
hỏi hợp lệ về chính thuộc tính đó ("cơn sốt của bạn thuộc loại sốt nào") - đó là ca chặn nhầm đo
được với `deepseek-chat`. "Đau ngực" thì gọi tên chính TRIỆU CHỨNG: nhắc tới nó khi field đã có căn
cứ và không nằm trong `missing_fields` gần như luôn là hỏi lại."""


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
        words = label.split()
        if len(words) < _DISTINCTIVE_LABEL_WORDS:
            continue
        if len(words) == _DISTINCTIVE_LABEL_WORDS and words[0] in _GENERIC_LABEL_WORDS:
            continue
        if label in lowered:
            return True
    return False


def _record(result: GuardResult) -> GuardResult:
    for violation in result.violations:
        _REJECTIONS[violation] = _REJECTIONS.get(violation, 0) + 1
    return result
