"""Reducer: nguồn sự thật DUY NHẤT của hồ sơ (§5 `_guidance/what_to_do_next.md`).

`previous_snapshot + field_events -> next_snapshot + audit + cụm mở lại + field chờ xác nhận`

VÌ SAO TỒN TẠI. Trước module này, việc "gộp trạng thái" nằm rải trong `run_turn`: `_merge_answers`
rồi `_apply_derived_fields` rồi `retraction.apply_retraction` rồi `find_contradictions`, và
`run_open_turn` gọi một tập con KHÁC của đúng chuỗi đó. Hai hệ quả đo được, không phải suy đoán:

1. **Không có đường nào XOÁ một dữ kiện đã khai.** `_merge_answers` cố ý bỏ qua "unknown" (im lặng
   không phải bằng chứng rút lại), nên người bệnh nói "con số 39 đó là nhiệt độ phòng, tôi chưa đo
   lại" thì `temp_c=39` nằm nguyên trong hồ sơ gửi cho điều dưỡng. Cách duy nhất để xoá là phủ định
   được đúng field CHA - nếu không có field cha thì không có đường nào.
2. **`confirm_before_retract` là một lời hứa chưa thực hiện.** Docstring của nó
   (`protocol.py:123`) ghi "phải XIN XÁC NHẬN trước khi xoá dây chuyền", nhưng `apply_retraction`
   chưa bao giờ đọc tập này - nó chỉ được dùng để giữ field trong schema trích xuất.

Vì thế reducer nhận **sự kiện** (`FieldEvent`) chứ không nhận dict giá trị: `unknown` do model không
trích được và `unknown` do người bệnh rút lại lời khai là HAI việc khác nhau, mà một dict không phân
biệt được. Ba `operation` của §4.1 chính là chỗ phân biệt đó.

RANH GIỚI. Đây là tầng L3, **KHÔNG có model** (§7.1). Mọi thứ trong file này phải tất định: cùng
`(before, events)` luôn cho ra cùng kết quả. `certainty` được suy ra bằng code từ `evidence_span` chứ
không tin nhãn model tự gán - xem `certainty_of`.

SNAPSHOT VẪN ĐÚNG 3 GIÁ TRỊ (§4.2). `unset` là OPERATION, không phải giá trị thứ tư: reducer quy nó
về `"unknown"` trong snapshot và ghi một `AuditEvent` để phân biệt "chưa bao giờ hỏi" với "đã khai
rồi rút lại". `rule_engine.evaluate` và `common_safety/predicates.py` đang giả định đúng ba giá trị -
thêm giá trị thứ tư là thay đổi lan ra toàn bộ tầng luật an toàn.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
from typing import Literal

from src.services.symptom_protocol import retraction
from src.services.symptom_protocol.output_guard import DISEASE_NAMES
from src.services.symptom_protocol.protocol import SymptomProtocol
from src.services.symptom_protocol.stage_machine import NEGATED_PARENT_VALUES, is_filled

TriState = str

Operation = Literal["set", "unset", "no_change"]
"""§4.1. `set` = xác nhận giá trị mới (kể cả `"false"`); `unset` = người dùng nói rõ thông tin cũ
không còn đúng nhưng CHƯA cung cấp giá trị thay thế; `no_change` = không có bằng chứng để cập nhật."""

Certainty = Literal["explicit", "inferred"]
"""`explicit` = bằng chứng nhắc tới CHÍNH field đó; `inferred` = suy ra từ ngữ cảnh, hoặc bằng chứng
là một hạt phủ định trần, hoặc bằng chứng dính tên bệnh. Chỉ `explicit` mới được phép xoá dây chuyền
một field trong `confirm_before_retract` mà không hỏi lại."""

SOURCE_EXTRACTOR = "extractor"
SOURCE_SCREENING = "screening"
SOURCE_KEYWORD = "keyword"
SOURCE_DERIVED = "derived"

# Tên bệnh trong đoạn trích dẫn (`DISEASE_NAMES`) = đính chính CÓ RỦI RO HIỂU NHẦM (§5 quy tắc 5).
# Đây đúng là bug C2: "bé không **sốt xuất huyết**" là phủ định một TÊN BỆNH, không phải phủ định
# triệu chứng sốt - nhưng chuỗi "sốt" nằm ngay trong đó nên cả model lẫn matcher từ khoá đều đọc
# thành `fever_reported=false` rồi xoá sạch nhiệt độ đã khai.

# Đoạn trích KHÔNG chứng minh được field nào cụ thể - cùng lý do với `intake_agent._EMPTY_EVIDENCE`,
# nhưng ở đây dùng cho việc khác: không phải để LOẠI giá trị (tầng trích xuất đã làm), mà để hạ
# `certainty` xuống `inferred` nên việc xoá dây chuyền phải hỏi lại trước.
_BARE_EVIDENCE: frozenset[str] = frozenset({
    "không", "khong", "ko", "no", "không có", "khong co", "không ạ", "khong a",
    "có", "co", "yes", "vâng", "vang", "dạ", "da", "ừ", "u", "ok", "đúng", "dung", "sai",
    "", "unknown", "null", "none", "n/a", "na", "-", ".",
})


@dataclass(frozen=True, slots=True)
class FieldEvent:
    """Một thay đổi của ĐÚNG lượt hiện tại, kèm bằng chứng (§4.1).

    Không phải một snapshot: extractor trả về cái gì ĐỔI ở lượt này, không viết lại toàn bộ hồ sơ.
    `value` chỉ có nghĩa khi `operation == "set"`."""

    field: str
    operation: Operation = "set"
    value: object = "unknown"
    certainty: Certainty = "explicit"
    evidence_span: str = ""
    source: str = SOURCE_EXTRACTOR


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """Một dòng nhật ký hồ sơ. Downstream triage KHÔNG đọc tập này (nó chỉ đọc snapshot đã validate);
    tập này tồn tại để trả lời được "vì sao field này mất giá trị" sau sự cố (§5 quy tắc 7)."""

    field: str
    kind: str
    """`set` | `unset` | `retract_dependent` | `retract_held`."""
    before: object = None
    after: object = None
    source: str = SOURCE_EXTRACTOR
    evidence_span: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "field": self.field, "kind": self.kind, "before": self.before, "after": self.after,
            "source": self.source, "evidence_span": self.evidence_span,
        }


AUDIT_SET = "set"
AUDIT_UNSET = "unset"
AUDIT_RETRACT_DEPENDENT = "retract_dependent"
AUDIT_RETRACT_HELD = "retract_held"


@dataclass(slots=True)
class ReduceResult:
    answers: dict[str, TriState] = dataclass_field(default_factory=dict)
    audit: tuple[AuditEvent, ...] = ()
    reopened_clusters: frozenset[str] = frozenset()
    contradicted: frozenset[str] = frozenset()
    pending_confirmation: tuple[str, ...] = ()
    """Field mà việc xoá dây chuyền đã bị GIỮ LẠI vì đính chính chưa đủ rõ (§5 quy tắc 5). Caller phải
    hỏi một câu xác nhận ngắn; không hỏi thì hồ sơ đứng yên chứ không tự xoá."""

    @property
    def audit_log(self) -> tuple[dict[str, object], ...]:
        return tuple(event.as_dict() for event in self.audit)


def certainty_of(value: object, evidence_span: object) -> Certainty:
    """Mức chắc chắn của một sự kiện, suy ra bằng CODE từ đoạn trích - không hỏi model.

    Model tự chấm `certainty` là mời nó nói "explicit" cho mọi thứ: nhãn đó không có chi phí gì với
    model nhưng lại là thứ quyết định hệ thống có được xoá hồ sơ hay không. Ba trường hợp bị hạ xuống
    `inferred`:

    1. không có đoạn trích nào (model trả dạng phẳng, hoặc trích xuất theo từ khoá);
    2. đoạn trích là hạt phủ định/khẳng định trần - nó nằm trong hầu hết mọi câu trả lời nên chứng
       minh được mọi thứ, tức là không chứng minh được gì;
    3. đoạn trích có TÊN BỆNH - "không sốt xuất huyết" không đồng nghĩa "không sốt" (§11 đính chính
       mục 3).

    Chỉ chiều PHỦ ĐỊNH mới bị soi: bịa một `"true"` chỉ đẩy ca lên mức thận trọng hơn, còn loại nhầm
    hoặc xoá nhầm là bỏ sót - cùng cân nhắc bất đối xứng với `_needs_evidence`."""
    if value not in NEGATED_PARENT_VALUES:
        return "explicit"
    if not isinstance(evidence_span, str):
        return "inferred"
    normalized = " ".join(evidence_span.split()).casefold()
    if normalized in _BARE_EVIDENCE:
        return "inferred"
    if any(name in normalized for name in DISEASE_NAMES):
        return "inferred"
    return "explicit"


def events_from_values(
    values: dict[str, TriState],
    *,
    source: str = SOURCE_EXTRACTOR,
    evidence: dict[str, str] | None = None,
) -> tuple[FieldEvent, ...]:
    """Dựng sự kiện từ một dict giá trị - cầu nối cho các nguồn CHƯA nói được ngôn ngữ sự kiện
    (quét từ khoá, verdict sàng lọc gộp).

    `"unknown"` thành `no_change` chứ KHÔNG thành `unset`: nguồn dict không phân biệt được "người
    bệnh rút lại lời khai" với "lượt này không nhắc tới", và mặc định an toàn là không xoá gì."""
    evidence = evidence or {}
    return tuple(
        FieldEvent(
            field=key,
            operation="no_change" if value == "unknown" else "set",
            value=value,
            certainty=certainty_of(value, evidence.get(key)),
            evidence_span=evidence.get(key, ""),
            source=source,
        )
        for key, value in values.items()
    )


def _apply_events(
    before: dict[str, TriState], events: tuple[FieldEvent, ...],
) -> tuple[dict[str, TriState], list[AuditEvent]]:
    """§5 quy tắc 1-3. Sự kiện SAU thắng sự kiện TRƯỚC (dữ kiện mới nhất thắng), và caller chịu trách
    nhiệm xếp `events` theo đúng thứ tự ưu tiên đó."""
    merged = dict(before)
    audit: list[AuditEvent] = []
    for event in events:
        previous = merged.get(event.field)
        if event.operation == "no_change":
            # Giữ NGUYÊN hành vi của `_merge_answers`: khoá chưa tồn tại thì tạo với "unknown" (nhiều
            # chỗ downstream đọc `answers.keys()` để biết field nào đã đi qua schema trích xuất), còn
            # giá trị đã xác định thì im lặng không được ghi đè.
            merged.setdefault(event.field, "unknown")
            continue
        if event.operation == "unset":
            if not is_filled(previous):
                continue  # không có gì để rút lại
            merged[event.field] = "unknown"
            audit.append(AuditEvent(
                event.field, AUDIT_UNSET, before=previous, after="unknown",
                source=event.source, evidence_span=event.evidence_span,
            ))
            continue
        merged[event.field] = event.value
        if previous != event.value:
            audit.append(AuditEvent(
                event.field, AUDIT_SET, before=previous, after=event.value,
                source=event.source, evidence_span=event.evidence_span,
            ))
    return merged, audit


def _risky_retractions(
    protocol: SymptomProtocol,
    before: dict[str, TriState],
    after: dict[str, TriState],
    events: tuple[FieldEvent, ...],
) -> frozenset[str]:
    """Field cha nào vừa bị phủ định bằng một đính chính CHƯA ĐỦ RÕ (§5 quy tắc 5).

    Hai điều kiện phải cùng đúng, cố ý HẸP:

    - field nằm trong `protocol.confirm_before_retract` - tập protocol tự khai "xoá nhầm cái này thì
      đắt". Mở rộng ra mọi field thì mỗi lời phủ định đều tốn một lượt xác nhận, và người bệnh sẽ bỏ
      giữa chừng (§1 mục 5);
    - `certainty == "inferred"` - đính chính rõ ràng ("à nhầm, tôi không sốt") vẫn được xoá NGAY, đúng
      như trước. Chỉ đường mờ mới bị giữ lại."""
    guarded = protocol.confirm_before_retract
    if not guarded:
        return frozenset()
    weak = {
        event.field for event in events
        if event.operation == "set" and event.certainty == "inferred"
        and event.value in NEGATED_PARENT_VALUES
    }
    return frozenset(
        key for key in guarded
        if key in weak
        and before.get(key) != after.get(key)
        and after.get(key) in NEGATED_PARENT_VALUES
        # Chỉ giữ lại khi thật sự CÓ cái để mất: không field con nào đã điền thì việc xác nhận không
        # bảo vệ được gì, mà vẫn tốn của người bệnh một lượt.
        and any(is_filled(after.get(child)) for child in protocol.field_dependencies.get(key, ()))
    )


def reduce(
    protocol: SymptomProtocol,
    before: dict[str, TriState],
    events: tuple[FieldEvent, ...],
    *,
    confirmed_retractions: frozenset[str] = frozenset(),
) -> ReduceResult:
    """Áp sự kiện của một lượt lên hồ sơ. Không gọi model, không ném ra ngoài.

    `confirmed_retractions`: field đã được hỏi xác nhận rồi (caller giữ sổ). Hỏi ĐÚNG MỘT LẦN mỗi
    field - nếu không, một phiên mà model liên tục trả `certainty=inferred` sẽ lặp mãi cùng một câu
    xác nhận và không bao giờ ghi nhận được lời đính chính.

    Thứ tự BẮT BUỘC, mỗi bước là điều kiện của bước sau:

        áp sự kiện -> derive -> giữ đính chính rủi ro -> xoá dây chuyền -> mâu thuẫn

    `derive` chạy TRƯỚC khi xoá dây chuyền vì field dẫn xuất (`fever_duration_days`) cũng là field con
    và phải bị xoá cùng."""
    merged, audit = _apply_events(before, events)
    merged = _derive(protocol, merged)

    held = _risky_retractions(protocol, before, merged, events) - confirmed_retractions
    for key in sorted(held):
        # Trả field cha về giá trị CŨ, không giữ giá trị mới rồi bỏ xoá dây chuyền. Nếu giữ, hồ sơ ở
        # trạng thái nửa vời ("không sốt" + "39 độ") và `rule_engine`/`select_protocol` của CHÍNH lượt
        # này chấm trên trạng thái đó - một câu nói mơ hồ đủ sức đổi protocol. Fail-safe là đứng yên.
        previous = before.get(key)
        audit.append(AuditEvent(
            key, AUDIT_RETRACT_HELD, before=merged.get(key), after=previous, source=SOURCE_EXTRACTOR,
        ))
        if previous is None:
            merged.pop(key, None)
        else:
            merged[key] = previous

    # `apply_retraction` tự tính lại field dẫn xuất của phần nó vừa xoá, và cố ý KHÔNG phục hồi field
    # dẫn xuất đã bị xoá nếu phép tính trả về rỗng. Gọi `_derive` thêm một lần nữa ở đây sẽ đạp lên
    # đúng quyết định đó và làm "sốt 2 ngày" sống lại sau khi đã ghi nhận là không sốt.
    cleaned, reopened = retraction.apply_retraction(protocol, before, merged)
    for key, value in cleaned.items():
        if value != merged.get(key):
            audit.append(AuditEvent(
                key, AUDIT_RETRACT_DEPENDENT, before=merged.get(key), after=value, source=SOURCE_DERIVED,
            ))
    merged = cleaned

    contradicted, contradiction_clusters = retraction.find_contradictions(protocol, merged)
    return ReduceResult(
        answers=merged,
        audit=tuple(audit),
        reopened_clusters=reopened | frozenset(contradiction_clusters),
        contradicted=contradicted,
        pending_confirmation=tuple(sorted(held)),
    )


def _derive(protocol: SymptomProtocol, answers: dict[str, TriState]) -> dict[str, TriState]:
    """Field dẫn xuất (`protocol.derive_fields`) - phép tính THUẦN, không qua LLM."""
    if protocol.derive_fields is None:
        return answers
    derived = protocol.derive_fields(answers)
    if not derived:
        return answers
    return {**answers, **derived}
