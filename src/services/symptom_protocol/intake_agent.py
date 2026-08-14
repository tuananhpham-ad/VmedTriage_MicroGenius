"""LLM extraction theo cụm + ghép hướng C/E theo stage - DÙNG CHUNG cho mọi symptom_group.

Tái dùng hạ tầng đã có, không viết lại: `provider_router.complete()` +
`intake_agent._parse_json_object()` (`src/services/agents/intake_agent.py`) để gọi LLM/bóc JSON, và
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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from src.services.agents.intake_agent import _parse_json_object
from src.services.engines.semantic_mapper import _contains_any
from src.services.infra import fever_stage_log as stage_log
from src.services.infra import provider_router
from src.services.symptom_protocol import retraction, rule_engine, stage_machine
from src.services.symptom_protocol.models import QuestionCluster
from src.services.symptom_protocol.protocol import SymptomProtocol

logger = logging.getLogger("vmedtriage.symptom_intake")

TriState = str  # "true" | "false" | "unknown"

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


def _missing_in_cluster(
    protocol: SymptomProtocol, cluster: QuestionCluster, answers: dict[str, TriState],
) -> tuple[str, ...]:
    """Field của cụm còn thiếu. Cụm điền dở phải hỏi tiếp ĐÚNG phần thiếu, không hỏi lại cả cụm."""
    return tuple(key for key in cluster.fields if not stage_machine.is_filled(answers.get(key)))


def _field_specs(protocol: SymptomProtocol, field_keys: tuple[str, ...]) -> str:
    lines = []
    for key in field_keys:
        spec = protocol.fields_by_key[key]
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
    cluster_fields = _collect(protocol, cluster, parsed, message, evidence=evidence)
    # batch_negation=False TƯỜNG MINH (turn-scoping): cờ phủ định gộp chỉ có nghĩa cho ĐÚNG cụm vừa
    # được hỏi. `safety_keys` là field của cụm KHÁC mà người dùng chưa hề được hỏi tới - để cờ lan
    # sang đây tức là một câu "không có gì cả" sẽ đóng luôn cả loạt cụm chưa hỏi.
    safety_fields = _collect_fields(
        protocol, tuple(k for k in safety_keys if k not in cluster.fields), parsed,
        batch_negation=False, message=message, evidence="unasked",
    )
    extraction = Extraction(
        cluster_fields=cluster_fields,
        safety_fields=safety_fields,
        answer_quality=_answer_quality(parsed),
        llm_ok=parse_error is None,
    )

    if session_id is not None:
        stage_log.step(
            session_id, turn=turn, stage=log_stage, cluster_id=cluster.id, event="extract",
            input=None, output=extraction.all_fields,
            answers_delta=_answers_delta(answers, extraction.all_fields),
            answer_quality=extraction.answer_quality,
        )

    return extraction


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
        result = provider_router.complete(messages, temperature=temperature, credential=credential)
    except Exception as exc:
        logger.warning("symptom_intake.extract_failed reason=%s", type(exc).__name__)
        latency_ms = int((time.monotonic() - started) * 1000)
        return None, f"{type(exc).__name__}: {exc}", "(none)", "(none)", "", latency_ms

    latency_ms = int((time.monotonic() - started) * 1000)
    try:
        parsed = _parse_json_object(result.text)
    except Exception:
        try:
            parsed = _parse_json_object(_repair_bareword_unknown(result.text))
        except Exception as exc:  # JSON vẫn hỏng sau khi đã thử sửa - không phải lỗi gọi provider
            logger.warning("symptom_intake.parse_failed reason=%s", type(exc).__name__)
            return None, f"{type(exc).__name__}: {exc}", result.provider, result.model, result.text, latency_ms

    return parsed, None, result.provider, result.model, result.text, latency_ms


_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_for_evidence(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", (text or "").strip()).casefold()


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


def _value_and_evidence(raw: object) -> tuple[object, object]:
    """Bóc `{"value": ..., "evidence_span": ...}` thành cặp, chấp nhận cả dạng phẳng `<giá trị>`.

    Giữ dạng phẳng vì hai lý do: (a) model đôi khi trả phẳng dù prompt yêu cầu có evidence - lúc đó
    giá trị vẫn được xét rồi bị loại ở tầng `_needs_evidence`, tốt hơn là làm hỏng cả JSON; (b) các
    caller kiểm tra hậu xử lý enum/tri-state không cần dựng evidence giả."""
    if isinstance(raw, dict) and "value" in raw:
        return raw.get("value"), raw.get("evidence_span")
    return raw, None


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


def _needs_evidence(policy: EvidencePolicy, spec, value: object) -> bool:
    """Giá trị này có bắt buộc phải kèm `evidence_span` khớp tin nhắn không?

    CHỈ field người dùng CHƯA được hỏi mới phải chứng minh, và chỉ ở chiều rủi ro:

    - `"false"` -> phải có bằng chứng (đúng chiều lỗi C1).
    - enum/số/ngày -> phải có bằng chứng (đúng chiều lỗi C2: model tự sinh
      `fever_onset_at="2023-10-05"` trong lúc đang hỏi chuyện khác).
    - `"true"` -> KHÔNG BAO GIỜ phải chứng minh. Bịa `"true"` chỉ đẩy ca lên mức thận trọng hơn (P0-6
      chấp nhận), còn LOẠI NHẦM một `"true"` thật là bỏ sót cấp cứu (P0-5) - hướng hỏng tệ hơn hẳn.

    Field của cụm ĐANG hỏi (`"asked"`) không phải chứng minh gì: cả tin nhắn chính là câu trả lời cho
    đúng câu vừa hỏi, nên `"không"` ở đó là dữ kiện thật chứ không phải suy diễn. Cả 3 lần tái hiện C1
    đều xảy ra ở field NGOÀI cụm đang hỏi (`safety_keys`) hoặc do cờ phủ định gộp lan ra ngoài cụm -
    hai đường đó đã có guard riêng (`_negation_evidence_ok` + `batch_negation=False` cho safety keys)."""
    if policy != "unasked":
        return False
    return not spec.tri_state or value == "false"


def _collect_fields(
    protocol: SymptomProtocol,
    field_keys: tuple[str, ...],
    parsed: dict,
    *,
    batch_negation: bool = False,
    message: str = "",
    evidence: EvidencePolicy = "off",
) -> dict[str, TriState]:
    """Bóc field từ JSON model trả về, loại mọi thứ không hợp lệ.

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
    cluster_negative = (
        batch_negation
        and bool(parsed.get("cluster_all_negative"))
        and _negation_evidence_ok(parsed, message)
    )

    collected: dict[str, TriState] = {}
    for key in field_keys:
        spec = protocol.fields_by_key[key]
        raw, evidence_span = _value_and_evidence(parsed.get(key))

        if not spec.tri_state:
            if raw not in (None, "", "null"):
                coerced = _coerce_enum(spec, raw)
                supported = not _needs_evidence(evidence, spec, coerced) or _evidence_in_message(
                    evidence_span, message,
                )
                if coerced is not None and supported:
                    collected[key] = coerced
            continue

        value = _tri_state_value(raw)
        if _needs_evidence(evidence, spec, value) and not _evidence_in_message(evidence_span, message):
            # Model khẳng định "không" nhưng không trích được câu nào trong tin nhắn -> giữ ngỏ để
            # còn được hỏi lại, thay vì đóng vĩnh viễn một field an toàn (lỗi C1).
            value = "unknown"
        if value == "unknown" and cluster_negative:
            # Phủ định gộp đã tự có bằng chứng riêng (`negation_evidence`) nên vẫn được áp ở đây.
            value = "false"
        collected[key] = value

    return collected


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
    protocol_name: str = ""
    """Protocol sẽ chạy từ lượt sau. Chỉ khác rỗng ở lượt mở (`run_open_turn`), nơi protocol được
    CHỌN chứ không phải cho trước."""
    harvested_nothing: bool = False
    """Lượt mở không thu được field nào - tin nhắn quá nghèo ("xin chào", "."), phải hỏi lại câu mở
    thay vì lao vào bộ câu hỏi lâm sàng."""
    triage_level: str | None = None
    reason_codes: tuple[str, ...] = ()
    triggered_rules: tuple[str, ...] = ()


_QUESTION_ONLY_SYSTEM = """Bạn là điều dưỡng đang hỏi triệu chứng qua tin nhắn cho người bệnh/người nhà.

Hãy diễn đạt lại Ý CẦN HỎI dưới đây thành MỘT câu hỏi tiếng Việt tự nhiên, ấm áp, ngắn gọn (tối đa 2 ý):
"{script_hint}"{focus}

ĐÃ BIẾT VỀ NGƯỜI BỆNH (TUYỆT ĐỐI không hỏi lại những điều này):
{known_facts}
{acknowledgement}
Vài lượt hội thoại gần đây nhất (để tránh lặp lại nguyên văn cách diễn đạt đã dùng trước đó):
{history}

QUY TẮC BẮT BUỘC:
- TUYỆT ĐỐI KHÔNG chẩn đoán bệnh, KHÔNG nêu tên bệnh, KHÔNG nhận định mức độ nguy hiểm.
- KHÔNG hỏi thêm ý nào ngoài Ý CẦN HỎI ở trên.
- {instruction}
- Chỉ trả về đúng câu hỏi, không thêm lời dẫn hay giải thích."""


def _format_history(conversation: list[dict[str, str]], limit: int = 6) -> str:
    if not conversation:
        return "(chưa có lượt nào trước đó)"
    recent = conversation[-limit:]
    return "\n".join(
        f"{'Người bệnh' if turn.get('role') == 'user' else 'Trợ lý'}: {turn.get('content', '')}" for turn in recent
    )


# temperature cao hơn CHỈ dùng cho bước "diễn đạt lại câu hỏi" - không trích xuất field ở đây nên
# không đánh đổi độ chính xác. temperature=0 khiến LLM trả gần như Y HỆT một câu cho cùng 1
# script_hint mỗi lần, làm hội thoại cảm giác "học thuộc lòng" (phát hiện qua test tay với LLM thật).
_QUESTION_TEMPERATURE = 0.7

# Số lần hỏi lại tối đa cho MỘT cụm trước khi bỏ qua. 2 là đánh đổi tường minh: đủ để người dùng hiểu
# ra ý câu hỏi khi diễn đạt lần đầu chưa rõ, nhưng không biến hội thoại thành vòng lặp - hội thoại
# treo vô hạn là bug đã gặp thật ở Stage 3A (Checkpoint 6).
MAX_RETRIES_PER_CLUSTER = 2


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
    missing_keys: tuple[str, ...] = (),
    acknowledgement: str = "",
    rephrase: bool = False,
    conversation: list[dict[str, str]] | None = None,
    credential: provider_router.LLMCredential | None,
) -> tuple[str, bool]:
    """Call LLM thứ hai: CHỈ diễn đạt câu hỏi cho cụm mà RULE đã chọn. Trả `(câu hỏi, llm_used)`.

    LLM không được chọn cụm ở đây - nó chỉ nhận `cluster` đã chốt. Đây là ranh giới quan trọng nhất
    của kiến trúc: kiến trúc cũ để LLM vừa trích xuất vừa tự chọn câu kế tiếp trong 1 call, nên khi
    code phát hiện lựa chọn sai và ép về cụm đúng thì CÂU HỎI vẫn là câu viết cho cụm bị loại - người
    dùng bị hỏi X trong khi lượt sau hệ thống trích theo schema Y."""
    if not cluster.script_hint:
        return "", False

    focus = ""
    if missing_keys and len(missing_keys) < len(cluster.fields):
        labels = ", ".join(protocol.fields_by_key[key].label for key in missing_keys)
        focus = f"\nCHỈ CÒN THIẾU (đừng hỏi lại phần đã biết): {labels}"

    instruction = (
        "Người bệnh vừa KHÔNG trả lời được ý này. Hãy diễn đạt KHÁC HẲN lần trước và nói ngắn gọn vì "
        "sao cần biết điều đó."
        if rephrase
        else "Diễn đạt KHÁC đi so với các câu hỏi trước đó của trợ lý (đổi từ ngữ/cấu trúc câu)."
    )

    system_prompt = _QUESTION_ONLY_SYSTEM.format(
        script_hint=cluster.script_hint,
        focus=focus,
        known_facts=_known_facts(protocol, answers),
        acknowledgement=(
            f'\nMở đầu bằng một câu công nhận NGẮN điều vừa nghe: "{acknowledgement}"' if acknowledgement else ""
        ),
        instruction=instruction,
        history=_format_history(conversation or []),
    )
    try:
        result = provider_router.complete(
            [{"role": "user", "content": system_prompt}], temperature=_QUESTION_TEMPERATURE, credential=credential,
        )
        question = result.text.strip().strip('"')
        if question:
            return question, True
    except Exception as exc:
        logger.warning("symptom_intake.question_failed reason=%s", type(exc).__name__)
    return cluster.script_hint, False


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
    asked_ids: frozenset[str] = frozenset(),
    retry_count: int = 0,
    conversation: list[dict[str, str]] | None = None,
    credential: provider_router.LLMCredential | None = None,
    select_protocol=None,
    protocol_for=None,
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
    """
    credential = credential or protocol.default_credential
    stage_log.step(
        session_id, turn=turn, stage=stage, cluster_id=cluster.id, event="user_message",
        input=None, output={"text": message},
    )

    safety_keys = _safety_extra_keys(protocol, stage, cluster, answers, asked_ids)
    extraction = extract_turn(
        protocol, cluster, message, answers=answers, safety_keys=safety_keys,
        session_id=session_id, turn=turn, stage=stage, credential=credential,
    )

    opportunistic = scan_opportunistic_fields(protocol, message)
    merged = _merge_answers(answers, opportunistic, extraction.safety_fields, extraction.cluster_fields)
    merged = _apply_derived_fields(protocol, merged)

    # Đính chính + mâu thuẫn PHẢI chạy TRƯỚC rule_engine: nếu chạy sau, mức triage của chính lượt này
    # được tính trên hồ sơ còn rác (vd đã nói "không sốt" nhưng `temp_c=39` vẫn còn trong answers).
    merged, reopened = retraction.apply_retraction(protocol, answers, merged)
    contradicted, contradiction_clusters = retraction.find_contradictions(protocol, merged)
    reopened = reopened | frozenset(contradiction_clusters)
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
            input=None, output={"text": active.emergency_message}, llm_used=False,
        )
        stage_log.step(
            session_id, turn=turn, stage=stage, cluster_id=cluster.id, event="stop", stop_reason="RED_FLAG",
        )
        return TurnResult(
            answers=merged, extracted=extraction.all_fields, agent_message=active.emergency_message,
            next_cluster=None, llm_used=True, emergency=True,
            protocol_name=active.name if protocol_switched else "",
            answer_quality=extraction.answer_quality, reopened_cluster_ids=reopened,
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
        if protocol_switched:
            step = stage_machine.advance(
                active, active.stage_order[0], merged, known_triage_level=rule_result.triage_level,
            )
        elif retry_this_cluster:
            step = stage_machine.Advance(cluster, stage, None)
        else:
            step = stage_machine.advance(
                active, stage, merged,
                asked_ids=(asked_ids | {cluster.id}) - reopened,
                known_triage_level=rule_result.triage_level,
            )
        following = step.cluster
        rec.output = {
            "cluster_id": following.id if following else None,
            "stage": step.stage, "stop_reason": step.stop_reason, "retry": retry_this_cluster,
        }

    question, question_llm_used = (
        _generate_question(
            active, following, answers=merged,
            missing_keys=_missing_in_cluster(active, following, merged),
            rephrase=retry_this_cluster,
            conversation=conversation, credential=credential,
        )
        if following is not None
        else ("", False)
    )
    stage_log.step(
        session_id, turn=turn, stage=stage, cluster_id=cluster.id, event="agent_message",
        input=None, output={"text": question}, llm_used=question_llm_used,
    )

    return TurnResult(
        answers=merged, extracted=extraction.all_fields, agent_message=question,
        next_cluster=following, next_stage=step.stage, stop_reason=step.stop_reason,
        llm_used=True, emergency=False,
        answer_quality=extraction.answer_quality,
        cluster_resolved=cluster_resolved,
        retried_same_cluster=retry_this_cluster,
        reopened_cluster_ids=reopened,
        protocol_name=active.name if protocol_switched else "",
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
    merged = _merge_answers(answers, opportunistic, extraction.cluster_fields)
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
            answers=merged, extracted=extraction.all_fields, agent_message=protocol.emergency_message,
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

    step = stage_machine.advance(protocol, protocol.stage_order[0], merged)
    question, question_llm_used = (
        _generate_question(
            protocol, step.cluster, answers=merged,
            missing_keys=_missing_in_cluster(protocol, step.cluster, merged),
            conversation=conversation, credential=credential,
        )
        if step.cluster is not None
        else ("", False)
    )
    stage_log.step(
        session_id, turn=turn, stage="OPEN", cluster_id="OPEN", event="agent_message",
        input=None, output={"text": question}, llm_used=question_llm_used,
    )

    return TurnResult(
        answers=merged, extracted=extraction.all_fields, agent_message=question,
        next_cluster=step.cluster, next_stage=step.stage, stop_reason=step.stop_reason,
        llm_used=True, emergency=False, protocol_name=protocol_name,
        answer_quality=extraction.answer_quality,
        triage_level=rule_result.triage_level,
        reason_codes=rule_result.reason_codes, triggered_rules=rule_result.triggered_rules,
    )


def _safety_extra_keys(
    protocol: SymptomProtocol,
    stage: str,
    cluster: QuestionCluster,
    answers: dict[str, TriState],
    asked_ids: frozenset[str],
    lookahead: int = 5,
) -> tuple[str, ...]:
    """Field được quét KÈM ngoài cụm đang hỏi.

    Gồm 3 nhóm: (a) `protocol.safety_signal_fields` - dấu hiệu đỏ, phải bắt được kể cả khi người dùng
    kể tình cờ trước lúc tới gate stage; (b) field còn thiếu của vài cụm SẮP hỏi; (c) field nhân khẩu
    còn thiếu.

    Bản cũ quét toàn bộ field của stage hiện tại. Đổi sang nhóm (b)+(c) không phải để prompt ngắn hơn
    - stage 3A có 11 cụm nên số field không chắc giảm - mà để phủ ĐÚNG thứ người dùng hay nói vượt
    trước ("19 tuổi, sống một mình, đo ở nách, 39 độ"), thay vì phủ đều cả stage."""
    keys: list[str] = list(protocol.safety_signal_fields)

    upcoming = 0
    for candidate in protocol.clusters:
        if upcoming >= lookahead:
            break
        if candidate.id == cluster.id or candidate.id in asked_ids:
            continue
        if protocol.skip_rule(candidate, answers):
            continue
        if not any(not stage_machine.is_filled(answers.get(key)) for key in candidate.fields):
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
        if stage_machine.is_filled(answers.get(key)) and key not in retractable:
            continue  # đã biết rồi thì không cần model trích lại
        seen.add(key)
        ordered.append(key)
    return tuple(ordered)


def scan_opportunistic_fields(protocol: SymptomProtocol, message: str) -> dict[str, TriState]:
    """Quét từ khoá nhẹ (kỹ thuật `_contains_any` của `semantic_mapper.py`) cho field an toàn cốt
    lõi có thể xuất hiện tự nhiên trước khi tới lượt hỏi cụm tương ứng. CHỈ trả `"true"` khi khớp từ
    khoá - không bao giờ trả `"false"` (im lặng không phải bằng chứng phủ định, đúng P0-4). Caller
    chịu trách nhiệm không ghi đè giá trị đã có."""
    normalized = (message or "").casefold()
    found: dict[str, TriState] = {}
    for key, keywords in protocol.opportunistic_keywords:
        if _contains_any(normalized, keywords):
            found[key] = "true"
    return found
