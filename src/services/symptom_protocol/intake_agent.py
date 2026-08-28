"""LLM extraction theo cụm + ghép hướng C/E theo stage - DÙNG CHUNG cho mọi symptom_group.

Tái dùng hạ tầng đã có, không viết lại: `provider_router.complete()` +
`infra/json_output.parse_json_object()` để gọi LLM/bóc JSON, và
kỹ thuật `_contains_any` của `semantic_mapper.py` để quét từ khoá nhẹ cho field "cơ hội".

LLM ở đây CHỈ làm một việc: trích field từ free text vào đúng schema của MỘT cụm câu hỏi
(`cluster.fields`), không bao giờ nhận toàn bộ field registry mỗi lượt. Quyết định next_cluster/route/
dừng KHÔNG nằm ở đây - đó là việc của `stage_machine.py` + `rule_engine.py`, đúng
`coding_convention.md` rule 1-2. Mọi nội dung đặc thù bệnh (field, cụm, thông điệp cấp cứu, field an
toàn "cơ hội") lấy từ `protocol: SymptomProtocol`, module này không biết field/bệnh cụ thể nào.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from src.config import get_settings
from src.services.engines.semantic_mapper import _contains_any
from src.services.infra import fever_stage_log as stage_log
from src.services.infra import provider_router
from src.services.infra.json_output import parse_json_object
from src.services.symptom_protocol import (
    batching,
    compaction,
    controller,
    coverage,
    dialogue,
    flags,
    output_guard,
    phrasing,
    ranking,
    reducer,
    rule_engine,
    screening,
    stage_machine,
)
from src.services.symptom_protocol.common_safety import screening_groups as common_screening
from src.services.symptom_protocol.common_safety import text_safety_signals
from src.services.symptom_protocol.models import QuestionCluster, ScreeningGroup
from src.services.symptom_protocol.protocol import SymptomProtocol
from src.services.text_norm import fold_diacritics

logger = logging.getLogger("vmedtriage.symptom_intake")

TriState = str  # "true" | "false" | "unknown"

TokenSink = Callable[[str], None]
"""Nhận từng mẩu văn bản câu hỏi ngay khi model sinh ra.

`None` (mặc định) = không stream, hành vi y như trước. Truyền hàm vào chỉ khi phía gọi thật sự phát
được từng mẩu ra ngoài (endpoint SSE) - không có ai nghe thì streaming chỉ thêm một lớp gián tiếp."""

# Mức khắt khe của việc đòi `evidence_span` - xem `_needs_evidence`/`_collect_fields`.
EvidencePolicy = Literal["off", "asked", "unasked"]

_TRUE_TOKENS = frozenset({"true", "có", "co", "yes", "dương tính", "duong tinh"})
_FALSE_TOKENS = frozenset({"false", "không", "khong", "no", "âm tính", "am tinh"})


def _answers_delta(before: dict[str, TriState], extracted: dict[str, TriState]) -> dict[str, str]:
    """Delta THẬT cho log: `"<giá trị cũ> -> <giá trị mới>"`.

    Trước đây hardcode `"unknown -> {value}"`, nên log luôn nói mọi field đi lên từ `unknown` - đọc
    log không bao giờ thấy được lượt nào GHI ĐÈ giá trị cũ (đính chính, sửa lời khai). Đúng lớp
    thông tin cần nhất khi lần lại bug C2."""
    delta: dict[str, str] = {}
    for key, value in extracted.items():
        old = before.get(key, "unknown")
        if old != value:
            delta[key] = f"{old} -> {value}"
    return delta


def _tri_state_value(raw: object) -> TriState:
    if raw is None:
        return "unknown"
    if isinstance(raw, bool):
        return "true" if raw else "false"
    text = str(raw).strip().casefold()
    if not text or text in ("null", "none"):
        return "unknown"
    if text in _TRUE_TOKENS:
        return "true"
    if text in _FALSE_TOKENS:
        return "false"
    return "unknown"


def _today_iso() -> str:
    """Ngày hiện tại thật (không phải ngày cố định của tài liệu nguồn) - cho LLM quy đổi được biểu
    thức tương đối ("hôm qua", "2 ngày nay", "3 hôm trước") sang ngày cụ thể. Thiếu mốc này, LLM
    không có cách nào biết "hôm nay" là ngày nào nên hay bịa hoặc bỏ trống field ngày tháng - phát
    hiện qua test tay với LLM thật (fever `fever_onset_at` không bao giờ trích đúng khi người dùng
    nói tương đối)."""
    return datetime.now(timezone.utc).date().isoformat()


# `answer_quality` chỉ điều khiển UX (hỏi lại / đi tiếp), TUYỆT ĐỐI không đụng tới triage - đó là
# việc của rule_engine. Giá trị lạ do model bịa rơi về "answered" (an toàn: không kích hoạt retry vô
# hạn), vì quyết định retry thật sự dựa trên `nothing_filled` do CODE tính, không dựa vào nhãn này.
ANSWER_QUALITIES: frozenset[str] = frozenset(
    {"answered", "partial", "evasive", "non_answer", "correction", "asks_question"}
)
_DEFAULT_ANSWER_QUALITY = "answered"


def _answer_quality(parsed: dict) -> str:
    value = str(parsed.get("answer_quality") or "").strip().casefold()
    return value if value in ANSWER_QUALITIES else _DEFAULT_ANSWER_QUALITY


def _known_facts(protocol: SymptomProtocol, answers: dict[str, TriState]) -> str:
    """Bảng `nhãn: giá trị` của field ĐÃ điền, đưa vào prompt để LLM hết mù trạng thái.

    Lỗi thật: prompt không hề nhận `answers` nên model không biết đã hỏi được gì, sinh ra câu hỏi vô
    hồn và hỏi lại thứ người dùng vừa nói. Dùng `FieldSpec.label` chứ không dump key thô - key kiểu
    `worse_after_defervescence` không giúp model diễn đạt tự nhiên hơn."""
    lines = [
        f"- {protocol.fields_by_key[key].label}: {value}"
        for key, value in answers.items()
        if key in protocol.fields_by_key and stage_machine.is_filled(value)
    ]
    return "\n".join(lines) if lines else "(chưa biết gì - đây là lượt đầu)"


def _field_specs(protocol: SymptomProtocol, field_keys: tuple[str, ...]) -> str:
    """Mô tả field cho prompt trích xuất. Field protocol không biết bị BỎ QUA kèm log, không raise.

    VÌ SAO KHÔNG `raise`, DÙ ĐÓ LÀ TRIỆU CHỨNG CỦA MỘT LỖI THẬT. Hàm này chạy lúc dựng prompt, tức
    NGOÀI khối `try` bọc lời gọi model trong `extract_turn` - nên một `KeyError` ở đây bay thẳng qua
    `run_turn`, qua `session._turn`, ra tới route, và người bệnh nhận đúng một dòng "Không xử lý được
    tin nhắn." giữa lúc đang khai bệnh. `extract_turn` hứa trong docstring của nó là KHÔNG BAO GIỜ
    ném; chỗ này từng là lỗ thủng của lời hứa đó.

    KHÓA THẬT NẰM Ở `key not in protocol.fields_by_key`: cụm đang hỏi thuộc protocol KHÁC với
    protocol đang chạy. Nó xảy ra được vì lượt phát hiện đổi protocol chọn cụm kế tiếp bằng protocol
    CŨ rồi mới đổi tên protocol (`session._turn`), nên lượt sau ghép cụm cũ với protocol mới. Ví dụ
    đã tái hiện: cụm `AB-02` (bụng) mang `complaint_onset_at`, mà `fever`/`chest_pain`/`headache`
    không khai field đó.

    Bỏ qua ở đây là NGẮT MÁU, không phải chữa: field bị bỏ sẽ không được trích trong lượt đó. Nhưng
    lượt vẫn chạy, `stage_machine.advance` vẫn chọn được cụm đúng của protocol mới cho lượt sau, nên
    phiên tự về lại đường ray - khác hẳn việc chết cả lượt. Log ở mức WARNING vì nó luôn là dấu hiệu
    của một lỗi định tuyến cần sửa, không phải trạng thái bình thường."""
    unknown = [key for key in field_keys if key not in protocol.fields_by_key]
    if unknown:
        logger.warning(
            "symptom_intake.unknown_fields protocol=%s fields=%s - cụm đang hỏi không thuộc protocol này",
            protocol.name, ",".join(unknown),
        )
    lines = []
    for key in field_keys:
        spec = protocol.fields_by_key.get(key)
        if spec is None:
            continue
        # Ghi rõ ngoặc kép trong chính hint để giảm khả năng model trả bareword unknown (không quote)
        # - lỗi thật gặp phải với gpt-4o-mini qua OpenRouter khi chạy Checkpoint 6(b) của fever, xem
        # _repair_bareword_unknown ở dưới (vẫn giữ lớp sửa lỗi đó làm lưới an toàn, không chỉ dựa vào
        # việc nhắc prompt - lỗi này không riêng gì fever, giữ ở tầng chung).
        if spec.tri_state:
            kind = '"true" | "false" | "unknown" (luôn có dấu ngoặc kép)'
        elif spec.allowed_values:
            # Liệt kê thẳng giá trị hợp lệ thay vì để model tự suy từ `hint` - `_collect_fields` loại
            # mọi giá trị ngoài danh sách này, nên không nhắc ở prompt chỉ làm field rơi về unknown.
            kind = " | ".join(f'"{value}"' for value in spec.allowed_values) + " hoặc null - CHỈ dùng đúng các mã này"
        else:
            kind = "giá trị cụ thể hoặc null"
        lines.append(f"- {key} ({spec.label}) [{kind}]: {spec.hint}")
    return "\n".join(lines)


_EXTRACTION_SYSTEM = """Bạn là bộ trích xuất thông tin y tế cho một hệ thống phân loại mức độ khẩn cấp.

Hôm nay là ngày {today} (định dạng YYYY-MM-DD).

NHIỆM VỤ DUY NHẤT: đọc tin nhắn của người dùng và điền vào ĐÚNG các trường liệt kê dưới đây, KHÔNG
được điền trường nào khác ngoài danh sách này.

ĐÃ BIẾT VỀ NGƯỜI BỆNH (đừng hỏi lại, đừng ghi đè nếu tin nhắn không nhắc tới):
{known_facts}

QUY TẮC BẮT BUỘC:
- CHỈ trích xuất thông tin ĐÃ CÓ trong tin nhắn. TUYỆT ĐỐI KHÔNG suy diễn, KHÔNG phỏng đoán con số.
- MỖI trường điền được PHẢI kèm "evidence_span": đoạn TRÍCH NGUYÊN VĂN từ tin nhắn người dùng làm
  căn cứ. Chép Y HỆT ký tự trong tin nhắn - không diễn giải lại, không dịch, không đổi hoa/thường.
  Không trích được đoạn nào thì để "unknown", TUYỆT ĐỐI KHÔNG đoán.
- Với trường [true|false|unknown]: trả "true" nếu người dùng xác nhận CÓ, "false" nếu XÁC NHẬN RÕ
  RÀNG không có, "unknown" nếu không nhắc tới hoặc mơ hồ. TUYỆT ĐỐI KHÔNG suy diễn im lặng thành
  "false" - im lặng luôn là "unknown". Cả "true" LẪN "false" đều phải có evidence_span.
- Với trường NGÀY THÁNG: nếu người dùng nói tương đối ("hôm nay", "hôm qua", "N ngày nay/trước/rồi"),
  tự quy đổi sang ngày cụ thể YYYY-MM-DD dựa trên "hôm nay" đã cho ở trên - KHÔNG bỏ trống chỉ vì
  người dùng không nói ngày tuyệt đối. evidence_span là cụm chỉ thời gian nguyên văn ("2 hôm nay").
- RÚT LẠI LỜI KHAI: nếu người dùng nói một thông tin ĐÃ KHAI TRƯỚC ĐÓ là không còn đúng nhưng KHÔNG
  cho giá trị thay thế (vd "con số 39 độ đó là nhiệt độ phòng, tôi chưa đo lại"), trả trường đó dạng
  {{"operation": "unset", "evidence_span": "<trích nguyên văn>"}}. CHỈ dùng khi người dùng nói rõ là
  sai/không còn đúng - không nhắc tới thì để "unknown", KHÔNG dùng "unset".
- KHÔNG chẩn đoán bệnh, KHÔNG đề xuất mức độ khẩn cấp, KHÔNG đưa hướng xử trí.
- Chỉ trả về MỘT JSON object, không kèm giải thích.
{batch_negation_rule}
CÁC TRƯỜNG CẦN TRÍCH XUẤT:
{field_specs}

Cuối cùng, thêm "answer_quality" mô tả tin nhắn này trả lời câu vừa hỏi ra sao:
"answered" (đã trả lời) | "partial" (mới trả lời một phần) | "evasive" (né tránh) |
"non_answer" (không phải câu trả lời: chào hỏi, dấu câu, lạc đề) | "correction" (đính chính điều đã
nói trước đó) | "asks_question" (hỏi ngược lại hệ thống)

Định dạng trả về:
{{"<field_key>": {{"value": <giá trị>, "evidence_span": "<trích nguyên văn>"}}, ...,
  "answer_quality": "<một trong các giá trị trên>"}}"""

_BATCH_NEGATION_RULE = """- Đây là câu hỏi gộp kiểu phủ định cả cụm. Nếu người dùng phủ định TƯỜNG MINH cho CẢ CỤM (vd "không,
  không có gì trong số đó cả", "hoàn toàn bình thường"), thêm "cluster_all_negative": true vào JSON
  trả về - hệ thống sẽ tự gán false cho các trường còn lại chưa nhắc tới. Nếu người dùng chỉ xác nhận
  một vài ý, đừng thêm cờ này - chỉ điền đúng field họ đã nói rõ.
- Khi thêm "cluster_all_negative": true, BẮT BUỘC thêm kèm "negation_evidence": "<đoạn TRÍCH NGUYÊN
  VĂN từ tin nhắn người dùng thể hiện sự phủ định đó>". Phải chép Y HỆT ký tự trong tin nhắn, không
  diễn giải lại, không dịch, không viết hoa/thường khác đi. Không trích được câu nào thì KHÔNG được
  đặt cờ.
"""


@dataclass(slots=True)
class Extraction:
    """Kết quả một call trích xuất. `cluster_fields` tách khỏi `safety_fields` để caller biết cụm
    đang hỏi có thực sự được trả lời hay không (quyết định retry) - field nhặt được từ cụm KHÁC
    không tính là đã trả lời câu vừa hỏi."""

    cluster_fields: dict[str, TriState] = field(default_factory=dict)
    safety_fields: dict[str, TriState] = field(default_factory=dict)
    answer_quality: str = _DEFAULT_ANSWER_QUALITY
    llm_ok: bool = False
    events: tuple[reducer.FieldEvent, ...] = ()
    """Sự kiện cho reducer (§4.1), theo ĐÚNG thứ tự ưu tiên: safety trước, cụm đang hỏi sau - sự kiện
    sau thắng sự kiện trước, và câu trả lời cho chính câu vừa hỏi phải thắng field nhặt bên lề.

    Rỗng nghĩa là nguồn này chưa nói được ngôn ngữ sự kiện; caller dựng tạm bằng
    `reducer.events_from_values` để không nhánh nào mất dữ kiện."""

    @property
    def all_fields(self) -> dict[str, TriState]:
        return {**self.safety_fields, **self.cluster_fields}


def extract_turn(
    protocol: SymptomProtocol,
    cluster: QuestionCluster,
    message: str,
    *,
    answers: dict[str, TriState] | None = None,
    safety_keys: tuple[str, ...] = (),
    session_id: str | None = None,
    turn: int = 0,
    stage: str | None = None,
    credential: provider_router.LLMCredential | None = None,
    evidence: EvidencePolicy = "asked",
) -> Extraction:
    """Call LLM DUY NHẤT của một lượt: trích field. Không sinh câu hỏi, không chọn cụm kế tiếp.

    `evidence` là mức khắt khe áp cho field CỦA CỤM (field ngoài cụm luôn là `"unasked"`). Mặc định
    `"asked"` - tin nhắn là câu trả lời trực tiếp cho câu vừa hỏi. Lượt mở truyền `"unasked"`: lúc đó
    chưa ai hỏi gì nên không field nào được miễn trích dẫn.

    Không bao giờ ném ra ngoài - lỗi LLM rơi về toàn bộ field = "unknown" (an toàn hơn suy diễn sai,
    đúng P0-4/P0-6)."""
    log_stage = stage or cluster.stage
    answers = answers or {}
    schema_keys = cluster.fields + tuple(k for k in safety_keys if k not in cluster.fields)

    if session_id is not None:
        stage_log.step(
            session_id, turn=turn, stage=log_stage, cluster_id=cluster.id, event="retrieve",
            input={"cluster_id": cluster.id},
            output={"fields": list(schema_keys), "schema_size": len(schema_keys)},
        )

    batch_rule = _BATCH_NEGATION_RULE if cluster.batch_negation else ""
    system_prompt = _EXTRACTION_SYSTEM.format(
        today=_today_iso(),
        known_facts=_known_facts(protocol, answers),
        batch_negation_rule=batch_rule,
        field_specs=_field_specs(protocol, schema_keys),
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ]

    parsed, parse_error, provider_name, model_name, response_text, latency_ms = _invoke_json(messages, credential)

    if session_id is not None:
        stage_log.llm_io(
            session_id, turn=turn, stage=log_stage, cluster_id=cluster.id, purpose="extract",
            provider=provider_name, model=model_name, messages=messages, response_text=response_text,
            parsed=parsed, tokens=None, latency_ms=latency_ms, parse_error=parse_error,
        )

    parsed = parsed or {}
    # Thứ tự hứng sự kiện = thứ tự áp trong reducer: safety (field bên lề) TRƯỚC, cụm đang hỏi SAU.
    # Đảo lại thì một suy đoán bên lề ghi đè chính câu trả lời người bệnh vừa nói ra.
    events: list[reducer.FieldEvent] = []
    # batch_negation=False TƯỜNG MINH (turn-scoping): cờ phủ định gộp chỉ có nghĩa cho ĐÚNG cụm vừa
    # được hỏi. `safety_keys` là field của cụm KHÁC mà người dùng chưa hề được hỏi tới - để cờ lan
    # sang đây tức là một câu "không có gì cả" sẽ đóng luôn cả loạt cụm chưa hỏi.
    safety_fields = _collect_fields(
        protocol, tuple(k for k in safety_keys if k not in cluster.fields), parsed,
        batch_negation=False, message=message, evidence="unasked", events=events,
    )
    cluster_fields = _collect_fields(
        protocol, cluster.fields, parsed, batch_negation=cluster.batch_negation, message=message,
        evidence=evidence, events=events,
    )
    extraction = Extraction(
        cluster_fields=cluster_fields,
        safety_fields=safety_fields,
        answer_quality=_answer_quality(parsed),
        llm_ok=parse_error is None,
        events=tuple(events),
    )

    if session_id is not None:
        stage_log.step(
            session_id, turn=turn, stage=log_stage, cluster_id=cluster.id, event="extract",
            input=None, output=extraction.all_fields,
            answers_delta=_answers_delta(answers, extraction.all_fields),
            answer_quality=extraction.answer_quality,
        )

    return extraction


_SCREENING_SYSTEM = """Bạn là bộ trích xuất thông tin y tế cho một hệ thống phân loại mức độ khẩn cấp.

Hôm nay là ngày {today} (định dạng YYYY-MM-DD).

BỐI CẢNH: trợ lý VỪA đọc cho người bệnh nghe một danh sách dấu hiệu, chia thành các NHÓM dưới đây.
Tin nhắn bạn sắp đọc là câu trả lời cho ĐÚNG danh sách đó.

CÁC NHÓM ĐÃ ĐỌC CHO NGƯỜI BỆNH:
{group_specs}

ĐÃ BIẾT VỀ NGƯỜI BỆNH (đừng hỏi lại, đừng ghi đè nếu tin nhắn không nhắc tới):
{known_facts}

NHIỆM VỤ 1 - kết luận cho TỪNG nhóm, dùng đúng một trong ba giá trị:
- "negative": người bệnh nói RÕ là KHÔNG có dấu hiệu nào của nhóm đó.
- "positive": có ít nhất một dấu hiệu trong nhóm.
- "unknown": tin nhắn không nhắc tới nhóm đó, hoặc câu trả lời mơ hồ.

QUY TẮC BẮT BUỘC:
- "negative" PHẢI kèm "evidence": đoạn TRÍCH NGUYÊN VĂN từ tin nhắn người bệnh. Chép Y HỆT ký tự -
  không diễn giải lại, không dịch. Không trích được đoạn nào thì PHẢI trả "unknown".
- Một câu phủ định CHUNG cho cả danh sách ("không có dấu hiệu nào cả", "không, tất cả đều bình
  thường") là "negative" cho MỌI nhóm - trích chính câu đó làm evidence cho từng nhóm.
- Nhưng nếu người bệnh chỉ nói về MỘT VÀI nhóm, các nhóm còn lại là "unknown", TUYỆT ĐỐI KHÔNG phải
  "negative". Im lặng không bao giờ là phủ định.
- KHÔNG chẩn đoán bệnh, KHÔNG đề xuất mức độ khẩn cấp, KHÔNG đưa hướng xử trí.

NHIỆM VỤ 2 - điền các trường cụ thể dưới đây.

- Nhóm nào bạn kết luận "positive" thì BẮT BUỘC phải chỉ ra dấu hiệu nào: đặt "true" cho ĐÚNG những
  trường ứng với dấu hiệu người bệnh xác nhận. Trả "positive" mà không đặt "true" cho trường nào là
  câu trả lời THIẾU - hệ thống sẽ không biết người bệnh vừa xác nhận điều gì.
- Người bệnh trả lời gọn ("có", "đúng rồi", "vâng") cho một câu chỉ đọc lên MỘT dấu hiệu thì đó là
  xác nhận ĐÚNG dấu hiệu ấy - đặt "true" cho nó. Câu đọc lên NHIỀU dấu hiệu mà họ chỉ nói "có" thì
  KHÔNG đoán là dấu hiệu nào: để cả nhóm "positive" và để các trường "unknown".
- Trường đặt "true" KHÔNG cần "evidence_span" - người bệnh đang trả lời đúng câu vừa được hỏi.
- Trường đặt "false", hoặc trường enum/số/ngày, thì PHẢI kèm "evidence_span" trích nguyên văn;
  không trích được thì để "unknown".

CÁC TRƯỜNG CÓ THỂ ĐIỀN THÊM:
{field_specs}

Chỉ trả về MỘT JSON object, không kèm giải thích, theo đúng định dạng:
{{"groups": {{"<mã nhóm>": {{"verdict": "negative|positive|unknown", "evidence": "<trích nguyên văn>"}}, ...}},
  "<field_key>": {{"value": <giá trị>, "evidence_span": "<trích nguyên văn>"}}, ...,
  "answer_quality": "answered|partial|evasive|non_answer|correction|asks_question"}}"""


def _group_specs(groups: tuple[ScreeningGroup, ...]) -> str:
    """Danh sách nhóm cho prompt. Định dạng `* <mã>` cố ý KHÁC dòng field (`- <key> (`) - hai loại
    dòng lẫn nhau thì cả người đọc log lẫn bộ tra bảng trong test đều nhặt nhầm mã nhóm thành key."""
    return "\n".join(f"* {group.id}: {group.probe_hint}" for group in groups)


def extract_probe_turn(
    protocol: SymptomProtocol,
    cluster: QuestionCluster,
    groups: tuple[ScreeningGroup, ...],
    message: str,
    *,
    answers: dict[str, TriState],
    safety_keys: tuple[str, ...] = (),
    session_id: str | None = None,
    turn: int = 0,
    stage: str | None = None,
    credential: provider_router.LLMCredential | None = None,
) -> tuple[Extraction, screening.ScreeningOutcome]:
    """Call LLM của một lượt SÀNG LỌC GỘP: verdict theo nhóm + field người bệnh nói rõ.

    **Vì sao field vẫn bị siết `evidence="unasked"` dù câu hỏi vừa đọc chính các dấu hiệu đó.** Câu
    sàng lọc chỉ đọc lên Ý ĐẠI DIỆN của từng nhóm, không đọc từng field một. Nới sang `"asked"` sẽ cho
    model ghi thẳng `"false"` cho ~25 field mà không cần trích dẫn gì - tức là đi vòng qua đúng cổng
    verdict+bằng chứng mà cả cơ chế này dựng ra để chặn. Đường đóng hàng loạt hợp lệ DUY NHẤT là
    verdict theo nhóm.

    Không bao giờ ném ra ngoài - lỗi LLM rơi về "không thu được gì", hội thoại tự về đường hỏi từng
    cụm (an toàn: hỏi thừa, không bỏ sót)."""
    log_stage = stage or cluster.stage
    schema_keys = cluster.fields + tuple(k for k in safety_keys if k not in cluster.fields)

    if session_id is not None:
        stage_log.step(
            session_id, turn=turn, stage=log_stage, cluster_id=cluster.id, event="retrieve",
            input={"cluster_id": cluster.id, "groups": [group.id for group in groups]},
            output={"fields": list(schema_keys), "schema_size": len(schema_keys)},
        )

    system_prompt = _SCREENING_SYSTEM.format(
        today=_today_iso(),
        group_specs=_group_specs(groups),
        known_facts=_known_facts(protocol, answers),
        field_specs=_field_specs(protocol, schema_keys),
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ]

    parsed, parse_error, provider_name, model_name, response_text, latency_ms = _invoke_json(messages, credential)

    if session_id is not None:
        stage_log.llm_io(
            session_id, turn=turn, stage=log_stage, cluster_id=cluster.id, purpose="extract",
            provider=provider_name, model=model_name, messages=messages, response_text=response_text,
            parsed=parsed, tokens=None, latency_ms=latency_ms, parse_error=parse_error,
        )

    parsed = parsed or {}
    events: list[reducer.FieldEvent] = []
    safety_fields = _collect_fields(
        protocol, tuple(k for k in safety_keys if k not in cluster.fields), parsed,
        batch_negation=False, message=message, evidence="unasked", events=events,
    )
    cluster_fields = _collect_fields(
        protocol, cluster.fields, parsed, batch_negation=False, message=message, evidence="unasked",
        events=events,
    )
    extraction = Extraction(
        cluster_fields=cluster_fields,
        safety_fields=safety_fields,
        answer_quality=_answer_quality(parsed),
        llm_ok=parse_error is None,
        events=tuple(events),
    )
    outcome = screening.apply_verdicts(
        protocol, log_stage, groups, parsed, answers,
        # `allow_bare=True`: một chữ "Không" trần ĐƯỢC nhận ở đây, khác hẳn field ngoài cụm đang hỏi.
        # Lý do là turn-scoping có thật chứ không phải nới lỏng: verdict chỉ được đọc ở lượt mà tin
        # nhắn trước của trợ lý ĐÚNG LÀ câu sàng lọc tĩnh liệt kê chính các nhóm này (`session` chỉ
        # truyền `probe` khi nó vừa phát ra câu đó). "Không" ở đây là câu trả lời trực tiếp cho danh
        # sách vừa đọc lên, không phải model tự nói thay người bệnh về thứ chưa ai hỏi.
        evidence_ok=lambda evidence: _evidence_in_message(evidence, message, allow_bare=True),
    )

    if session_id is not None:
        stage_log.step(
            session_id, turn=turn, stage=log_stage, cluster_id=cluster.id, event="screen",
            input={"groups": [group.id for group in groups]},
            output={
                "negative": list(outcome.negative_group_ids),
                "positive": list(outcome.positive_group_ids),
                "closed_clusters": sorted(outcome.closed_cluster_ids),
            },
        )
        if outcome.rejected_group_ids:
            stage_log.step(
                session_id, turn=turn, stage=log_stage, cluster_id=cluster.id, event="screen_reject",
                input=None, output={"groups": list(outcome.rejected_group_ids)},
            )
        stage_log.step(
            session_id, turn=turn, stage=log_stage, cluster_id=cluster.id, event="extract",
            input=None, output={**outcome.negatives, **extraction.all_fields},
            answers_delta=_answers_delta(answers, {**outcome.negatives, **extraction.all_fields}),
            answer_quality=extraction.answer_quality,
        )

    return extraction, outcome


def extract_cluster(
    protocol: SymptomProtocol,
    cluster: QuestionCluster,
    message: str,
    *,
    session_id: str | None = None,
    turn: int = 0,
    stage: str | None = None,
    answers: dict[str, TriState] | None = None,
    credential: provider_router.LLMCredential | None = None,
) -> dict[str, TriState]:
    """Chữ ký cũ (chỉ field của đúng cụm) - giữ cho caller/test hiện có."""
    return extract_turn(
        protocol, cluster, message, answers=answers, session_id=session_id, turn=turn, stage=stage,
        credential=credential,
    ).cluster_fields


_BAREWORD_UNKNOWN_RE = re.compile(r'(:\s*)unknown\b(?!")')


def _repair_bareword_unknown(text: str) -> str:
    """Sửa lỗi JSON thật gặp phải với gpt-4o-mini (qua OpenRouter, phát hiện lần đầu khi chạy
    Checkpoint 6(b) của fever): model đọc thấy `[true|false|unknown]` trong mô tả schema rồi coi
    "unknown" như 1 literal JSON kiểu `true`/`false`/`null` và trả về KHÔNG có dấu ngoặc kép (vd
    `"seizure_occurred": unknown,`), khiến `json.loads` hỏng toàn bộ - kể cả field khác trong CÙNG
    response đã trích đúng cũng bị mất theo. Chỉ thay bareword `unknown` ngay sau dấu `:` (không đụng
    tới "unknown" đã nằm trong chuỗi có ngoặc kép)."""
    return _BAREWORD_UNKNOWN_RE.sub(r'\1"unknown"', text)


def _invoke_json(
    messages: list[dict[str, str]],
    credential: provider_router.LLMCredential | None,
    *,
    temperature: float | None = None,
) -> tuple[dict | None, str | None, str, str, str, int]:
    started = time.monotonic()
    try:
        result = provider_router.complete(
            messages, temperature=temperature, credential=credential,
            role=provider_router.ROLE_FACT_EXTRACTOR,
        )
    except Exception as exc:
        logger.warning("symptom_intake.extract_failed reason=%s", type(exc).__name__)
        latency_ms = int((time.monotonic() - started) * 1000)
        return None, f"{type(exc).__name__}: {exc}", "(none)", "(none)", "", latency_ms

    latency_ms = int((time.monotonic() - started) * 1000)
    try:
        parsed = parse_json_object(result.text)
    except Exception:
        try:
            parsed = parse_json_object(_repair_bareword_unknown(result.text))
        except Exception as exc:  # JSON vẫn hỏng sau khi đã thử sửa - không phải lỗi gọi provider
            logger.warning("symptom_intake.parse_failed reason=%s", type(exc).__name__)
            return None, f"{type(exc).__name__}: {exc}", result.provider, result.model, result.text, latency_ms

    return parsed, None, result.provider, result.model, result.text, latency_ms


_WHITESPACE_RE = re.compile(r"\s+")
_EDGE_PUNCT_RE = re.compile(r"^[\s,.;:!?]+|[\s,.;:!?]+$")


def _normalize_for_evidence(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", (text or "").strip()).casefold()


def _fold_bare_reply(text: str) -> str:
    folded = _EDGE_PUNCT_RE.sub("", fold_diacritics(text))
    return _WHITESPACE_RE.sub(" ", folded.strip())


_BARE_CLUSTER_NEGATIVE_REPLIES: frozenset[str] = frozenset({
    "binh thuong",
    "van binh thuong",
    "hoan toan binh thuong",
    "tat ca binh thuong",
    "mọi thứ bình thường",
    "moi thu binh thuong",
    "on",
    "on a",
    "binh thuong a",
    "khong",
    "minh khong",
    "toi khong",
    "em khong",
    "da bao khong",
    "da noi khong",
    "khong co",
    "khong thay",
    "khong co dau hieu nao",
    "khong co gi",
    "khong co gi ca",
})


def _apply_bare_cluster_negation(parsed: dict, message: str, *, batch_negation: bool) -> dict:
    """Treat terse normal/negative replies as a scoped denial of the cluster just asked."""
    if not batch_negation or parsed.get("cluster_all_negative"):
        return parsed
    if _fold_bare_reply(message) not in _BARE_CLUSTER_NEGATIVE_REPLIES:
        return parsed
    patched = dict(parsed)
    patched["cluster_all_negative"] = True
    patched["negation_evidence"] = message.strip()
    return patched


# Đoạn trích KHÔNG mang thông tin: nó nằm trong hầu hết mọi câu trả lời nên chứng minh được mọi thứ,
# tức là không chứng minh được gì. Lỗi thật đo được khi chạy LLM thật: người bệnh trả lời "Không,
# không bị co giật" thì model ghi luôn `rash_present="false"` và trích dẫn "Không" - đúng chữ có trong
# tin nhắn nên `_evidence_in_message` chấp nhận, dù người bệnh chưa hề được hỏi về ban. Đây chính là
# lỗi C1 ở dạng nhỏ hơn. Yêu cầu bằng chứng phải nhắc tới CHÍNH triệu chứng đó, không phải chỉ là hạt
# phủ định trần. Model cũng hay dùng "unknown"/"null" làm giá trị lấp chỗ cho khoá này.
_EMPTY_EVIDENCE: frozenset[str] = frozenset({
    "không", "khong", "ko", "no", "không có", "khong co", "không ạ", "khong a", "không, không",
    "có", "co", "yes", "vâng", "vang", "dạ", "da", "ừ", "u", "ok",
    "unknown", "null", "none", "n/a", "na", "-", ".", "không rõ", "khong ro",
})


def _evidence_in_message(evidence: object, message: str, *, allow_bare: bool = False) -> bool:
    """Đoạn trích do model trả về có THẬT SỰ nằm trong tin nhắn người dùng không.

    So khớp là substring sau khi chuẩn hoá khoảng trắng + casefold: model bịa evidence sẽ không khớp,
    còn model trích đúng thì hầu như luôn khớp. So khớp lỏng hơn (fuzzy) sẽ mở lại đúng lỗ hổng mà
    guard này sinh ra để bịt.

    `allow_bare=True` cho phép hạt phủ định trần (`_EMPTY_EVIDENCE`) - CHỈ dùng cho phủ định gộp của
    đúng cụm vừa hỏi, nơi "Không" là câu trả lời trực tiếp cho câu hỏi vừa đặt ra chứ không phải model
    tự nói thay người dùng."""
    if not isinstance(evidence, str):
        return False
    normalized = _normalize_for_evidence(evidence)
    if not normalized or (not allow_bare and normalized in _EMPTY_EVIDENCE):
        return False
    return normalized in _normalize_for_evidence(message)


_VALID_OPERATIONS = frozenset({"set", "unset", "no_change"})


def _field_payload(raw: object) -> tuple[object, object, str]:
    """Bóc `{"value": ..., "evidence_span": ..., "operation": ...}`, chấp nhận cả dạng phẳng.

    Giữ dạng phẳng vì hai lý do: (a) model đôi khi trả phẳng dù prompt yêu cầu có evidence - lúc đó
    giá trị vẫn được xét rồi bị loại ở tầng `_needs_evidence`, tốt hơn là làm hỏng cả JSON; (b) các
    caller kiểm tra hậu xử lý enum/tri-state không cần dựng evidence giả.

    `operation` (§4.1) mặc định `"set"` và mọi giá trị lạ đều rơi về `"set"`: một nhãn model viết sai
    chính tả không được biến thành lệnh xoá hồ sơ. Chỉ `"unset"` là lệnh phá huỷ, nên chỉ nó phải
    được viết đúng."""
    if isinstance(raw, dict) and ("value" in raw or "operation" in raw):
        operation = str(raw.get("operation") or "set").strip().casefold()
        if operation not in _VALID_OPERATIONS:
            operation = "set"
        return raw.get("value"), raw.get("evidence_span"), operation
    return raw, None, "set"


def _negation_evidence_ok(parsed: dict, message: str) -> bool:
    """Cờ phủ định gộp CHỈ được tin khi model trích được nguyên văn câu phủ định từ chính tin nhắn.

    Lỗi thật đã tái hiện 3/3 lần khi test tay với LLM thật: người dùng nói "ăn uống tốt, không nôn",
    model đặt `cluster_all_negative` rồi hệ thống gán "false" cho cả 11 red flag (co giật, tím tái,
    xuất huyết...) mà người dùng chưa hề được hỏi. Đây là suy diễn im lặng thành phủ định - vi phạm
    P0-4 và là loại lỗi nguy hiểm nhất của hệ thống (bỏ sót ca cấp cứu).

    Dùng chung phép kiểm với evidence của từng field (`_evidence_in_message`) - cùng một nguyên tắc:
    không có bằng chứng trong lời người dùng thì không được ghi nhận. Khác một điểm: ở đây một chữ
    "Không" trần VẪN được chấp nhận (`allow_bare=True`), vì cờ này đã bị turn-scoping giới hạn trong
    ĐÚNG cụm vừa hỏi - "Không" là câu trả lời cho chính câu hỏi đó. Ngoài phạm vi cụm đang hỏi, cùng
    chữ "Không" ấy lại không chứng minh được gì (xem `_EMPTY_EVIDENCE`)."""
    return _evidence_in_message(parsed.get("negation_evidence"), message, allow_bare=True)


def _coerce_enum(spec, raw: object) -> object | None:
    """Ép giá trị field không-tri-state về đúng `allowed_values`. Trả None = loại (giữ unknown)."""
    if isinstance(raw, (list, tuple)):
        return raw
    text = str(raw).strip()
    if not spec.allowed_values:
        return text
    lowered = text.casefold()
    for value in spec.allowed_values:
        if lowered == value.casefold():
            return value  # trả về đúng dạng chuẩn trong allowed_values, không giữ dạng model viết
    return None


_VOMITING_FREQUENT_MARKERS = (
    "non nhieu", "oi nhieu", "non lien tuc", "oi lien tuc", "non lap lai", "oi lap lai",
    "non lien tiep", "oi lien tiep", "non rat nhieu", "oi rat nhieu",
)
_VOMITING_UNABLE_TO_KEEP_FLUIDS_MARKERS = (
    "khong giu duoc nuoc", "khong giu duoc do an", "uong vao non", "uong vao oi",
    "an vao non", "an vao oi", "non tat ca", "oi tat ca", "non het", "oi het",
)
_VOMITING_NONE_MARKERS = (
    "khong non", "khong oi", "chua non", "chua oi", "khong bi non", "khong bi oi",
)
def _vomiting_value_supported(value: object, evidence_span: object, message: str) -> bool:
    """Chặn nâng ``buồn nôn`` thành một mức độ NÔN mà lời khai không hề có.

    ``evidence_span`` khớp nguyên văn mới chỉ chứng minh model đã chép một đoạn có thật; nó chưa chứng minh
    đoạn ấy *hàm ý đúng enum*. Lỗi thực tế là evidence ``buồn nôn`` có thật nhưng model vẫn trả
    ``vomiting_severity=frequent``. Guard hẹp này kiểm tra entailment tối thiểu cho đúng field có ảnh hưởng
    tới RF-15/RF-40, không cố thay LLM bằng một bộ NLP tổng quát.
    """
    if value == "unknown":
        return True
    if not _evidence_in_message(evidence_span, message):
        return False
    folded = _fold_bare_reply(str(evidence_span))
    # "buồn nôn" là nausea. Bỏ cụm này trước khi tìm động từ nôn để chữ "nôn" bên trong không bị tính
    # nhầm là một lần nôn thực sự.
    actual_vomiting = folded.replace("buon non", "").replace("cam giac non", "")
    has_vomiting_verb = bool(re.search(r"\b(non|oi)\b", actual_vomiting))
    if value == "none":
        return any(marker in folded for marker in _VOMITING_NONE_MARKERS)
    if value == "occasional":
        return has_vomiting_verb and not any(marker in folded for marker in _VOMITING_NONE_MARKERS)
    if value == "frequent":
        stated_frequency = bool(re.search(r"\b(non|oi)\s+(?:\w+\s+){0,2}\d+\s*(?:lan|lần)\b", actual_vomiting))
        return any(marker in folded for marker in _VOMITING_FREQUENT_MARKERS) or stated_frequency
    if value == "unable_to_keep_fluids":
        return any(marker in folded for marker in _VOMITING_UNABLE_TO_KEEP_FLUIDS_MARKERS)
    return False


_RIGORS_MARKERS = (
    "ret run", "run cam cap", "run ban bat", "run lap cap", "run bat ban", "lanh run",
    "run nguoi", "run toan than", "rung minh", "co giat vi lanh",
    "dap chan khong do", "dap chan van khong do", "mac am van khong do", "u am van khong do",
)
"""Cụm cho thấy RUN NGƯỜI không kiểm soát được - đúng thứ `rigors` định nghĩa."""

_CHILL_ONLY_MARKERS = (
    "on lanh", "gai ret", "gai lanh", "gai nguoi", "hoi lanh", "thay lanh", "cam giac lanh",
    "lanh", "ret", "so lanh",
)
"""Cụm chỉ nói tới CẢM GIÁC LẠNH. Gần như mọi cơn sốt đều có, và bản thân nó không phải rét run."""


def _rigors_value_supported(value: object, evidence_span: object, message: str) -> bool:
    """Chặn nâng ``ớn lạnh``/``sốt có rét`` thành ``rigors=true``.

    Cùng lỗi và cùng khuôn chữa với `_vomiting_value_supported`: evidence khớp nguyên văn chỉ chứng
    minh model đã chép một đoạn CÓ THẬT, chưa chứng minh đoạn đó *hàm ý đúng field*. Lỗi thật đo
    được: người bệnh nói "sốt có rét", model trả `rigors="true"` trích dẫn đúng chữ "rét" - và
    `rigors` là M0 amber NICE gợi ý nhiễm khuẩn huyết, nên một true bịa ở đây đẩy thẳng mức ưu tiên.

    Trong tiếng Việt "rét" một mình nghĩa là LẠNH, còn "rét RUN" mới là rét run; hai thứ cách nhau
    đúng một chữ mà khác nhau cả một mức triage. Nhắc prompt là cần nhưng không đủ - cùng lý do đã
    ghi ở `_vomiting_value_supported`.

    Chỉ xét khi model CÓ trích dẫn và trích dẫn đó nói về cảm giác lạnh. Người bệnh trả lời thẳng
    câu hỏi Q2-02 ("có ạ") thì evidence không chứa từ lạnh nào - đó là câu trả lời trực tiếp cho
    đúng câu vừa hỏi, guard không có quyền phủ quyết nó (nếu không thì cụm không bao giờ đủ dữ kiện
    và agent hỏi lại tới hết hạn mức - đúng cái bẫy `_collect_fields` mô tả)."""
    if value != "true":
        return True
    if not _evidence_in_message(evidence_span, message):
        return True
    folded = _fold_bare_reply(str(evidence_span))
    if any(marker in folded for marker in _RIGORS_MARKERS):
        return True
    return not any(marker in folded for marker in _CHILL_ONLY_MARKERS)


_TRI_STATE_ENTAILMENT_GUARDS: dict[str, object] = {
    "rigors": _rigors_value_supported,
}
"""Field tri-state có guard entailment riêng: `key -> (value, evidence_span, message) -> bool`.

Bảng chứ không phải một chuỗi `if`: đây là chỗ đăng ký khi phát hiện một field bị model nâng cực sai
một cách CÓ HỆ THỐNG. Giữ nó NGẮN - mỗi mục là một luật tiếng Việt viết tay, và một bảng dài là dấu
hiệu nên sửa ở tầng khác (hint của field, hoặc tách field). Nhánh enum có bảng riêng của nó
(`vomiting_severity`) vì hai nhánh kiểm giá trị khác nhau."""


def _needs_evidence(policy: EvidencePolicy, spec, value: object) -> bool:
    """Giá trị này có bắt buộc phải kèm `evidence_span` khớp tin nhắn không?

    CHỈ field người dùng CHƯA được hỏi mới phải chứng minh:

    - Cả `"true"` lẫn `"false"` đều phải có bằng chứng. Positive thiếu căn cứ vẫn là dữ kiện bịa,
      dù nó thường đẩy mức triage theo hướng thận trọng hơn.
    - enum/số/ngày -> phải có bằng chứng (đúng chiều lỗi C2: model tự sinh
      `fever_onset_at="2023-10-05"` trong lúc đang hỏi chuyện khác).

    Lưới keyword red-flag chạy độc lập và lấy căn cứ từ chính cụm từ khớp, nên việc siết output LLM
    tại đây không loại bỏ lớp bắt khẩn cấp tất định.

    Field của cụm ĐANG hỏi (`"asked"`) không phải chứng minh gì: cả tin nhắn chính là câu trả lời cho
    đúng câu vừa hỏi, nên `"không"` ở đó là dữ kiện thật chứ không phải suy diễn. Cả 3 lần tái hiện C1
    đều xảy ra ở field NGOÀI cụm đang hỏi (`safety_keys`) hoặc do cờ phủ định gộp lan ra ngoài cụm -
    hai đường đó đã có guard riêng (`_negation_evidence_ok` + `batch_negation=False` cho safety keys)."""
    if policy != "unasked":
        return False
    # Lượt kể tự do/field ngoài câu đang hỏi: mọi dữ kiện xác định đều phải trỏ về lời người dùng.
    # Positive không có evidence dù làm triage thận trọng hơn vẫn là dữ kiện bịa và không được phép
    # lọt vào summary. Lưới keyword red-flag chạy độc lập nên các cụm khẩn cấp tất định vẫn được bắt.
    return value != "unknown"


def _collect_fields(
    protocol: SymptomProtocol,
    field_keys: tuple[str, ...],
    parsed: dict,
    *,
    batch_negation: bool = False,
    message: str = "",
    evidence: EvidencePolicy = "off",
    events: list[reducer.FieldEvent] | None = None,
    source: str = reducer.SOURCE_EXTRACTOR,
) -> dict[str, TriState]:
    """Bóc field từ JSON model trả về, loại mọi thứ không hợp lệ.

    `events` (tuỳ chọn) là ống hứng `FieldEvent` cho reducer (§4.1). Nó đi SONG SONG với dict trả về
    chứ không thay thế: dict là "giá trị của lượt này" mà mọi caller cũ vẫn đọc, còn sự kiện mang
    thêm `operation`/`certainty`/`evidence_span` - thứ một dict không diễn đạt được. Truyền `None`
    (mặc định) thì hàm hành xử y hệt bản trước.

    `evidence` chọn mức khắt khe theo việc người dùng CÓ ĐANG ĐƯỢC HỎI field đó hay không - chi tiết
    quy tắc xem `_needs_evidence`. `"off"` (mặc định) dùng cho test hậu xử lý enum/tri-state.

    **Vì sao KHÔNG siết mọi giá trị.** Bản đầu bắt MỌI giá trị xác định phải kèm `evidence_span`. Hai
    hậu quả đo được bằng test, không phải suy đoán:

    1. `{"seizure_occurred": "true", "seizure_active_now": "true"}` (model trả phẳng) trên câu "tay
       chân đang giật, mắt trợn lên" -> CẢ HAI red flag bị loại -> không chốt EMERGENCY -> agent hỏi
       tiếp như ca thường. Guard chống bịa lại tự tạo ra đúng lỗi tệ nhất (bỏ sót cấp cứu, P0-5). Lưới
       từ khoá `scan_opportunistic_fields` KHÔNG đỡ được ("tay chân đang giật" không chứa "co giật").
    2. Ca lành tính (H1/V1 Part 8) không bao giờ kết thúc: gần như mọi câu trả lời của người bệnh là
       phủ định, tất cả bị loại vì thiếu trích dẫn -> cụm không bao giờ đủ dữ kiện -> hỏi lại tới hết
       hạn mức. Mọi ca nhẹ sẽ bị đẩy lên EARLY_VISIT vì checklist tự chăm sóc không bao giờ đủ.

    Nguyên tắc rút ra: **bằng chứng chỉ bắt buộc khi model nói thay người dùng về thứ chưa được hỏi**,
    và chỉ ở chiều làm ca nhẹ đi. Trả lời trực tiếp cho đúng câu vừa hỏi thì không phải chứng minh."""
    parsed = _apply_bare_cluster_negation(parsed, message, batch_negation=batch_negation)
    cluster_negative = (
        batch_negation
        and bool(parsed.get("cluster_all_negative"))
        and _negation_evidence_ok(parsed, message)
    )

    collected: dict[str, TriState] = {}
    for key in field_keys:
        spec = protocol.fields_by_key.get(key)
        if spec is None:
            # Field protocol đang chạy không khai - cùng nguyên nhân với `_field_specs` (cụm thuộc
            # protocol khác) và cùng cách xử lý: bỏ qua, không raise. Không log lại ở đây vì
            # `_field_specs` đã ghi đúng một dòng cho cùng lượt đó; log hai lần cho một sự cố làm
            # người đọc tưởng nó xảy ra hai lần.
            continue
        raw, evidence_span, operation = _field_payload(parsed.get(key))

        if operation == "unset":
            # RÚT LẠI lời khai: người bệnh nói thông tin cũ không còn đúng nhưng chưa có giá trị thay
            # thế (§4.1). Bắt buộc có bằng chứng đúng như `set false` - không có thì hạ về
            # `no_change`, vì một lệnh xoá không chứng minh được là đường ngắn nhất để mất hồ sơ.
            if flags.unset_operation_enabled() and _evidence_in_message(evidence_span, message):
                collected[key] = "unknown"
                if events is not None:
                    events.append(reducer.FieldEvent(
                        field=key, operation="unset", value="unknown", certainty="explicit",
                        evidence_span=str(evidence_span), source=source,
                    ))
            continue

        if not spec.tri_state:
            if raw not in (None, "", "null"):
                coerced = _coerce_enum(spec, raw)
                supported = not _needs_evidence(evidence, spec, coerced) or _evidence_in_message(
                    evidence_span, message,
                )
                if key == "vomiting_severity" and coerced is not None:
                    supported = supported and _vomiting_value_supported(coerced, evidence_span, message)
                if coerced is not None and supported:
                    collected[key] = coerced
                    _emit(events, key, coerced, evidence_span, source)
            continue

        value = _tri_state_value(raw)
        guard = _TRI_STATE_ENTAILMENT_GUARDS.get(key)
        if guard is not None and not guard(value, evidence_span, message):
            # Trích dẫn có thật nhưng KHÔNG hàm ý field này - giữ ngỏ để còn được hỏi lại đúng cách,
            # thay vì ghi một dữ kiện sai cực vào hồ sơ.
            value = "unknown"
        if _needs_evidence(evidence, spec, value) and not _evidence_in_message(evidence_span, message):
            # Model khẳng định "không" nhưng không trích được câu nào trong tin nhắn -> giữ ngỏ để
            # còn được hỏi lại, thay vì đóng vĩnh viễn một field an toàn (lỗi C1).
            value = "unknown"
        if value == "unknown" and cluster_negative:
            # Phủ định gộp đã tự có bằng chứng riêng (`negation_evidence`) nên vẫn được áp ở đây.
            value = "false"
            evidence_span = parsed.get("negation_evidence")
        collected[key] = value
        _emit(events, key, value, evidence_span, source)

    return collected


def _emit(
    events: list[reducer.FieldEvent] | None, key: str, value: object, evidence_span: object, source: str,
) -> None:
    """Ghi một sự kiện `set`/`no_change` vào ống hứng, `certainty` do CODE chấm (`reducer.certainty_of`).

    Không nhận `certainty` từ model: nhãn đó không tốn gì của model nhưng lại là thứ quyết định hệ
    thống có được xoá dây chuyền hay không."""
    if events is None:
        return
    span = evidence_span if isinstance(evidence_span, str) else ""
    events.append(reducer.FieldEvent(
        field=key,
        operation="no_change" if value == "unknown" else "set",
        value=value,
        certainty=reducer.certainty_of(value, span),
        evidence_span=span,
        source=source,
    ))


def _collect(
    protocol: SymptomProtocol,
    cluster: QuestionCluster,
    parsed: dict,
    message: str = "",
    *,
    evidence: EvidencePolicy = "off",
) -> dict[str, TriState]:
    return _collect_fields(
        protocol, cluster.fields, parsed, batch_negation=cluster.batch_negation, message=message,
        evidence=evidence,
    )


def _merge_answers(answers: dict[str, TriState], *updates: dict[str, TriState]) -> dict[str, TriState]:
    """Gộp answers, `updates` sau ghi đè `updates` trước - đúng CS §3: giá trị TRÍCH MỚI NHẤT thắng.

    NGOẠI LỆ (đơn điệu tri-state): "unknown" KHÔNG được ghi đè một giá trị đã xác định. Lỗi thật khi
    test tay: các dấu hiệu nguy hiểm đã xác nhận "không có" ở lượt trước bị xoá về "unknown" ở lượt
    sau chỉ vì tin nhắn mới không nhắc tới chúng - hệ thống quên câu trả lời cũ rồi hỏi lại. "Không
    nhắc tới" là im lặng, không phải bằng chứng rút lại. Giá trị XÁC ĐỊNH mới vẫn ghi đè giá trị xác
    định cũ (CS §3 - người dùng có quyền sửa lại lời khai)."""
    merged = dict(answers)
    for update in updates:
        for key, value in update.items():
            if value == "unknown" and merged.get(key) not in (None, "unknown"):
                continue
            merged[key] = value
    return merged


def _apply_derived_fields(protocol: SymptomProtocol, merged: dict[str, TriState]) -> dict[str, TriState]:
    """Tính field dẫn xuất (`protocol.derive_fields`, vd `fever_duration_days` từ `fever_onset_at`)
    NGAY SAU KHI merge mỗi lượt - phép tính THUẦN, không qua LLM (đúng lý do trong docstring
    `SymptomProtocol.derive_fields`)."""
    if protocol.derive_fields is None:
        return merged
    derived = protocol.derive_fields(merged)
    if not derived:
        return merged
    return {**merged, **derived}


# --- Ghép hướng C/E theo stage -----------------------------------------------------------------


@dataclass(slots=True)
class TurnResult:
    answers: dict[str, TriState] = field(default_factory=dict)
    extracted: dict[str, TriState] = field(default_factory=dict)
    agent_message: str = ""
    next_cluster: QuestionCluster | None = None
    next_stage: str = ""
    """Stage của `next_cluster` - có thể KHÁC stage vừa hỏi (cụm cuối stage đã được trả lời)."""
    stop_reason: str | None = None
    """Chỉ khác `None` khi không còn cụm nào để hỏi - session dùng để kết thúc phiên."""
    llm_used: bool = False
    emergency: bool = False
    answer_quality: str = _DEFAULT_ANSWER_QUALITY
    cluster_resolved: bool = True
    """Cụm vừa hỏi có thu được gì không. `False` = người dùng không trả lời được ý nào (input rác,
    né tránh) ⇒ session KHÔNG được đánh dấu cụm là xong, phải hỏi lại. Do CODE tính trên `answers`,
    không lấy từ `answer_quality` của LLM."""
    retried_same_cluster: bool = False
    """Lượt tới có hỏi LẠI đúng cụm này không. Session phải theo đúng quyết định này: nếu agent đã
    chọn đi tiếp (cụm chỉ còn field tuỳ chọn, không đáng hỏi lại) mà session vẫn để cụm ở trạng thái
    "chưa xong" thì `next_cluster` sẽ chọn lại chính nó ở lượt sau ⇒ lặp vô hạn."""
    reopened_cluster_ids: frozenset[str] = frozenset()
    """Cụm phải mở lại vì field bên trong vừa bị xoá (đính chính) hoặc đang mâu thuẫn."""
    screened_cluster_ids: frozenset[str] = frozenset()
    """Cụm được ĐÓNG bởi một verdict phủ định của lượt sàng lọc gộp - người bệnh đã nghe đọc danh
    sách dấu hiệu của chúng và trả lời không có. Session ghi chúng là đã hoàn tất, nhưng đếm chúng
    NGOÀI ngân sách câu hỏi: một lượt sàng lọc đóng 5 cụm mà chỉ tốn đúng một câu hỏi."""
    next_probe: tuple[ScreeningGroup, ...] = ()
    """Lượt tới là câu SÀNG LỌC GỘP cho các nhóm này (rỗng = câu hỏi cụm thường). Session phải giữ
    lại để lượt sau biết đọc câu trả lời theo verdict nhóm - đọc nhầm thành cụm thường sẽ không có
    đường nào đóng nhóm, và câu sàng lọc dài kia thành ra hỏi phí."""
    protocol_name: str = ""
    """Protocol sẽ chạy từ lượt sau. Chỉ khác rỗng ở lượt mở (`run_open_turn`), nơi protocol được
    CHỌN chứ không phải cho trước."""
    harvested_nothing: bool = False
    """Lượt mở không thu được field nào - tin nhắn quá nghèo ("xin chào", "."), phải hỏi lại câu mở
    thay vì lao vào bộ câu hỏi lâm sàng."""
    deferred_cluster_ids: frozenset[str] = frozenset()
    """Cụm ĐỦ ĐIỀU KIỆN hỏi nhưng thua điểm xếp hạng ở lượt này (§8.3). Session cộng vào
    `CoverageLedger` để cụm bị đẩy lùi mãi cuối cùng vẫn được hỏi - hoãn mà không ghi sổ là bỏ sót."""
    recent_fields: frozenset[str] = frozenset()
    """Field vừa thu được căn cứ từ chính tin nhắn này - nguồn của `relevance` ở lượt SAU."""
    dialogue_act: str = ""
    """Nhãn `DialogueAct` mà `DialoguePolicy` đã dùng - cho log và metric theo vai trò (§12)."""
    router_trigger: str = ""
    """Trigger §3.1 khiến lượt này ĐÁNG hỏi `symptom_group_router` (rỗng = không lượt nào). Chưa có
    model nào phía sau; đây là chỉ số để phát hiện sớm việc "chỉ gọi khi cần" trôi thành "gọi mọi lượt"."""
    pending_retraction: tuple[str, ...] = ()
    """Field mà việc xoá dây chuyền vừa bị GIỮ LẠI vì đính chính chưa đủ rõ (§5 quy tắc 5). Hồ sơ giữ
    nguyên giá trị cũ; session phải hỏi một câu xác nhận ngắn trước khi lời đính chính được ghi nhận."""
    audit: tuple[dict[str, object], ...] = ()
    """Nhật ký thay đổi hồ sơ của lượt này (`reducer.AuditEvent`). Không tham gia quyết định nào - nó
    tồn tại để trả lời được "vì sao field này mất giá trị" sau sự cố (§5 quy tắc 7)."""
    triage_level: str | None = None
    reason_codes: tuple[str, ...] = ()
    triggered_rules: tuple[str, ...] = ()


_QUESTION_ONLY_SYSTEM = """Bạn là điều dưỡng đang hỏi triệu chứng qua tin nhắn cho người bệnh/người nhà.

Hãy tự soạn MỘT tin nhắn tiếng Việt tự nhiên, ấm áp, ngắn gọn để hỏi {scope_intro} dưới đây.

ĐIỀU CẦN BIẾT (mỗi gạch đầu dòng là MỘT thông tin phải thu được - tự chọn cách hỏi):
{field_brief}

{script_block}{focus}

{subject_note}
ĐÃ BIẾT VỀ NGƯỜI BỆNH (TUYỆT ĐỐI không hỏi lại những điều này):
{known_facts}
{acknowledgement}{dialogue_note}{transition_note}
Vài lượt hội thoại gần đây nhất (để tránh lặp lại nguyên văn cách diễn đạt đã dùng trước đó):
{history}

QUY TẮC BẮT BUỘC:
- TUYỆT ĐỐI KHÔNG chẩn đoán bệnh, KHÔNG nêu tên bệnh, KHÔNG nhận định mức độ nguy hiểm.
- KHÔNG khuyên dùng thuốc, KHÔNG nêu liều, KHÔNG đưa hướng xử trí.
- {scope_rule}
- {instruction}
- {persona_rule}
- Hỏi thân mật nhưng đi thẳng vào ý cần hỏi. Tránh mẫu câu lặp lại như "mình đã ghi nhận",
  "để mình nắm rõ hơn", "để mình yên tâm hơn" nếu không thật sự cần.
- Nếu không có dữ kiện cần công nhận, bắt đầu thẳng bằng câu hỏi.
- Nói VỚI người bệnh (ngôi thứ hai), không nói VỀ họ ở ngôi thứ ba.
- KHÔNG chép lại nhãn kỹ thuật, tên trường dữ liệu, hay bất kỳ câu hướng dẫn nào ở trên.
- Chỉ trả về đúng nội dung tin nhắn, không thêm lời dẫn hay giải thích.

ĐỊNH DẠNG (tin nhắn chat, không phải tài liệu):
- Nếu có phần công nhận thông tin, viết tối đa 1 câu ngắn rồi xuống dòng sang câu hỏi. Nếu không có
  phần công nhận, chỉ viết câu hỏi.
- Từ hai ý hỏi trở lên thì tách gạch đầu dòng "- ", mỗi ý một dòng; một ý thì viết liền câu.
- KHÔNG in đậm, KHÔNG in nghiêng, KHÔNG bảng, KHÔNG tiêu đề "#", KHÔNG khối mã.
- Tối đa {max_questions} dấu hỏi trong cả tin nhắn."""
# Vì sao cấm in đậm/in nghiêng thay vì "dùng đúng chỗ": tin nhắn này đi qua `/chat/stream`, nên
# markdown phải hợp lệ THEO TỪNG MẨU. Mọi cú pháp cần ký tự đóng ở cuối (`**`, `` ` ``) hiện ra
# dưới dạng ký tự trần khi người bệnh mới nhận được nửa câu. Gạch đầu dòng và xuống dòng thì đóng
# bằng newline nên an toàn. `output_guard` kiểm lại đúng ràng buộc này.

# Hai biến thể của cùng một prompt. Lượt gộp phải nói RÕ số ý: bỏ dòng này thì model quen tay rút về
# một câu hỏi duy nhất, các ý còn lại không bao giờ được hỏi mà cụm tương ứng vẫn bị đánh dấu đã hỏi.
_SCRIPT_HINT_BLOCK = """Cách diễn đạt tham khảo của điều dưỡng (KHÔNG bắt buộc chép, PHẢI viết khác đi cho tự nhiên hơn):
"{script_hint}"
"""
"""Câu viết sẵn của CẢ cụm - chỉ được đưa vào prompt khi cụm còn thiếu TRỌN VẸN.

Cụm điền dở mà vẫn kèm khối này thì prompt chứa ba tín hiệu chọi nhau: (i) một câu tiếng Việt viết
sẵn hỏi CẢ cụm, (ii) dòng `CHỈ CÒN THIẾU` bảo đừng hỏi phần đã biết, (iii) `ĐÃ BIẾT VỀ NGƯỜI BỆNH`.
Model bám vào cái CỤ THỂ nhất - câu viết sẵn - nên nó hỏi lại đúng thứ người bệnh vừa khai.

Ca đo được (F10 lỗi 2): `CP-03` có `script_hint` = "Có kèm đau ngực, khó thở, ho ra máu..." mà
`chest_pain` đã "true" từ lượt mở, vì `chest_pain` nằm trong CẢ HAI cụm `CP-01` và `CP-03`. Đường rơi
về `script_hint` khi guard chặn hoặc `synthesis_enabled()` tắt KHÔNG bị ảnh hưởng - nó lấy
`cluster.script_hint` trực tiếp, không đi qua prompt."""


_SINGLE_SCOPE = ("Ý CẦN HỎI", "KHÔNG hỏi thêm ý nào ngoài Ý CẦN HỎI ở trên (tối đa 2 ý).")


def _batch_scope(parts: int) -> tuple[str, str]:
    return (
        f"{parts} Ý CẦN HỎI",
        f"Hỏi ĐỦ cả {parts} ý trên trong CÙNG một tin nhắn và KHÔNG thêm ý nào khác. Viết thành câu "
        "liền mạch tự nhiên như điều dưỡng hỏi chuyện, đừng chép lại danh sách đánh số.",
    )


def _field_brief(protocol: SymptomProtocol, keys: tuple[str, ...]) -> str:
    """Nhãn + gợi ý của từng field cần thu, cho renderer TỰ SOẠN câu thay vì chép `script_hint`.

    Vì sao đổi (2026-08-22): trước đây prompt chỉ đưa `script_hint` - một câu tiếng Việt viết cứng -
    nên model chỉ còn việc diễn đạt lại đúng câu đó. Không gian sáng tạo bằng 0 về mặt *hỏi cái gì*
    và rất hẹp về *hỏi thế nào*, và đó là nguồn của cảm giác "hỏi máy móc".

    RANH GIỚI KHÔNG NỚI: danh sách field này do `stage_machine` + `ranking` chốt, model KHÔNG chọn.
    Nó được tự do về cách nói, thứ tự các ý trong cùng một lượt và giọng điệu - không được tự do về
    việc hỏi field nào. `output_guard` check 4 chặn câu chạm field đã biết, và `EvidencePolicy` chặn
    việc điền field không có bằng chứng, nên nới ở đây không mở đường cho model bịa dữ kiện."""
    lines = []
    for key in keys:
        spec = protocol.fields_by_key.get(key)
        if spec is None:
            continue
        hint = (spec.hint or "").strip()
        lines.append(f"- {spec.label}" + (f" ({hint})" if hint else ""))
    return "\n".join(lines) if lines else "(không có ý nào)"


_SUBJECT_NOTES: dict[str, str] = {
    "self": 'Người có triệu chứng CHÍNH LÀ người bạn đang nhắn tin - hỏi thẳng "bạn".',
    "parent_caregiver": (
        "Người có triệu chứng là NGƯỜI NHÀ mà người nhắn đang chăm sóc, KHÔNG phải người nhắn. Hỏi "
        'về "bé"/"người nhà của bạn", đừng hỏi như thể người nhắn đang có triệu chứng đó.'
    ),
    "other": (
        "Người có triệu chứng là NGƯỜI KHÁC, không phải người đang nhắn tin. Hỏi về \"người bệnh\" "
        '("người bệnh có thấy...", "bạn của bạn có..."), TUYỆT ĐỐI đừng hỏi "bạn có bị... không".'
    ),
}
"""Chủ ngữ của câu hỏi, theo `reporter_type`.

Đây là chỗ Fix E và Fix F gặp nhau: Fix E chốt agent tự xưng "mình" và gọi người NHẮN là "bạn", còn
chỗ này chốt người nhắn có phải người BỆNH hay không. Thiếu nó thì persona nhất quán lại làm lỗi nặng
thêm - agent hỏi "bạn có đau ngực không" một cách rất kiên định với người vừa nói rõ là đang hỏi hộ
bạn mình."""


def _subject_note(answers: dict[str, TriState]) -> str:
    """Dòng chủ ngữ cho prompt, rỗng khi chưa biết ai là người bệnh.

    Rỗng chứ không mặc định `"self"`: chưa hỏi thì chưa biết, và đoán "người nhắn là bệnh nhân" chính
    là giả định ngầm sinh ra lỗi 4 của F10."""
    note = _SUBJECT_NOTES.get(str(answers.get("reporter_type") or ""))
    return f"\nCHỦ NGỮ CỦA CÂU HỎI: {note}\n" if note else ""


def _format_history(conversation: list[dict[str, str]], limit: int | None = None) -> str:
    """Cửa sổ hội thoại gửi cho model: bản tóm tắt phần cũ (nếu có) + `limit` lượt thô gần nhất.

    `limit` ĐỌC TỪ `context_compaction_keep_turns`, không viết cứng nữa. Hai con số này phải bằng
    nhau, và trước đây chúng chỉ *tình cờ* bằng nhau vì cả hai cùng là 6: `maybe_compact` chừa lại
    `keep_turns` lượt không nén, còn hàm này đọc 6 lượt cuối. Lượt nào vừa không bị nén vừa nằm
    ngoài 6 lượt cuối thì rơi vào VÙNG CHẾT - không có trong bản tóm tắt, cũng không có trong phần
    model đọc. Nó biến mất, và biến mất không kèm exception, không kèm log.

    Đo được: hội thoại 30 lượt, đặt `keep_turns=20` (hợp lệ, `Field(ge=2, le=40)`) thì 14 lượt giữa
    phiên bốc hơi khỏi tầm nhìn của model. Vặn núm lên với ý định cho model nhớ nhiều hơn lại làm nó
    nhớ ít đi - đúng kiểu hỏng mà một cấu hình "an toàn" gây ra.

    Lượt mang vai `compaction.ROLE_SUMMARY` được tách ra xử lý RIÊNG chứ không đi qua `[-limit:]`:
    nó là bản nén của hàng chục lượt trước đó, và để nó bị đẩy khỏi cửa sổ vì mấy lượt "vâng"/"không"
    mới nhất là đánh mất đúng thứ việc nén sinh ra để giữ (§4.9 M2)."""
    limit = get_settings().context_compaction_keep_turns if limit is None else limit
    summary = " ".join(
        str(turn.get("content", "")).strip()
        for turn in conversation
        if turn.get("role") == compaction.ROLE_SUMMARY
    ).strip()
    turns = [turn for turn in conversation if turn.get("role") != compaction.ROLE_SUMMARY]
    if not turns and not summary:
        return "(chưa có lượt nào trước đó)"
    lines = [f"(tóm tắt các lượt trước đó) {summary}"] if summary else []
    lines += [
        f"{'Người bệnh' if turn.get('role') == 'user' else 'Trợ lý'}: {turn.get('content', '')}"
        for turn in turns[-limit:]
    ]
    return "\n".join(lines)


# temperature cao hơn CHỈ dùng cho bước "diễn đạt lại câu hỏi" - không trích xuất field ở đây nên
# không đánh đổi độ chính xác. temperature=0 khiến LLM trả gần như Y HỆT một câu cho cùng 1
# script_hint mỗi lần, làm hội thoại cảm giác "học thuộc lòng" (phát hiện qua test tay với LLM thật).
def _emit_static(on_token: TokenSink | None, text: str) -> None:
    """Phát một câu TĨNH ra kênh streaming ngay khi nó được chọn.

    Câu tĩnh không cần chờ model, nên nó là câu đến được màn hình NHANH NHẤT trong cả hệ - nhưng
    trước đây nó lại là câu duy nhất không đi qua `on_token`, nên người bệnh phải đợi hết lượt
    (rule engine, chốt triage, lưu case) rồi mới đọc được nó trong sự kiện `done`. Nghịch lý: câu
    rẻ nhất lại hiện chậm nhất.

    Phát nguyên một mẩu chứ không cắt nhỏ giả vờ: chữ đã có sẵn đủ, chia nhỏ ra để trông giống đang
    gõ là làm chậm một cách cố ý."""
    if on_token is not None and text:
        on_token(text)


def _visible_text(raw: str) -> str:
    """Phần ĐẦU của output model sẽ thật sự hiện ra cho người bệnh, bỏ rác mở đầu.

    Tồn tại vì streaming cần một hệ toạ độ ỔN ĐỊNH. Bản gom-trọn cũ chỉ cần `raw.strip().strip('"')`
    một lần ở cuối, nhưng khi phát dần thì mỗi mẩu được cắt theo CHỈ SỐ, mà `strip()` ở cuối lại dịch
    toàn bộ chỉ số nếu model mở đầu bằng khoảng trắng hoặc một dấu nháy. Lệch một ký tự ở đây nghĩa là
    người bệnh đọc một câu mất chữ đầu hoặc lặp chữ.

    Chỉ gỡ ĐẦU, không gỡ đuôi: đuôi còn đang được viết tiếp, `rstrip` giữa chừng sẽ cắt mất khoảng
    trắng ngăn từ rồi mẩu sau dính liền vào từ trước."""
    return raw.lstrip().lstrip('"')


_QUESTION_TEMPERATURE = 0.7

# Số lần hỏi lại tối đa cho MỘT cụm trước khi bỏ qua.
#
# Chốt UX 2026-08-22: hỏi một cụm đúng MỘT LẦN. Người bệnh thường chỉ trả lời những ý họ có/nhớ;
# phần đã hỏi mà họ không nhắc tới giữ nguyên `unknown` và cụm được đóng dưới dạng unresolved, thay
# vì hỏi lại làm hội thoại dài và lạc nhịp.
MAX_RETRIES_PER_CLUSTER = 0


def _worth_retrying(protocol: SymptomProtocol, cluster: QuestionCluster, answers: dict[str, TriState]) -> bool:
    """Cụm chưa thu được gì có ĐÁNG hỏi lại không.

    Chỉ hỏi lại khi còn thiếu field BẮT BUỘC (tier ngoài O/H). Cụm chỉ còn field làm giàu/bàn giao thì
    hỏi lại là phí lượt: người dùng đã im lặng một lần, ép hỏi thêm 2 lần nữa không đổi được kết luận
    lâm sàng nào - trong khi mỗi cụm ×3 lượt khiến ca lành tính (đa số cụm không có gì để nói) dài gấp
    ba, tới mức không kết thúc nổi (đo được: ca H1/V1 Part 8 vượt 60 lượt vẫn chưa xong).

    Cùng tiêu chí tier với `stage_machine._cluster_is_optional_tier` - ngân sách cũng chỉ được cắt cụm
    thuần O/H, nên hai cơ chế nhất quán về "cụm nào được phép bỏ qua"."""
    return any(
        not stage_machine.is_filled(answers.get(key)) and protocol.fields_by_key[key].tier not in ("O", "H")
        for key in cluster.fields
    )


def _generate_question(
    protocol: SymptomProtocol,
    cluster: QuestionCluster,
    *,
    answers: dict[str, TriState],
    plan: dialogue.ResponsePlan | None = None,
    missing_keys: tuple[str, ...] = (),
    rephrase: bool = False,
    parts: int = 1,
    conversation: list[dict[str, str]] | None = None,
    credential: provider_router.LLMCredential | None,
    on_token: TokenSink | None = None,
) -> tuple[str, bool]:
    """Call LLM thứ hai: CHỈ diễn đạt `ResponsePlan` cho cụm mà RULE đã chọn. Trả `(câu, llm_used)`.

    LLM không được chọn cụm ở đây - nó chỉ nhận `cluster` đã chốt. Đây là ranh giới quan trọng nhất
    của kiến trúc: kiến trúc cũ để LLM vừa trích xuất vừa tự chọn câu kế tiếp trong 1 call, nên khi
    code phát hiện lựa chọn sai và ép về cụm đúng thì CÂU HỎI vẫn là câu viết cho cụm bị loại - người
    dùng bị hỏi X trong khi lượt sau hệ thống trích theo schema Y.

    Kết quả đi qua `output_guard` TRƯỚC khi ra ngoài; fail thì rơi về `script_hint` tất định."""
    if not cluster.script_hint:
        return "", False
    if not flags.synthesis_enabled():
        # Công tắc ngắt (§9 P4 mục 5): phát nguyên văn `script_hint`. Đây đúng là đường mà
        # `output_guard` rơi về khi model viết sai, nên nhánh này không phải code chưa ai chạy.
        return cluster.script_hint, False

    missing = plan.missing_fields if plan is not None else missing_keys
    partial = bool(missing) and len(missing) < len(cluster.fields)
    focus = ""
    if partial:
        labels = ", ".join(
            protocol.fields_by_key[key].label for key in missing if key in protocol.fields_by_key
        )
        if labels:
            focus = f"\nCHỈ CÒN THIẾU (đừng hỏi lại phần đã biết): {labels}"

    wants_rephrase = rephrase or (plan.rephrase if plan is not None else False)
    instruction = (
        "Người bệnh vừa KHÔNG trả lời được ý này. Hãy đổi CẤU TRÚC CÂU và cách dẫn dắt so với lần "
        "trước, nói ngắn gọn vì sao cần biết điều đó. Đại từ xưng hô giữ NGUYÊN."
        if wants_rephrase
        # "Viết khác đi" bị thu về đúng CẤU TRÚC CÂU: chỉ thị cũ nói trống "đổi từ ngữ", mà đại từ
        # cũng là từ ngữ - đó là đường model hợp lý hoá việc đổi "mình" thành "em" giữa phiên.
        else (
            "Diễn đạt KHÁC đi so với các câu hỏi trước đó của trợ lý: đổi CẤU TRÚC CÂU và cách dẫn "
            "dắt. KHÔNG đổi đại từ xưng hô."
        )
    )

    scope_intro, scope_rule = _batch_scope(parts) if parts > 1 else _SINGLE_SCOPE
    acknowledge = plan.acknowledge if plan is not None else ""
    # Field cho renderer: phan CON THIEU neu biet, khong thi ca cum.
    brief_keys = tuple(missing) if missing else tuple(cluster.fields)
    system_prompt = _QUESTION_ONLY_SYSTEM.format(
        field_brief=_field_brief(protocol, brief_keys),
        scope_intro=scope_intro,
        scope_rule=scope_rule,
        # Cụm điền dở: dựng câu từ `_field_brief` của riêng phần còn thiếu, KHÔNG kèm câu viết sẵn
        # hỏi cả cụm - xem `_SCRIPT_HINT_BLOCK`.
        script_block="" if partial else _SCRIPT_HINT_BLOCK.format(script_hint=cluster.script_hint),
        focus=focus,
        known_facts=_known_facts(protocol, answers),
        # Hướng dẫn và DỮ KIỆN đi riêng: gộp chúng vào một chuỗi thì model chép nguyên văn phần
        # hướng dẫn ngôi thứ ba ra tin nhắn (đo được trên transcript thật với deepseek-chat).
        acknowledgement=(
            f"\n{plan.acknowledge_instruction} Dữ kiện vừa nhận được, diễn đạt lại bằng lời của bạn "
            f'(KHÔNG chép nguyên văn nhãn): "{acknowledge}"'
            if acknowledge and plan is not None and plan.acknowledge_instruction
            else ""
        ),
        dialogue_note=f"\n{plan.answer_user_question}" if plan is not None and plan.answer_user_question else "",
        transition_note=f"\n{plan.transition_note}" if plan is not None and plan.transition_note else "",
        instruction=instruction,
        persona_rule=phrasing.PERSONA_RULE,
        subject_note=_subject_note(answers),
        history=_format_history(conversation or []),
        max_questions=plan.max_questions if plan is not None else max(parts, 1),
    )
    messages = [{"role": "user", "content": system_prompt}]
    try:
        if on_token is None:
            result = provider_router.complete(
                messages, temperature=_QUESTION_TEMPERATURE, credential=credential,
                role=provider_router.ROLE_SYNTHESIS,
            )
            question = result.text.strip().strip('"')
        else:
            # Chỉ bước NÀY được stream, và chỉ vì nó là văn bản người bệnh đọc. Lượt trích xuất trả
            # JSON - JSON dở dang thì không parse được nên streaming ở đó không giúp gì.
            #
            # PHÁT DẦN, NHƯNG CHỈ PHÁT PHẦN ĐÃ QUA GUARD. Bản trước gom trọn rồi mới phát một cục, vì
            # §6.5 đòi `output_guard` chạy TRƯỚC khi người bệnh đọc được chữ nào - đúng, và ràng buộc
            # đó vẫn được giữ nguyên ở đây. Thứ đổi là cách giữ nó: mọi vi phạm NGUY HIỂM của guard
            # (tên bệnh, lời khuyên điều trị, hỏi lại field đã biết, markdown hỏng, thừa dấu hỏi) đều
            # ĐƠN ĐIỆU - đã vi phạm thì viết thêm không hết - nên `check_prefix` phán được ngay trên
            # câu viết dở. Chữ chỉ rời khỏi đây sau khi tiền tố chứa nó đã sạch.
            #
            # GIỮ LẠI ĐUÔI `PREFIX_SAFE_TAIL` ký tự: không giữ thì một cụm cấm bị cắt đôi giữa hai mẩu
            # sẽ phát nửa đầu ra màn hình trước khi có đủ chữ để nhận ra nó.
            pieces: list[str] = []
            emitted = 0
            blocked = False
            for piece in provider_router.complete_stream(
                messages, temperature=_QUESTION_TEMPERATURE, credential=credential,
                role=provider_router.ROLE_SYNTHESIS,
            ):
                pieces.append(piece)
                draft = _visible_text("".join(pieces))
                if not output_guard.check_prefix(
                    draft, plan=plan, protocol=protocol, cluster=cluster, answers=answers
                ):
                    # Dừng ĐỌC luôn, không chỉ dừng phát: phần còn lại của một câu đã hỏng thì không
                    # có giá trị gì, mà vẫn tính tiền token.
                    blocked = True
                    break
                if on_token is not None:
                    safe_upto = len(draft) - output_guard.PREFIX_SAFE_TAIL
                    if safe_upto > emitted:
                        on_token(draft[emitted:safe_upto])
                        emitted = safe_upto
            question = "" if blocked else _visible_text("".join(pieces)).rstrip().rstrip('"').rstrip()
        if question and _passes_output_guard(question, protocol, cluster, plan, answers):
            if on_token is not None:
                # Phát nốt phần đuôi đã giữ lại - câu giờ đã hoàn chỉnh và qua guard ĐẦY ĐỦ.
                #
                # `emitted` đếm trên `_visible_text`, cùng một gốc với `question`, nên hai chuỗi khớp
                # tiền tố. `min` là lưới an toàn cho trường hợp model kết thúc bằng cả một khối
                # khoảng trắng dài hơn phần đuôi giữ lại: lúc đó `question` ngắn hơn `emitted` và cắt
                # thẳng sẽ ném. Cắt lố chỉ làm mất phần đã hiện, không bao giờ phát trùng.
                on_token(question[min(emitted, len(question)):])
            return question, True
    except Exception as exc:
        logger.warning("symptom_intake.question_failed reason=%s", type(exc).__name__)
    if on_token is not None:
        on_token(cluster.script_hint)
    return cluster.script_hint, False


# Tên public cho `session` gọi ở lượt BỎ extractor (§7.4): lượt đó không đi qua `run_turn` nhưng vẫn
# phải phát ra một câu hỏi, và câu đó vẫn phải qua `output_guard` như mọi câu khác.
generate_question = _generate_question


def _passes_output_guard(
    question: str,
    protocol: SymptomProtocol,
    cluster: QuestionCluster,
    plan: dialogue.ResponsePlan | None,
    answers: dict[str, TriState],
) -> bool:
    """Không có plan thì không có hợp đồng để kiểm - đường này chỉ còn ở caller cũ/test."""
    if plan is None:
        return True
    result = output_guard.check(question, plan=plan, protocol=protocol, cluster=cluster, answers=answers)
    if not result.ok:
        logger.warning(
            "symptom_intake.output_guard_blocked cluster=%s violations=%s",
            cluster.id, ",".join(result.violations),
        )
    return result.ok


def _recent_fields(*sources: dict[str, TriState]) -> frozenset[str]:
    """Field vừa thu được căn cứ TỪ CHÍNH tin nhắn này - thành phần `relevance` của xếp hạng (§8.4).

    Chỉ nhận giá trị XÁC ĐỊNH: `unknown` nghĩa là model không trích được gì, không phải người bệnh
    vừa nhắc tới field đó. Cố ý KHÔNG gồm giá trị âm tính của lượt sàng lọc gộp - một câu "không có
    gì trong số đó" đóng cả nhóm chứ không phải người bệnh đang kể về nhóm ấy."""
    return frozenset(
        key
        for source in sources
        for key, value in source.items()
        if stage_machine.is_filled(value)
    )


def _ranking_context(
    recent_fields: frozenset[str], ledger: coverage.CoverageLedger | None, recent_text: str = "",
) -> ranking.RankingContext | None:
    if not flags.ranking_enabled():
        # `None` là đúng đường quay lui của §8.3, không phải một nhánh mới: `select_cluster` không có
        # tín hiệu nào để chấm thì mọi cụm hoà điểm, và hoà điểm giữ nguyên thứ tự khai báo - tức
        # first-fit cũ. Cả hai hành vi dùng chung một đoạn code.
        return None
    if ledger is None:
        return ranking.RankingContext(recent_fields=recent_fields, recent_text=recent_text)
    return ranking.RankingContext(
        recent_fields=recent_fields, recent_text=recent_text,
        deferred=dict(ledger.deferred), overdue=ledger.overdue_ids(),
    )


def _stop_requested(stop_signals: stage_machine.StopSignals) -> bool:
    """Người bệnh đã nói rõ họ muốn dừng chưa.

    Cần riêng một hàm vì nhánh HỎI LẠI CỤM CŨ đi VÒNG QUA `advance` (`Advance(cluster, stage, None)`)
    - nó là đường duy nhất trong `run_turn` không đi qua `should_stop`. Không chặn ở đây thì người
    bệnh nói "tôi không trả lời nữa" đúng lượt cụm đang được hỏi lại sẽ bị hỏi lại y hệt câu vừa từ
    chối. `no_more_symptoms` KHÔNG nằm trong đây: nó là tín hiệu mềm và `should_stop` mới đủ dữ kiện
    (cụm chưa hỏi mang field M0/M1) để quyết."""
    return not stop_signals.user_can_continue or stop_signals.uncooperative


def run_turn(
    protocol: SymptomProtocol,
    session_id: str,
    *,
    turn: int,
    stage: str,
    cluster: QuestionCluster,
    message: str,
    answers: dict[str, TriState],
    protocol_name: str = "",
    on_token: TokenSink | None = None,
    asked_ids: frozenset[str] = frozenset(),
    retry_count: int = 0,
    conversation: list[dict[str, str]] | None = None,
    credential: provider_router.LLMCredential | None = None,
    select_protocol=None,
    protocol_for=None,
    protocol_candidates=None,
    probe: tuple[ScreeningGroup, ...] = (),
    screened_ids: frozenset[str] = frozenset(),
    screening_history: dict[str, tuple[frozenset[str], ...]] | None = None,
    ledger: coverage.CoverageLedger | None = None,
    confirmed_retractions: frozenset[str] = frozenset(),
    stop_signals: stage_machine.StopSignals = stage_machine.NO_STOP_SIGNALS,
) -> TurnResult:
    """Một lượt hỏi-đáp. MỘT luồng duy nhất cho mọi stage (không còn chia hướng C/E):

        extract  ->  merge  ->  mâu thuẫn/đính chính  ->  derive  ->  rule_engine
                 ->  [EMERGENCY? dừng ngay, thông điệp tĩnh]
                 ->  next_cluster (THUẦN RULE)  ->  render câu hỏi

    Vì sao 2 call thay vì 1: cụm kế tiếp chỉ tính được SAU khi biết kết quả trích xuất lượt này. Bản
    cũ lách bằng cách tính trước cụm kế tiếp trên `answers` CŨ (look-ahead), nên lời đính chính của
    người dùng ở chính lượt đó không kịp ảnh hưởng - đúng bug "nói không sốt vẫn bị hỏi sốt bao lâu".

    `cluster`: cụm mà `message` đang trả lời.
    `asked_ids`: cụm KHÔNG được chọn lại (đã hoàn tất + đã bỏ dở không giải quyết được).
    `probe`: khác rỗng ⇒ `cluster` là cụm sàng lọc TỔNG HỢP và `message` đang trả lời câu hỏi gộp
    liệt kê các nhóm này (xem `screening.py`).
    """
    credential = credential or protocol.default_credential
    stage_log.step(
        session_id, turn=turn, stage=stage, cluster_id=cluster.id, event="user_message",
        input=None, output={"text": message},
    )

    if probe:
        # `lookahead=0`: field của các cụm sắp hỏi ĐÃ nằm trong `cluster.fields` của cụm sàng lọc
        # (chính các nhóm đang được quét), thêm nữa chỉ làm schema phình ra - mà schema càng rộng thì
        # model càng có xu hướng điền bừa cho đủ, đúng cơ chế của lỗi C1.
        safety_keys = _safety_extra_keys(protocol, stage, cluster, answers, asked_ids, lookahead=0)
        extraction, outcome = extract_probe_turn(
            protocol, cluster, probe, message, answers=answers, safety_keys=safety_keys,
            session_id=session_id, turn=turn, stage=stage, credential=credential,
        )
    else:
        safety_keys = _safety_extra_keys(protocol, stage, cluster, answers, asked_ids)
        extraction = extract_turn(
            protocol, cluster, message, answers=answers, safety_keys=safety_keys,
            session_id=session_id, turn=turn, stage=stage, credential=credential,
        )
        outcome = None

    opportunistic = scan_opportunistic_fields(protocol, message)
    # Giá trị âm tính của lượt sàng lọc đứng TRƯỚC field trích được: người bệnh nói rõ một chi tiết
    # ("có, bé không tiểu từ sáng") phải thắng phủ định gộp của chính nhóm đó.
    screened_negatives = outcome.negatives if outcome is not None else {}
    screened_positives = outcome.positives if outcome is not None else {}
    recent_fields = _recent_fields(opportunistic, extraction.safety_fields, extraction.cluster_fields)

    # L3 REDUCER - nguồn sự thật DUY NHẤT của hồ sơ (§5). Đính chính + mâu thuẫn nằm TRONG nó và vì
    # thế chạy TRƯỚC rule_engine: nếu chạy sau, mức triage của chính lượt này được tính trên hồ sơ còn
    # rác (vd đã nói "không sốt" nhưng `temp_c=39` vẫn còn trong answers).
    # §4.8: ý tier O/H bị bỏ qua trong một lượt hỏi GỘP được suy `false`. Đứng ĐẦU danh sách sự
    # kiện = ưu tiên THẤP NHẤT: mọi nguồn thật (quét từ khoá, verdict sàng lọc, trích xuất) đều ghi
    # đè lên nó. Field M0/M1/an toàn không bao giờ có mặt ở đây - xem `skipped_field_defaults`.
    batch_defaults = (
        batching.skipped_field_defaults(
            protocol, cluster, answers,
            information_gain=any(
                stage_machine.is_filled(value) for value in extraction.cluster_fields.values()
            ),
        )
        if batching.is_batch(cluster)
        else {}
    )
    reduced = reducer.reduce(
        protocol, answers,
        (
            *reducer.events_from_values(batch_defaults, source=reducer.SOURCE_BATCH_DEFAULT),
            *reducer.events_from_values(opportunistic, source=reducer.SOURCE_KEYWORD),
            *reducer.events_from_values(screened_negatives, source=reducer.SOURCE_SCREENING),
            # Dương tính suy từ verdict đứng SAU âm tính: khi một nhóm vừa bị phủ định gộp vừa có một
            # dấu hiệu được xác nhận, lời khẳng định thắng. Vẫn đứng TRƯỚC `extraction.events` để
            # field model trích được nguyên văn ghi đè lên phần suy luận.
            *reducer.events_from_values(screened_positives, source=reducer.SOURCE_SCREENING),
            *extraction.events,
        ),
        confirmed_retractions=confirmed_retractions,
    )
    merged, reopened, contradicted = reduced.answers, reduced.reopened_clusters, reduced.contradicted
    if reduced.audit:
        stage_log.step(
            session_id, turn=turn, stage=stage, cluster_id=cluster.id, event="extract",
            input=None, output={"audit": [event.as_dict() for event in reduced.audit]},
        )
    # Cụm vừa bị đính chính mở lại thì KHÔNG được tính là đã đóng bởi sàng lọc: field bên trong vừa bị
    # xoá hoặc đang chọi nhau, phải hỏi cho rõ dù người bệnh đã phủ định cả nhóm ở đầu lượt.
    screened_closed = (outcome.closed_cluster_ids if outcome is not None else frozenset()) - reopened
    if reopened:
        stage_log.step(
            session_id, turn=turn, stage=stage, cluster_id=cluster.id, event="extract",
            input=None, output={"reopened_clusters": sorted(reopened), "contradicted": sorted(contradicted)},
        )

    # ĐỔI PROTOCOL GIỮA CHỪNG - phải nằm SAU đính chính/xoá dây chuyền và TRƯỚC rule engine. Sau, vì
    # căn cứ để đổi chính là hồ sơ đã được đính chính ("à tôi nhầm, tôi không sốt" phải xoá phần sốt
    # rồi mới hỏi lại protocol nào hợp). Trước, vì kết luận triage của chính lượt này phải do luật của
    # protocol MỚI chấm - chấm bằng luật cũ rồi mới đổi là kết luận trên một hồ sơ không còn tồn tại.
    active = protocol
    protocol_switched = False
    if select_protocol is not None and protocol_for is not None:
        current_name = protocol_name or protocol.name
        chosen = select_protocol(merged, current_name)
        if chosen != current_name:
            active = protocol_for(chosen)
            protocol_switched = True
            merged = _apply_derived_fields(active, merged)
            stage_log.step(
                session_id, turn=turn, stage=stage, cluster_id=cluster.id, event="rule_gate",
                input=None, output={"protocol_switched_to": chosen, "from": current_name},
            )

    with stage_log.tool(
        session_id, turn=turn, stage=stage, cluster_id=cluster.id,
        tool="rule_engine.evaluate", input=merged,
    ) as rec:
        rule_result = rule_engine.evaluate(active, merged)
        rec.output = {
            "triage_level": rule_result.triage_level,
            "reason_codes": list(rule_result.reason_codes),
            "triggered_rules": list(rule_result.triggered_rules),
        }

    is_emergency = rule_result.triage_level == "EMERGENCY"
    stage_log.step(
        session_id, turn=turn, stage=stage, cluster_id=cluster.id, event="rule_gate",
        input=None, output={"triage_level": rule_result.triage_level},
        stop_reason="RED_FLAG" if is_emergency else None,
    )

    if is_emergency:
        # P0-5: dừng NGAY, không hỏi nốt checklist. Thông điệp TĨNH, không qua LLM (P0-2).
        stage_log.step(
            session_id, turn=turn, stage=stage, cluster_id=cluster.id, event="agent_message",
            input=None, output={"text": active.patient_red_flag_message}, llm_used=False,
        )
        stage_log.step(
            session_id, turn=turn, stage=stage, cluster_id=cluster.id, event="stop", stop_reason="RED_FLAG",
        )
        return TurnResult(
            answers=merged, extracted=extraction.all_fields, agent_message=active.patient_red_flag_message,
            next_cluster=None, llm_used=True, emergency=True,
            protocol_name=active.name if protocol_switched else "",
            answer_quality=extraction.answer_quality, reopened_cluster_ids=reopened,
            screened_cluster_ids=screened_closed,
            audit=reduced.audit_log,
            triage_level=rule_result.triage_level,
            reason_codes=rule_result.reason_codes, triggered_rules=rule_result.triggered_rules,
        )

    # Cụm coi là XONG khi (a) mọi field của nó đã có giá trị, HOẶC (b) lượt này thu được ít nhất một
    # field của nó. Nhánh (b) cần vì nhiều cụm có field tuỳ chọn không bao giờ điền hết (vd
    # `antipyretic_drug` khi chưa uống thuốc) - thiếu nó thì cụm nào cũng bị hỏi lại tới hết retry.
    # KHÔNG dùng `answer_quality` của LLM làm điều kiện: đó là nhãn model tự gán, không đáng tin cho
    # một quyết định điều khiển luồng.
    cluster_resolved = all(
        stage_machine.is_filled(merged.get(key)) for key in cluster.fields
    ) or any(stage_machine.is_filled(extraction.cluster_fields.get(key)) for key in cluster.fields)

    # Hỏi lại ĐÚNG cụm cũ phải quyết định Ở ĐÂY, trước khi sinh câu hỏi - nếu để tầng session ép sau
    # thì câu hỏi đã được viết cho cụm khác.
    # Vừa đổi protocol thì KHÔNG hỏi lại cụm cũ: cụm đó thuộc protocol trước, hỏi lại nó bây giờ là
    # kéo người bệnh về nhánh câu hỏi vừa bị bỏ.
    retry_this_cluster = (
        not cluster_resolved
        and not protocol_switched
        and retry_count < MAX_RETRIES_PER_CLUSTER
        and _worth_retrying(active, cluster, merged)
    )
    if probe or batching.is_batch(cluster) or common_screening.is_routing_disambiguation(cluster):
        # Lượt sàng lọc và lượt hỏi gộp KHÔNG BAO GIỜ hỏi lại nguyên gói. Người bệnh vừa nghe nhiều ý
        # một lúc mà không trả lời được thì đọc lại đúng loạt ý đó lần nữa chỉ làm họ bỏ cuộc. Đường
        # lùi đúng là quay về hỏi từng cụm một theo script chuẩn - `advance` tự làm điều đó khi cụm
        # tổng hợp được đánh dấu xong, và `batching.already_batched` chặn việc gói lại y hệt.
        #
        # Đánh dấu "xong" ở đây chỉ áp cho MÃ GÓI (một mã tổng hợp, sống đúng một lượt). Cụm thật bên
        # trong vẫn đóng/mở theo DỮ LIỆU như mọi cụm khác - không có sổ sách song song nào.
        cluster_resolved = True
        retry_this_cluster = False

    with stage_log.tool(
        session_id, turn=turn, stage=stage, cluster_id=cluster.id,
        tool="stage_machine.next_cluster", input={"stage": stage},
    ) as rec:
        # `advance` chứ không phải `next_cluster`: cụm kế tiếp có thể nằm ở stage SAU, và câu hỏi
        # phải được sinh cho ĐÚNG cụm đó ngay trong lượt này. Để session tự nhảy stage sau khi
        # `run_turn` trả về thì lượt này không có câu hỏi nào cả (tin nhắn rỗng).
        #
        # Sau khi đổi protocol thì duyệt lại TỪ ĐẦU với `asked_ids` RỖNG: mã cụm dùng chung giữa các
        # protocol (`Q3-03` là cụm co giật ở cả hai), nên mang tập "đã hỏi" của protocol cũ sang sẽ
        # bỏ qua nhầm cụm của protocol mới. Cụm nào thực sự đã có đủ dữ liệu vẫn bị `next_cluster` bỏ
        # qua theo DỮ LIỆU (`_cluster_needs_answer`), nên không ai bị hỏi lại điều đã trả lời.
        closed_now = (asked_ids | {cluster.id} | screened_closed) - reopened
        # Thứ tự hỏi phản ứng lại điều người bệnh VỪA nói (§8.4). Cơ chế thu hoạch cơ hội đã có sẵn -
        # cái thiếu là thứ tự chưa đi theo nó. Đổi protocol thì bỏ ledger cũ: mã cụm dùng chung giữa
        # các protocol nên nợ của protocol cũ sẽ gán nhầm cụm của protocol mới.
        ranking_context = _ranking_context(
            recent_fields, None if protocol_switched else ledger, message,
        )
        route_candidates = protocol_candidates(merged) if protocol_candidates is not None else ()
        disjoint_candidates = tuple(
            name for name in route_candidates if name not in {"chest_pain", "breathing"}
        )
        needs_disambiguation = (
            bool(probe)
            and stage == active.critical_scan_stage
            and len(route_candidates) >= 2
            and not (set(route_candidates) <= {"chest_pain", "breathing"})
            and merged.get("primary_symptom_group") in (None, "", "unknown")
            and len(disjoint_candidates) >= 1
        )
        if needs_disambiguation:
            step = stage_machine.Advance(
                common_screening.routing_disambiguation_cluster(route_candidates), stage, None,
            )
        elif protocol_switched:
            # `asked_ids` RỖNG là đúng (mã cụm dùng chung giữa các protocol), nhưng `asked_count`
            # thì KHÔNG được rỗng theo. Bỏ trống nó khiến `advance` tính `len(asked_ids) = 0`, tức
            # phiên được cấp lại TRỌN VẸN 13-16 cụm mỗi lần đổi protocol - đo được: một phiên trôi
            # nhóm giữa chừng hỏi tới 26-30 cụm. Ngân sách là ngân sách KIÊN NHẪN CỦA NGƯỜI BỆNH,
            # không phải của protocol; đổi protocol không làm họ có thêm kiên nhẫn.
            step = stage_machine.advance(
                active, active.stage_order[0], merged, known_triage_level=rule_result.triage_level,
                asked_count=len(closed_now - (screened_ids | screened_closed)),
                context=ranking_context, stop_signals=stop_signals,
            )
        elif retry_this_cluster and not _stop_requested(stop_signals):
            step = stage_machine.Advance(cluster, stage, None)
        else:
            step = stage_machine.advance(
                active, stage, merged,
                asked_ids=closed_now,
                context=ranking_context,
                # CS §6.5 tính ngân sách theo CỤM CÂU HỎI, không phải field đơn lẻ - và một lượt sàng
                # lọc là ĐÚNG MỘT câu hỏi dù nó đóng 5 cụm. Không trừ ra thì ca lành tính vừa được rút
                # ngắn lại bị coi như đã tiêu gần hết ngân sách và bị cắt ở Stage 5.
                asked_count=len(closed_now - (screened_ids | screened_closed)),
                known_triage_level=rule_result.triage_level,
                stop_signals=stop_signals,
            )
        following = step.cluster
        rec.output = {
            "cluster_id": following.id if following else None,
            "stage": step.stage, "stop_reason": step.stop_reason, "retry": retry_this_cluster,
        }

    next_probe: tuple[ScreeningGroup, ...] = ()
    if following is not None and not protocol_switched and not retry_this_cluster:
        next_probe = screening.next_probe(
            active, step.stage, merged, following,
            closed_ids=closed_now,
            history=(screening_history or {}).get(step.stage, ()),
        )
        if next_probe:
            following = screening.probe_cluster(active, step.stage, next_probe)

    # Gộp 2-3 cụm thường vào một tin nhắn. Đứng SAU nhánh sàng lọc vì hai cơ chế loại trừ nhau:
    # sàng lọc lo `gate_stages` (phủ định hàng loạt, văn bản tĩnh), gộp lo phần còn lại (hỏi thẳng,
    # qua LLM). Không gộp khi đang hỏi lại một cụm - lúc đó việc cần làm là diễn đạt lại cho rõ, thêm
    # ý mới chỉ làm người bệnh khó trả lời hơn.
    batched: tuple[QuestionCluster, ...] = ()
    if (
        following is not None
        and not next_probe
        and not retry_this_cluster
        and not common_screening.is_routing_disambiguation(following)
    ):
        batched = batching.next_batch(
            active, step.stage, merged, following,
            asked_ids=frozenset() if protocol_switched else closed_now,
        )
        if batched:
            following = batching.batch_cluster(step.stage, batched)

    # `DialoguePolicy` chạy SAU khi rule engine + stage machine đã chốt cụm, và TRƯỚC renderer: nó
    # quyết định NÓI GÌ về lượt vừa rồi (công nhận, trả lời câu hỏi ngược, câu chuyển hướng), còn
    # renderer chỉ viết câu. Lượt sàng lọc gộp KHÔNG có plan - văn bản của nó là tĩnh theo thiết kế.
    plan = (
        None
        if next_probe
        else dialogue.build_response_plan(
            active, following,
            act=dialogue.dialogue_act_from_quality(
                extraction.answer_quality, new_symptom=protocol_switched,
            ),
            answers=merged,
            recent_fields=recent_fields,
            protocol_switched=protocol_switched,
            rephrase=retry_this_cluster,
            parts=len(batched) or 1,
            # `protocol` (không phải `active`) là bản đã nới thêm field nhận diện protocol khác, nên
            # nó tra được nhãn của chính dữ kiện vừa làm phiên đổi hướng.
            label_protocol=protocol,
        )
    )

    # Cổng router: tính SAU trích xuất vì ba trong bốn trigger cần biết lượt này thu được gì.
    # `protocol_ruled_out` suy từ act `correction` + protocol vừa đổi - đó chính là hình dạng của
    # `registry._fever_ruled_out` nhìn từ đây (người bệnh RÚT lời khai, không phải nêu thêm).
    router_trigger = controller.should_consult_group_router(
        is_opening=False,
        act=plan.act if plan is not None else dialogue.DialogueAct.ANSWER,
        recent_fields=recent_fields,
        chief_complaint_field=active.chief_complaint_field,
        protocol_ruled_out=protocol_switched and plan is not None and plan.act is dialogue.DialogueAct.CORRECTION,
    )

    if next_probe:
        # Câu sàng lọc là văn bản TĨNH, không qua LLM - xem `screening.probe_question`.
        question, question_llm_used = following.script_hint, False
        _emit_static(on_token, question)
    else:
        question, question_llm_used = (
            _generate_question(
                active, following, answers=merged, plan=plan,
                rephrase=retry_this_cluster,
                parts=len(batched) or 1,
                conversation=conversation, credential=credential, on_token=on_token,
            )
            if following is not None
            else ("", False)
        )
    stage_log.step(
        session_id, turn=turn, stage=stage, cluster_id=cluster.id, event="agent_message",
        input=None, output={
            "text": question,
            "dialogue_act": plan.act.value if plan is not None else None,
            "max_questions": plan.max_questions if plan is not None else None,
        },
        llm_used=question_llm_used,
    )

    return TurnResult(
        answers=merged, extracted=extraction.all_fields, agent_message=question,
        next_cluster=following, next_stage=step.stage, stop_reason=step.stop_reason,
        llm_used=True, emergency=False,
        answer_quality=extraction.answer_quality,
        cluster_resolved=cluster_resolved,
        retried_same_cluster=retry_this_cluster,
        reopened_cluster_ids=reopened,
        screened_cluster_ids=screened_closed,
        next_probe=next_probe,
        deferred_cluster_ids=step.deferred_ids,
        recent_fields=recent_fields,
        dialogue_act=plan.act.value if plan is not None else "",
        router_trigger=router_trigger,
        protocol_name=active.name if protocol_switched else "",
        pending_retraction=reduced.pending_confirmation,
        audit=reduced.audit_log,
        triage_level=rule_result.triage_level,
        reason_codes=rule_result.reason_codes, triggered_rules=rule_result.triggered_rules,
    )


def run_open_turn(
    opening_protocol: SymptomProtocol,
    session_id: str,
    *,
    turn: int,
    message: str,
    answers: dict[str, TriState],
    select_protocol,
    protocol_for,
    conversation: list[dict[str, str]] | None = None,
    credential: provider_router.LLMCredential | None = None,
    on_token: TokenSink | None = None,
) -> TurnResult:
    """LƯỢT MỞ: người bệnh kể tự do, chưa ai hỏi gì cả.

    Khác `run_turn` ở ba điểm, cả ba đều là ràng buộc an toàn chứ không phải tiện lợi:

    1. **Không có "cụm đang hỏi"** nên MỌI field đều thuộc diện "chưa được hỏi" (`evidence="unasked"`)
       - model muốn ghi một phủ định hay một con số thì phải trích được nguyên văn từ lời người bệnh.
       Đây là lượt dễ bịa nhất (schema rộng, tin nhắn tự do), nên cũng là lượt phải siết chặt nhất.
    2. **Chốt đỏ vẫn chạy đầy đủ** - kể co giật/tím tái ngay câu đầu là chốt cấp cứu ngay câu đầu,
       không đợi đi hết bộ câu hỏi.
    3. **Protocol được CHỌN sau khi trích xuất**, không phải trước. Nghịch lý "phải biết protocol để
       chạy stage chọn protocol" là lý do lượt mở nằm ngoài `STAGE_ORDER` của mọi protocol.

    `select_protocol`/`protocol_for` truyền vào dạng hàm để module này không phải import registry -
    cơ chế không được biết danh sách bệnh nào tồn tại."""
    stage_log.step(
        session_id, turn=turn, stage="OPEN", cluster_id="OPEN", event="user_message",
        input=None, output={"text": message},
    )

    cluster = opening_protocol.clusters[0]
    extraction = extract_turn(
        opening_protocol, cluster, message, answers=answers,
        session_id=session_id, turn=turn, stage="OPEN", credential=credential,
        evidence="unasked",
    )

    opportunistic = scan_opportunistic_fields(opening_protocol, message)
    # Cùng reducer với `run_turn` - lượt mở KHÔNG được có một đường gộp trạng thái riêng, vì đó đúng
    # là cách hai nhánh lặng lẽ lệch nhau. Ở đây `answers` gần như luôn rỗng nên xoá dây chuyền và
    # mâu thuẫn không có gì để làm; giá trị nằm ở chỗ chỉ còn MỘT bộ quy tắc merge trong hệ thống.
    reduced = reducer.reduce(
        opening_protocol, answers,
        (
            *reducer.events_from_values(opportunistic, source=reducer.SOURCE_KEYWORD),
            *extraction.events,
        ),
    )
    merged = reduced.answers
    harvested = any(stage_machine.is_filled(value) for value in merged.values())

    protocol_name = select_protocol(merged, None)
    protocol = protocol_for(protocol_name)
    merged = _apply_derived_fields(protocol, merged)

    with stage_log.tool(
        session_id, turn=turn, stage="OPEN", cluster_id="OPEN",
        tool="rule_engine.evaluate", input=merged,
    ) as rec:
        rule_result = rule_engine.evaluate(protocol, merged)
        rec.output = {
            "triage_level": rule_result.triage_level,
            "reason_codes": list(rule_result.reason_codes),
            "triggered_rules": list(rule_result.triggered_rules),
        }

    if rule_result.triage_level == "EMERGENCY":
        stage_log.step(
            session_id, turn=turn, stage="OPEN", cluster_id="OPEN", event="stop", stop_reason="RED_FLAG",
        )
        return TurnResult(
            answers=merged, extracted=extraction.all_fields, agent_message=protocol.patient_red_flag_message,
            next_cluster=None, llm_used=True, emergency=True, protocol_name=protocol_name,
            answer_quality=extraction.answer_quality,
            triage_level=rule_result.triage_level,
            reason_codes=rule_result.reason_codes, triggered_rules=rule_result.triggered_rules,
        )

    if not harvested:
        # "xin chào", ".", "abc" - chưa có gì để đi tiếp. Hỏi lại câu mở TĨNH thay vì lao vào bộ câu
        # hỏi lâm sàng: nhảy sang "bé hay người lớn, bao nhiêu tuổi" khi người ta mới chào là cách
        # nhanh nhất để người bệnh bỏ cuộc.
        stage_log.step(
            session_id, turn=turn, stage="OPEN", cluster_id="OPEN", event="agent_message",
            input=None, output={"text": cluster.script_hint}, llm_used=False,
        )
        return TurnResult(
            answers=merged, extracted=extraction.all_fields, agent_message=cluster.script_hint,
            next_cluster=None, llm_used=True, emergency=False, protocol_name="",
            harvested_nothing=True, answer_quality=extraction.answer_quality,
            triage_level=rule_result.triage_level,
            reason_codes=rule_result.reason_codes, triggered_rules=rule_result.triggered_rules,
        )

    # Lượt mở là chỗ `relevance` đáng giá nhất: người bệnh vừa kể tự do nên field họ tự nêu chính là
    # mạch cần đi theo. Chưa có ledger nào ở đây - phiên vừa bắt đầu, chưa cụm nào bị hoãn.
    recent_fields = _recent_fields(opportunistic, extraction.cluster_fields)
    step = stage_machine.advance(
        protocol, protocol.stage_order[0], merged, context=_ranking_context(recent_fields, None, message),
    )
    following = step.cluster
    # Lời kể mở đầu có thể đã trả lời xong cả Stage 0/1/2 ("bé 4 tuổi, sốt 38.5 từ hôm qua, đã uống
    # hạ sốt"), lúc đó cụm kế tiếp đã nằm ở stage quét đỏ - lượt sàng lọc gộp phải áp dụng được ngay,
    # không đợi tới lượt sau.
    next_probe = screening.next_probe(protocol, step.stage, merged, following)
    batched: tuple[QuestionCluster, ...] = ()
    if next_probe:
        following = screening.probe_cluster(protocol, step.stage, next_probe)
        question, question_llm_used = following.script_hint, False
        _emit_static(on_token, question)
    else:
        # Lượt mở là chỗ gộp có giá trị nhất: người bệnh vừa kể tự do xong, hỏi dồn 2-3 ý nền (tuổi,
        # giới, triệu chứng chính) nghe tự nhiên hơn hẳn so với hỏi nhỏ giọt từng câu.
        batched = batching.next_batch(protocol, step.stage, merged, following)
        if batched:
            following = batching.batch_cluster(step.stage, batched)
        # Lượt mở: người bệnh vừa kể tự do, chưa trả lời câu hỏi nào của hệ thống - nên act luôn là
        # `ANSWER`, không phải nhãn `answer_quality` model gán cho một câu hỏi chưa từng được hỏi.
        open_plan = dialogue.build_response_plan(
            protocol, following,
            act=dialogue.DialogueAct.ANSWER,
            answers=merged,
            recent_fields=recent_fields,
            parts=len(batched) or 1,
        )
        question, question_llm_used = (
            _generate_question(
                protocol, following, answers=merged, plan=open_plan,
                parts=len(batched) or 1,
                conversation=conversation, credential=credential, on_token=on_token,
            )
            if following is not None
            else ("", False)
        )
    stage_log.step(
        session_id, turn=turn, stage="OPEN", cluster_id="OPEN", event="agent_message",
        input=None, output={"text": question}, llm_used=question_llm_used,
    )

    return TurnResult(
        answers=merged, extracted=extraction.all_fields, agent_message=question,
        next_cluster=following, next_stage=step.stage, stop_reason=step.stop_reason,
        llm_used=True, emergency=False, protocol_name=protocol_name,
        answer_quality=extraction.answer_quality, next_probe=next_probe,
        deferred_cluster_ids=step.deferred_ids, recent_fields=recent_fields,
        dialogue_act=dialogue.DialogueAct.ANSWER.value,
        router_trigger=controller.should_consult_group_router(
            is_opening=True, act=dialogue.DialogueAct.ANSWER, recent_fields=recent_fields,
            chief_complaint_field=protocol.chief_complaint_field, protocol_ruled_out=False,
        ),
        triage_level=rule_result.triage_level,
        reason_codes=rule_result.reason_codes, triggered_rules=rule_result.triggered_rules,
    )


SAFETY_LOOKAHEAD_CLUSTERS = 0
"""Bao nhiêu cụm SẮP hỏi được đưa kèm vào schema trích xuất mỗi lượt.

Trước đây là 5, và đó là nguồn của phàn nàn "có thông tin trong câu trả lời rồi mà vẫn hỏi lại":
người bệnh kể vượt trước một chi tiết thuộc cụm nằm ngoài cửa sổ 5 cụm (vd kể luôn bối cảnh nguy cơ
của Stage 4 ngay lượt mở) thì model KHÔNG có ô nào trong schema để ghi - chi tiết đó rơi mất, và khi
hội thoại đi tới đúng cụm đó thì hỏi lại nguyên văn thứ họ vừa nói.

**`0` = KHÔNG TRẦN** (2026-08-22): mọi cụm còn lại của protocol đều có ô trong schema, ở mọi lượt.

12 từng đủ khi mục tiêu là "phủ hai stage kế tiếp". Yêu cầu mới mạnh hơn: field thuộc về TỪNG
BƯỚC của quy trình, và người bệnh trả lời trước field của BẤT KỲ bước nào thì phải ghi nhận được
ngay, để khi hội thoại đi tới bước đó thì KHÔNG hỏi lại - và dùng lượt đó hỏi field khác. Một trần
12 cụm vẫn để lọt ca "kể luôn bệnh nền và thuốc đang dùng ngay lượt mở" (Stage 4/5 của fever).

Nới rộng KHÔNG mở đường cho model bịa: field chưa được hỏi vẫn chịu `EvidencePolicy` khắt khe nhất
(phải trích được nguyên văn câu của người bệnh mới được điền). Cái giá thật là **prompt dài hơn và
tốn token hơn mỗi lượt** - fever có 101 field. Đó là đánh đổi có chủ đích: đổi token lấy việc không
hỏi lại thứ người bệnh vừa nói. Đặt lại một số dương nếu cần cắt chi phí."""


def _safety_extra_keys(
    protocol: SymptomProtocol,
    stage: str,
    cluster: QuestionCluster,
    answers: dict[str, TriState],
    asked_ids: frozenset[str],
    lookahead: int = SAFETY_LOOKAHEAD_CLUSTERS,
) -> tuple[str, ...]:
    """Field được quét KÈM ngoài cụm đang hỏi.

    Gồm 3 nhóm: (a) `protocol.safety_signal_fields` - dấu hiệu đỏ, phải bắt được kể cả khi người dùng
    kể tình cờ trước lúc tới gate stage; (b) field còn thiếu của các cụm SẮP hỏi (xem
    `SAFETY_LOOKAHEAD_CLUSTERS`); (c) field hệ trọng được phép đính chính.

    Bản cũ quét toàn bộ field của stage hiện tại. Đổi sang nhóm (b)+(c) không phải để prompt ngắn hơn
    - stage 3A có 11 cụm nên số field không chắc giảm - mà để phủ ĐÚNG thứ người dùng hay nói vượt
    trước ("19 tuổi, sống một mình, đo ở nách, 39 độ"), thay vì phủ đều cả stage."""
    keys: list[str] = list(protocol.safety_signal_fields)

    upcoming = 0
    for candidate in protocol.clusters:
        if lookahead and upcoming >= lookahead:
            break
        if candidate.id == cluster.id or candidate.id in asked_ids:
            continue
        if protocol.skip_rule(candidate, answers):
            continue
        # `cluster_needs_answer` chứ không phải `is_filled` từng field: cụm chỉ còn field KHÔNG ÁP
        # DỤNG (cha đã bị phủ định) thì đưa vào schema là mời model điền thứ vô nghĩa.
        if not stage_machine.cluster_needs_answer(protocol, candidate, answers):
            continue
        keys.extend(candidate.fields)
        upcoming += 1

    # Field HỆ TRỌNG tới mức được phép đính chính: giữ trong schema NGAY CẢ KHI đã điền.
    #
    # Lỗi thật đo được: người bệnh nói "à tôi nhầm, tôi không sốt" ở một lượt đang hỏi chuyện khác thì
    # không có đường nào ghi nhận được, vì `fever_reported` đã điền nên bị loại khỏi schema - toàn bộ
    # cơ chế đính chính (`retraction.apply_retraction`, `_merge_answers` cho phép ghi đè giá trị đã
    # xác định) không bao giờ có dữ liệu để chạy. Dùng đúng `confirm_before_retract` chứ không mở cho
    # mọi field: đó là tập protocol đã tự khai "xoá nhầm cái này thì đắt", tức cũng là tập người bệnh
    # hay đính chính nhất.
    retractable = protocol.confirm_before_retract
    keys.extend(key for key in retractable if key not in cluster.fields)

    seen: set[str] = set()
    ordered: list[str] = []
    for key in keys:
        if key in cluster.fields or key in seen or key not in protocol.fields_by_key:
            continue
        if key not in retractable and stage_machine.field_is_settled(protocol, key, answers):
            continue  # đã biết rồi, hoặc không áp dụng vì field cha đã bị phủ định
        seen.add(key)
        ordered.append(key)
    return tuple(ordered)


def scan_opportunistic_fields(protocol: SymptomProtocol, message: str) -> dict[str, TriState]:
    """Quét từ khoá nhẹ (kỹ thuật `_contains_any` của `semantic_mapper.py`) cho field an toàn cốt
    lõi có thể xuất hiện tự nhiên trước khi tới lượt hỏi cụm tương ứng. CHỈ trả `"true"` khi khớp từ
    khoá - không bao giờ trả `"false"` (im lặng không phải bằng chứng phủ định, đúng P0-4). Caller
    chịu trách nhiệm không ghi đè giá trị đã có.

    Khớp thô kèm guard polarity: "tôi không co giật" chứa đúng chuỗi "co giật" nên bản trước ghi
    `seizure_occurred="true"` cho một câu người bệnh vừa PHỦ ĐỊNH. Guard dùng chung với tầng L0
    (`text_safety_signals`) chứ không viết lại ở đây - hai bản luật phủ định sẽ lệch nhau."""
    normalized = (message or "").casefold()
    found: dict[str, TriState] = {}
    for key, keywords in protocol.opportunistic_keywords:
        if _contains_any(normalized, keywords) and not text_safety_signals.all_mentions_negated(message, keywords):
            found[key] = "true"
    # `reporter_type` thuộc về đây chứ không phải một móc riêng ở `run_turn`: nó đúng là thứ người
    # bệnh nói tình cờ, ở lượt mà không cụm nào hỏi tới. Quan trọng hơn, đây là hàm DUY NHẤT mà cả
    # lượt MỞ lẫn lượt giữa phiên đều gọi - mà "bạn tôi bị đau ngực" gần như luôn là câu ĐẦU TIÊN.
    #
    # Không đi qua `protocol.opportunistic_keywords`: bộ đó ánh xạ từ khoá -> `"true"` cho field
    # tri-state, còn field này là enum. Bảng cue nằm ở `text_safety_signals` để dùng CHUNG với guard
    # `GUARD_OTHER_SUBJECT`, chứ không chép ra bản thứ hai.
    reported_by = text_safety_signals.reporter_type_from_text(message)
    if reported_by:
        found["reporter_type"] = reported_by
    return found
