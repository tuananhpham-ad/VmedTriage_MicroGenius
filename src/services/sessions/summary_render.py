"""Hai output summary của agent (§4.3 + ADR-006) — TẤT ĐỊNH, không model.

```text
              snapshot đã validate          <- MỘT nguồn. Đây là điều kiện duy nhất khiến hai
                       │                       output không mâu thuẫn nhau.
        ┌──────────────┴──────────────┐
  summary_text                   summary_json
  văn xuôi (LLM viết lại)        HandoffSummary PHẲNG
  -> lưu DB, làm memory          -> `to_isbar()` map sang bảng I/S/B/A/R
```

Module này lo **phần tất định**: bản render theo field (chế độ (b) của §4.3) và bộ map ISBAR. Phần
văn xuôi do LLM viết nằm ở `intake_agent`; nó ghi vào `HandoffSummary.narrative`.

**Chế độ (b) là BẢN ĐỐI CHỨNG của chế độ (a).** Nếu văn xuôi nói một điều mà không field nào ở đây
đỡ, thì văn xuôi đang bịa. Đó là một kiểm tra rẻ và nên chạy tự động - xem `narrative_is_grounded`.

**Quy tắc lọc (ADR-006):** trường rỗng KHÔNG xuất. Nhưng việc lọc xảy ra ở ĐÂY, không ở nguồn dữ
liệu - snapshot vẫn giữ đủ ba giá trị. **Ngoại lệ: field an toàn luôn được render**, kể cả khi
`false` hoặc `unknown`, vì "người bệnh phủ nhận đau lan xuống tay" và "chưa ai hỏi về đau lan xuống
tay" là hai thứ điều dưỡng bắt buộc phải phân biệt được - và đó chính là chỗ họ nhìn đầu tiên.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.models.schemas import HandoffSummary
from src.services.symptom_protocol.protocol import SymptomProtocol

_TRUE, _FALSE, _UNKNOWN = "true", "false", "unknown"


@dataclass(frozen=True, slots=True)
class FieldSummary:
    """Chế độ (b) của §4.3: render TẤT ĐỊNH từ snapshot, không qua model.

    Ba nhóm, và nhóm thứ ba không được bỏ: `unknown` là dữ kiện nói "chỗ này chưa ai biết". Xoá nó đi
    thì phiếu đọc ra giống hệt như đã hỏi và người bệnh nói không."""

    reported: list[str] = field(default_factory=list)
    """Field = `true` - triệu chứng ghi nhận."""
    denied: list[str] = field(default_factory=list)
    """Field = `false` - người bệnh PHỦ NHẬN. Đây là dữ kiện lâm sàng có giá trị, không phải chỗ trống."""
    unknown_safety: list[str] = field(default_factory=list)
    """Field an toàn còn `unknown`. CHỈ field an toàn: liệt kê cả 80 field chưa hỏi thì điều dưỡng
    phải đọc 80 dòng để tìm 3 dòng có nghĩa, và như vậy là làm hỏng chính mục đích của khối này."""

    def as_text(self) -> str:
        """Bản chữ cho phiếu. Khối rỗng không xuất - đúng quy tắc render của ADR-006."""
        blocks = [
            ("Triệu chứng ghi nhận:", self.reported),
            ("Người bệnh phủ nhận:", self.denied),
            ("Chưa xác định được:", self.unknown_safety),
        ]
        return "\n\n".join(
            "\n".join([heading, *(f"- {item}" for item in items)])
            for heading, items in blocks
            if items
        )


def field_summary(protocol: SymptomProtocol, answers: dict[str, object]) -> FieldSummary:
    """Snapshot -> ba nhóm field. THUẦN: không model, không I/O."""
    safety = frozenset(protocol.safety_signal_fields)
    result = FieldSummary()
    for key, spec in protocol.fields_by_key.items():
        value = answers.get(key)
        if value == _TRUE:
            result.reported.append(spec.label)
        elif value == _FALSE:
            result.denied.append(spec.label)
        elif key in safety and value in (None, "", _UNKNOWN):
            result.unknown_safety.append(spec.label)
    return result


_DENIAL_MARKERS: tuple[str, ...] = (
    "không ghi nhận", "khong ghi nhan", "phủ nhận", "phu nhan",
    "không có", "khong co", "không bị", "khong bi", "không thấy", "khong thay",
    "không kèm", "khong kem", "không xuất hiện", "khong xuat hien",
)
"""Cụm từ biến một field thành PHỦ ĐỊNH trong văn xuôi. Xem `narrative_invents_denials`."""

_UNKNOWN_MARKERS: tuple[str, ...] = (
    "chưa xác định", "chua xac dinh", "chưa rõ", "chua ro", "chưa biết", "chua biet",
    "chưa được", "chua duoc", "chưa hỏi", "chua hoi", "không rõ", "khong ro",
)
"""Cụm từ nói đúng rằng field còn `unknown`. Câu có chúng thì KHÔNG bị tính là bịa phủ định, kể cả
khi nó cũng chứa chữ "không" ("chưa xác định được có sốt hay không")."""

_CLAUSE_SPLIT = re.compile(r"[.;\n]")
"""Tách mệnh đề. Kiểm theo MỆNH ĐỀ chứ không theo cả đoạn: một đoạn văn nói đúng ở câu đầu và bịa
ở câu ba sẽ lọt hết nếu chỉ kiểm toàn văn."""


def narrative_invents_denials(narrative: str, summary: FieldSummary) -> list[str]:
    """Field còn `unknown` mà bản văn xuôi lại nói người bệnh PHỦ NHẬN — trả về danh sách nhãn đó.

    **Đây là lỗi im lặng nguy hiểm nhất của chế độ (a), và nó đã xảy ra thật.** Chạy ca "bé 2 tháng
    sốt 38" ngày 2026-08-19, model viết:

    > *"Người bệnh không ghi nhận các triệu chứng như mệt mỏi, khó chịu, co giật, cứng gáy, yếu
    > liệt..."*

    trong khi TOÀN BỘ những field đó đang là `unknown` — chưa ai hỏi tới. Phiếu đọc ra như thể đã hỏi
    và người nhà nói không có, mà "chưa ai hỏi về co giật" và "người nhà nói bé không co giật" là hai
    hồ sơ lâm sàng khác hẳn nhau. Đúng thứ `CLAUDE.md` nguyên tắc 3 cấm, và đúng thứ mà gate
    "hallucinated negative rate 0% trên tập safety" (§8) đo.

    `narrative_is_grounded` KHÔNG bắt được ca này: nó chỉ hỏi "văn xuôi có nhắc tới field nào trong
    hồ sơ không", và ở đây model nhắc tới đúng field — chỉ sai CỰC. Vì thế phải có kiểm tra thứ hai.

    Cách kiểm: tách văn xuôi thành mệnh đề, và một mệnh đề bị tính là bịa khi nó **vừa** nhắc tới
    nhãn của một field `unknown` **vừa** mang cụm từ phủ định, **và không** mang cụm từ nói rõ là
    chưa xác định. Điều kiện thứ ba là thứ chống báo nhầm: "chưa xác định được có sốt hay không" là
    câu ĐÚNG, dù nó chứa chữ "không"."""
    if not narrative.strip() or not summary.unknown_safety:
        return []
    invented: list[str] = []
    for clause in _CLAUSE_SPLIT.split(narrative.casefold()):
        if not any(marker in clause for marker in _DENIAL_MARKERS):
            continue
        if any(marker in clause for marker in _UNKNOWN_MARKERS):
            continue
        invented.extend(
            label for label in summary.unknown_safety
            if label.casefold() in clause and label not in invented
        )
    return invented


def narrative_is_grounded(narrative: str, summary: FieldSummary) -> bool:
    """Văn xuôi có được ít nhất một field đỡ không - kiểm tra RẺ chống bịa (§4.3).

    Cố ý thô: nó chỉ trả lời "bản văn xuôi này có nhắc tới thứ gì trong hồ sơ không", không phải "mọi
    câu trong đó đều đúng". Kiểm tra đúng-từng-câu cần một model thứ hai chấm một model thứ nhất, mà
    như thế thì không còn là kiểm tra tất định nữa. Bản thô này bắt được ca tệ nhất và hay gặp nhất:
    model trả về một đoạn văn tổng quát không dính gì tới ca này.

    Phiếu KHÔNG có field nào (phiên đóng ngay lượt đầu) thì không có gì để đối chứng - trả `True`,
    vì báo "bịa" ở đó là báo sai."""
    labels = [*summary.reported, *summary.denied, *summary.unknown_safety]
    if not labels or not narrative.strip():
        return True
    folded = narrative.casefold()
    return any(label.casefold() in folded for label in labels)


ISBAR_BLOCKS = ("I", "S", "B", "A", "R")


def to_isbar(summary: HandoffSummary) -> dict[str, dict[str, object]]:
    """`HandoffSummary` phẳng -> 5 khối I/S/B/A/R cho bảng của điều dưỡng (ADR-006 mục 1).

    Đây là toàn bộ chỗ ISBAR tồn tại trong hệ thống. Schema lưu trữ vẫn phẳng; đổi bố cục bảng là sửa
    HÀM NÀY, không phải migrate dữ liệu.

    Trường rỗng không xuất (`_present`). `Triage Category` nằm trong khối `[I]` đúng như template -
    và nó **do code tất định điền, không do LLM**; đó là chỗ dễ bị hiểu nhầm nhất khi người mới đọc
    phiếu, nên nhãn của nó nói thẳng điều đó."""
    blocks: dict[str, dict[str, object]] = {
        "I": _present(
            {
                "Tuổi": summary.age,
                "Giới tính": summary.sex,
                "Mức ưu tiên đề xuất (do rule engine, KHÔNG do LLM)": _priority(summary.proposed_priority),
                "Mức tạm thời trong hội thoại": _priority(summary.provisional_priority),
                "Nguồn mức ưu tiên": summary.priority_source,
            }
        ),
        "S": _present({"Lý do vào viện": summary.chief_complaint}),
        "B": _present(
            {
                "Dị ứng": summary.allergies,
                "Bệnh nền": summary.comorbidities,
                "Thuốc đang dùng": summary.current_medications,
            }
        ),
        "A": _present(
            {
                "Khởi phát": summary.onset,
                "Mức độ": summary.severity,
                "Triệu chứng đi kèm": summary.associated_symptoms,
                "Dấu hiệu nguy hiểm phát hiện": [flag.label or flag.code for flag in summary.red_flags],
                "Thông tin còn thiếu": summary.missing_information,
                "Phiếu đã đầy đủ": summary.is_complete,
                "Lý do kết thúc": summary.stop_reason,
            }
        ),
        "R": _present(
            {
                "Đề xuất xử trí": summary.proposed_action,
                "Trạng thái duyệt": summary.approval_status,
            }
        ),
    }
    return {key: value for key, value in blocks.items() if value}


def _present(rows: dict[str, object]) -> dict[str, object]:
    """Bỏ trường rỗng. `False` và `0` KHÔNG phải rỗng - `is_complete=False` là đúng thứ điều dưỡng
    cần thấy, mà một phép kiểm `if not value` sẽ nuốt mất nó."""
    return {
        label: value
        for label, value in rows.items()
        if value is not None and value != "" and value != []
    }


def _priority(value) -> str | None:
    return getattr(value, "value", None) if value is not None else None
