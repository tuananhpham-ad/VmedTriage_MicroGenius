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

from src.services.agents.intake_agent import _parse_json_object
from src.services.engines.semantic_mapper import _contains_any
from src.services.infra import fever_stage_log as stage_log
from src.services.infra import provider_router
from src.services.symptom_protocol import rule_engine, stage_machine
from src.services.symptom_protocol.models import QuestionCluster
from src.services.symptom_protocol.protocol import SymptomProtocol, clusters_for_stage

logger = logging.getLogger("vmedtriage.symptom_intake")

TriState = str  # "true" | "false" | "unknown"

_TRUE_TOKENS = frozenset({"true", "có", "co", "yes", "dương tính", "duong tinh"})
_FALSE_TOKENS = frozenset({"false", "không", "khong", "no", "âm tính", "am tinh"})


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

QUY TẮC BẮT BUỘC:
- CHỈ trích xuất thông tin ĐÃ CÓ trong tin nhắn. TUYỆT ĐỐI KHÔNG suy diễn, KHÔNG phỏng đoán con số.
- Với trường [true|false|unknown]: trả "true" nếu người dùng xác nhận CÓ, "false" nếu XÁC NHẬN RÕ
  RÀNG không có, "unknown" nếu không nhắc tới hoặc mơ hồ. TUYỆT ĐỐI KHÔNG suy diễn im lặng thành
  "false" - im lặng luôn là "unknown".
- Với trường NGÀY THÁNG: nếu người dùng nói tương đối ("hôm nay", "hôm qua", "N ngày nay/trước/rồi"),
  tự quy đổi sang ngày cụ thể YYYY-MM-DD dựa trên "hôm nay" đã cho ở trên - KHÔNG bỏ trống chỉ vì
  người dùng không nói ngày tuyệt đối.
- KHÔNG chẩn đoán bệnh, KHÔNG đề xuất mức độ khẩn cấp, KHÔNG đưa hướng xử trí.
- Chỉ trả về MỘT JSON object phẳng, không kèm giải thích, không lồng object con.
{batch_negation_rule}
CÁC TRƯỜNG CẦN TRÍCH XUẤT:
{field_specs}

Định dạng trả về: {{"<field_key>": <giá trị>, ...}}"""

_BATCH_NEGATION_RULE = """- Đây là câu hỏi gộp kiểu phủ định cả cụm. Nếu người dùng phủ định TƯỜNG MINH cho CẢ CỤM (vd "không,
  không có gì trong số đó cả", "hoàn toàn bình thường"), thêm "cluster_all_negative": true vào JSON
  trả về - hệ thống sẽ tự gán false cho các trường còn lại chưa nhắc tới. Nếu người dùng chỉ xác nhận
  một vài ý, đừng thêm cờ này - chỉ điền đúng field họ đã nói rõ.
- Khi thêm "cluster_all_negative": true, BẮT BUỘC thêm kèm "negation_evidence": "<đoạn TRÍCH NGUYÊN
  VĂN từ tin nhắn người dùng thể hiện sự phủ định đó>". Phải chép Y HỆT ký tự trong tin nhắn, không
  diễn giải lại, không dịch, không viết hoa/thường khác đi. Không trích được câu nào thì KHÔNG được
  đặt cờ.
"""


def extract_cluster(
    protocol: SymptomProtocol,
    cluster: QuestionCluster,
    message: str,
    *,
    session_id: str | None = None,
    turn: int = 0,
    stage: str | None = None,
    credential: provider_router.LLMCredential | None = None,
) -> dict[str, TriState]:
    """Trích field của MỘT cụm câu hỏi từ tin nhắn tự do. Không bao giờ ném ra ngoài - lỗi LLM rơi
    về toàn bộ field = "unknown" (an toàn hơn suy diễn sai, đúng P0-4/P0-6)."""
    log_stage = stage or cluster.stage

    if session_id is not None:
        stage_log.step(
            session_id, turn=turn, stage=log_stage, cluster_id=cluster.id, event="retrieve",
            input={"cluster_id": cluster.id}, output={"fields": list(cluster.fields), "schema_size": len(cluster.fields)},
        )

    batch_rule = _BATCH_NEGATION_RULE if cluster.batch_negation else ""
    system_prompt = _EXTRACTION_SYSTEM.format(
        today=_today_iso(), batch_negation_rule=batch_rule, field_specs=_field_specs(protocol, cluster.fields),
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

    extracted = _collect(protocol, cluster, parsed or {}, message)

    if session_id is not None:
        stage_log.step(
            session_id, turn=turn, stage=log_stage, cluster_id=cluster.id, event="extract",
            input=None, output=extracted,
            answers_delta={key: f"unknown -> {value}" for key, value in extracted.items()},
        )

    return extracted


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


def _negation_evidence_ok(parsed: dict, message: str) -> bool:
    """Cờ phủ định gộp CHỈ được tin khi model trích được nguyên văn câu phủ định từ chính tin nhắn.

    Lỗi thật đã tái hiện 3/3 lần khi test tay với LLM thật: người dùng nói "ăn uống tốt, không nôn",
    model đặt `cluster_all_negative` rồi hệ thống gán "false" cho cả 11 red flag (co giật, tím tái,
    xuất huyết...) mà người dùng chưa hề được hỏi. Đây là suy diễn im lặng thành phủ định - vi phạm
    P0-4 và là loại lỗi nguy hiểm nhất của hệ thống (bỏ sót ca cấp cứu).

    Kiểm tra là substring sau khi chuẩn hoá khoảng trắng + casefold: model bịa evidence sẽ không khớp,
    còn model trích đúng thì hầu như luôn khớp. So khớp lỏng hơn (fuzzy) sẽ mở lại đúng lỗ hổng này."""
    evidence = parsed.get("negation_evidence")
    if not isinstance(evidence, str):
        return False
    normalized_evidence = _normalize_for_evidence(evidence)
    if not normalized_evidence:
        return False
    return normalized_evidence in _normalize_for_evidence(message)


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


def _collect_fields(
    protocol: SymptomProtocol,
    field_keys: tuple[str, ...],
    parsed: dict,
    *,
    batch_negation: bool = False,
    message: str = "",
) -> dict[str, TriState]:
    cluster_negative = (
        batch_negation
        and bool(parsed.get("cluster_all_negative"))
        and _negation_evidence_ok(parsed, message)
    )

    collected: dict[str, TriState] = {}
    for key in field_keys:
        spec = protocol.fields_by_key[key]
        if not spec.tri_state:
            raw = parsed.get(key)
            if raw not in (None, "", "null"):
                coerced = _coerce_enum(spec, raw)
                if coerced is not None:
                    collected[key] = coerced
            continue

        value = _tri_state_value(parsed.get(key))
        if value == "unknown" and cluster_negative:
            value = "false"
        collected[key] = value

    return collected


def _collect(protocol: SymptomProtocol, cluster: QuestionCluster, parsed: dict, message: str = "") -> dict[str, TriState]:
    return _collect_fields(
        protocol, cluster.fields, parsed, batch_negation=cluster.batch_negation, message=message,
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
    llm_used: bool = False
    emergency: bool = False
    triage_level: str | None = None
    reason_codes: tuple[str, ...] = ()
    triggered_rules: tuple[str, ...] = ()


_QUESTION_ONLY_SYSTEM = """Bạn là điều dưỡng đang hỏi triệu chứng qua tin nhắn cho người bệnh/người nhà.

Hãy diễn đạt lại Ý CẦN HỎI dưới đây thành MỘT câu hỏi tiếng Việt tự nhiên, ấm áp, ngắn gọn (tối đa 2 ý):
"{script_hint}"

Vài lượt hội thoại gần đây nhất (để tránh lặp lại nguyên văn cách diễn đạt đã dùng trước đó):
{history}

QUY TẮC BẮT BUỘC:
- TUYỆT ĐỐI KHÔNG chẩn đoán bệnh, KHÔNG nêu tên bệnh, KHÔNG nhận định mức độ nguy hiểm.
- Diễn đạt KHÁC đi so với các câu hỏi trước đó của trợ lý (đổi từ ngữ/cấu trúc câu), miễn giữ đúng
  Ý CẦN HỎI - tránh nghe như một kịch bản cố định lặp đi lặp lại.
- Chỉ trả về đúng câu hỏi, không thêm lời dẫn hay giải thích."""

_COMBINED_SYSTEM = """Bạn là trợ lý y tế vừa trích xuất thông tin vừa hỏi tiếp câu tiếp theo.

Hôm nay là ngày {today} (định dạng YYYY-MM-DD).

BƯỚC 1 - TRÍCH XUẤT: đọc tin nhắn người dùng, điền vào ĐÚNG các trường liệt kê dưới đây, KHÔNG được
điền trường nào khác:
{field_specs}

NGOÀI RA, dù KHÔNG thuộc lượt hỏi này, nếu tin nhắn có TỰ MÔ TẢ/NHẮC TỚI bất kỳ điều nào dưới đây, vẫn
PHẢI điền vào JSON (dấu hiệu an toàn khẩn cấp hoặc thông tin hay được nói trước tự nhiên - không được
bỏ sót rồi bắt hỏi lại):
{safety_field_specs}

QUY TẮC TRÍCH XUẤT:
- CHỈ trích xuất thông tin ĐÃ CÓ trong tin nhắn. TUYỆT ĐỐI KHÔNG suy diễn, KHÔNG phỏng đoán.
- Với trường [true|false|unknown]: "true" nếu xác nhận CÓ, "false" nếu XÁC NHẬN RÕ RÀNG không có,
  "unknown" nếu không nhắc tới/mơ hồ. Im lặng KHÔNG BAO GIỜ là "false".
- Với trường NGÀY THÁNG: nếu người dùng nói tương đối ("hôm nay", "hôm qua", "N ngày nay/trước/rồi"),
  tự quy đổi sang ngày cụ thể YYYY-MM-DD dựa trên "hôm nay" đã cho ở trên - KHÔNG bỏ trống chỉ vì
  người dùng không nói ngày tuyệt đối.

Vài lượt hội thoại gần đây nhất (để BƯỚC 2 tránh lặp nguyên văn cách hỏi trước đó):
{history}

BƯỚC 2 - HỎI TIẾP: viết MỘT câu hỏi tiếng Việt tự nhiên, ngắn gọn, diễn đạt lại ý sau:
"{next_script_hint}"
Diễn đạt KHÁC đi so với các câu hỏi trước đó của trợ lý ở trên (đổi từ ngữ/cấu trúc câu), miễn giữ
đúng ý cần hỏi.

QUY TẮC CHUNG:
- TUYỆT ĐỐI KHÔNG chẩn đoán bệnh, KHÔNG đề xuất mức độ khẩn cấp, KHÔNG đưa hướng xử trí - đó không
  phải việc của bạn.
- Chỉ trả về MỘT JSON phẳng đúng 2 khoá: {{"extracted": {{...}}, "next_question": "..."}}"""


def _format_history(conversation: list[dict[str, str]], limit: int = 6) -> str:
    if not conversation:
        return "(chưa có lượt nào trước đó)"
    recent = conversation[-limit:]
    return "\n".join(
        f"{'Người bệnh' if turn.get('role') == 'user' else 'Trợ lý'}: {turn.get('content', '')}" for turn in recent
    )


# temperature cao hơn CHỈ dùng cho bước "diễn đạt lại câu hỏi" (không trích xuất field ở đây, nên
# không đánh đổi độ chính xác) - temperature=0 mặc định của hệ thống khiến LLM trả gần như Y HỆT một
# câu cho cùng 1 script_hint mỗi lần, làm hội thoại cảm giác "học thuộc lòng" thay vì tự nhiên (phát
# hiện qua test tay với LLM thật).
_QUESTION_TEMPERATURE = 0.7

# temperature THẤP HƠN call trên (chỉ 0.3, không phải 0.7) vì call này CÒN GÁNH việc trích xuất field -
# tăng đủ để câu hỏi ở BƯỚC 2 bớt lặp khuôn, nhưng không tăng cao tới mức ảnh hưởng đáng kể độ tin cậy
# JSON/field ở BƯỚC 1. Đánh đổi này do người dùng chọn tường minh (0.3, không phải giữ 0).
_COMBINED_TEMPERATURE = 0.3


def _generate_question(
    cluster: QuestionCluster,
    *,
    conversation: list[dict[str, str]] | None = None,
    credential: provider_router.LLMCredential | None,
) -> tuple[str, bool]:
    """Gọi LLM 1 lần CHỈ để diễn đạt câu hỏi (hướng C, call thứ 2). Trả (câu hỏi, llm_used)."""
    system_prompt = _QUESTION_ONLY_SYSTEM.format(
        script_hint=cluster.script_hint, history=_format_history(conversation or []),
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
    next_cluster: QuestionCluster | None = None,
    asked_ids: frozenset[str] = frozenset(),
    conversation: list[dict[str, str]] | None = None,
    credential: provider_router.LLMCredential | None = None,
) -> TurnResult:
    """Một lượt hỏi-đáp, ghép đúng hướng C/E theo stage (mục 2, `_guidance/fever-detect-agent-task.md`).

    `cluster`: cụm câu hỏi mà `message` đang trả lời.
    `next_cluster`: cụm kế tiếp ĐÃ BIẾT TRƯỚC từ `stage_machine.next_cluster(protocol, stage, answers)`
    (tính trên `answers` TRƯỚC lượt này) - không phụ thuộc kết quả extract lượt này, đúng kiến trúc.
    `asked_ids`: các cụm ĐÃ hỏi trong toàn phiên (kể cả những cụm trả lời "unknown") - BẮT BUỘC
    truyền đúng, nếu không hướng C sẽ chọn lại đúng cụm vừa hỏi thay vì tiến tới cụm kế tiếp khi field
    vẫn còn "unknown" (bug đã phát hiện qua Checkpoint 6 của fever: hội thoại treo vô hạn ở Stage 3A).
    """
    credential = credential or protocol.default_credential
    stage_log.step(
        session_id, turn=turn, stage=stage, cluster_id=cluster.id, event="user_message",
        input=None, output={"text": message},
    )

    if stage in protocol.gate_stages:
        return _run_turn_gate(
            protocol, session_id, turn=turn, stage=stage, cluster=cluster, message=message, answers=answers,
            asked_ids=asked_ids, conversation=conversation, credential=credential,
        )
    return _run_turn_combined(
        protocol, session_id, turn=turn, stage=stage, cluster=cluster, message=message, answers=answers,
        next_cluster=next_cluster, asked_ids=asked_ids, conversation=conversation, credential=credential,
    )


def _run_turn_gate(
    protocol: SymptomProtocol,
    session_id: str,
    *,
    turn: int,
    stage: str,
    cluster: QuestionCluster,
    message: str,
    answers: dict[str, TriState],
    asked_ids: frozenset[str],
    conversation: list[dict[str, str]] | None,
    credential: provider_router.LLMCredential | None,
) -> TurnResult:
    """Hướng C (`protocol.gate_stages`): extract -> rule-based red-flag gate -> next_question/thông
    báo cấp cứu. 2 call LLM TÁCH BIỆT, call thứ 2 (next_question) CHỈ chạy khi KHÔNG phải EMERGENCY."""
    extracted = extract_cluster(protocol, cluster, message, session_id=session_id, turn=turn, stage=stage, credential=credential)
    opportunistic = scan_opportunistic_fields(protocol, message)
    merged = _merge_answers(answers, opportunistic, extracted)
    merged = _apply_derived_fields(protocol, merged)

    with stage_log.tool(
        session_id, turn=turn, stage=stage, cluster_id=cluster.id,
        tool="rule_engine.evaluate", input=merged,
    ) as rec:
        rule_result = rule_engine.evaluate(protocol, merged)
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
        # KHÔNG gọi next_question - dừng ngay theo P0-5, không chờ hỏi hết checklist.
        stage_log.step(
            session_id, turn=turn, stage=stage, cluster_id=cluster.id, event="agent_message",
            input=None, output={"text": protocol.emergency_message}, llm_used=False,
        )
        stage_log.step(
            session_id, turn=turn, stage=stage, cluster_id=cluster.id, event="stop", stop_reason="RED_FLAG",
        )
        return TurnResult(
            answers=merged, extracted=extracted, agent_message=protocol.emergency_message,
            next_cluster=None, llm_used=True, emergency=True,
            triage_level=rule_result.triage_level,
            reason_codes=rule_result.reason_codes, triggered_rules=rule_result.triggered_rules,
        )

    with stage_log.tool(
        session_id, turn=turn, stage=stage, cluster_id=cluster.id,
        tool="stage_machine.next_cluster", input={"stage": stage},
    ) as rec:
        following = stage_machine.next_cluster(protocol, stage, merged, asked_ids=asked_ids | {cluster.id})
        rec.output = {"cluster_id": following.id if following else None}

    question, question_llm_used = (
        _generate_question(following, conversation=conversation, credential=credential)
        if following is not None
        else ("", False)
    )
    stage_log.step(
        session_id, turn=turn, stage=stage, cluster_id=cluster.id, event="agent_message",
        input=None, output={"text": question}, llm_used=question_llm_used,
    )

    return TurnResult(
        answers=merged, extracted=extracted, agent_message=question,
        next_cluster=following, llm_used=True, emergency=False,
        triage_level=rule_result.triage_level,
        reason_codes=rule_result.reason_codes, triggered_rules=rule_result.triggered_rules,
    )


def _run_turn_combined(
    protocol: SymptomProtocol,
    session_id: str,
    *,
    turn: int,
    stage: str,
    cluster: QuestionCluster,
    message: str,
    answers: dict[str, TriState],
    next_cluster: QuestionCluster | None,
    asked_ids: frozenset[str],
    conversation: list[dict[str, str]] | None,
    credential: provider_router.LLMCredential | None,
) -> TurnResult:
    """Hướng E (mọi stage ngoài `protocol.gate_stages`): 1 call JSON gộp extract + next_question.
    `next_cluster` được chọn TRƯỚC lượt này từ `answers` cũ - không phụ thuộc kết quả extract lượt
    này (đúng kiến trúc)."""
    with stage_log.tool(
        session_id, turn=turn, stage=stage, cluster_id=cluster.id,
        tool="stage_machine.next_cluster", input={"stage": stage},
    ) as rec:
        following = (
            next_cluster
            if next_cluster is not None
            else stage_machine.next_cluster(protocol, stage, answers, asked_ids=asked_ids | {cluster.id})
        )
        rec.output = {"cluster_id": following.id if following else None}

    stage_log.step(
        session_id, turn=turn, stage=stage, cluster_id=cluster.id, event="retrieve",
        input={"cluster_id": cluster.id}, output={"fields": list(cluster.fields), "schema_size": len(cluster.fields)},
    )

    # Không chỉ nhặt field "an toàn" cố định (`protocol.safety_signal_fields`) mà còn nhặt MỌI field
    # còn thiếu thuộc CÁC CỤM KHÁC trong CÙNG stage - người dùng hay trả lời gộp nhiều ý cùng lúc, nếu
    # chỉ nhặt đúng field của cụm đang hỏi thì hệ thống hỏi lại cứng nhắc dù họ đã nói trước (phát
    # hiện qua test tay với LLM thật). Phạm vi giới hạn trong 1 stage (không quét toàn bộ 101 field)
    # để giữ prompt gọn và tránh tăng rủi ro LLM suy diễn/gán nhầm field ở xa ngữ cảnh đang hỏi.
    stage_field_keys = {key for stage_cluster in clusters_for_stage(protocol, stage) for key in stage_cluster.fields}
    safety_extra_keys = tuple(
        key for key in (set(protocol.safety_signal_fields) | stage_field_keys) if key not in cluster.fields
    )
    system_prompt = _COMBINED_SYSTEM.format(
        today=_today_iso(),
        history=_format_history(conversation or []),
        field_specs=_field_specs(protocol, cluster.fields),
        safety_field_specs=_field_specs(protocol, safety_extra_keys),
        next_script_hint=following.script_hint if following is not None else "(đã đủ thông tin, không cần hỏi thêm)",
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ]
    parsed, parse_error, provider_name, model_name, response_text, latency_ms = _invoke_json(
        messages, credential, temperature=_COMBINED_TEMPERATURE,
    )

    stage_log.llm_io(
        session_id, turn=turn, stage=stage, cluster_id=cluster.id, purpose="extract+next_question",
        provider=provider_name, model=model_name, messages=messages, response_text=response_text,
        parsed=parsed, tokens=None, latency_ms=latency_ms, parse_error=parse_error,
    )

    parsed = parsed or {}
    extracted = _collect(protocol, cluster, parsed.get("extracted") or {}, message)
    # batch_negation=False TƯỜNG MINH (turn-scoping): cờ phủ định gộp chỉ có nghĩa cho ĐÚNG cụm vừa
    # được hỏi. `safety_extra_keys` là field của các cụm KHÁC mà người dùng chưa hề được hỏi tới - để
    # cờ lan sang đây tức là một câu "không có gì cả" trả lời cụm này sẽ đóng luôn cả stage.
    safety_extracted = _collect_fields(protocol, safety_extra_keys, parsed.get("extracted") or {}, batch_negation=False)
    opportunistic = scan_opportunistic_fields(protocol, message)
    merged = _merge_answers(answers, opportunistic, safety_extracted, extracted)
    merged = _apply_derived_fields(protocol, merged)

    stage_log.step(
        session_id, turn=turn, stage=stage, cluster_id=cluster.id, event="extract",
        input=None, output=extracted,
        answers_delta={key: f"unknown -> {value}" for key, value in extracted.items()},
    )

    # P0-5: dấu hiệu khẩn cấp có thể được mô tả TÌNH CỜ dù chưa tới lượt hỏi gate stage (vd ca E2,
    # CS Part 8 của fever: co giật được mô tả ngay ở tin nhắn đầu tiên trong khi đang ở Stage 0) -
    # phải chốt đỏ NGAY, không đợi hết các stage trước rồi mới quét ở gate stage. Dùng lại 1 call đã
    # gọi, không tốn thêm call nào (hướng E vốn đã là 1 call gộp).
    with stage_log.tool(
        session_id, turn=turn, stage=stage, cluster_id=cluster.id,
        tool="rule_engine.evaluate", input=merged,
    ) as rec:
        rule_result = rule_engine.evaluate(protocol, merged)
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
        stage_log.step(
            session_id, turn=turn, stage=stage, cluster_id=cluster.id, event="agent_message",
            input=None, output={"text": protocol.emergency_message}, llm_used=False,
        )
        stage_log.step(
            session_id, turn=turn, stage=stage, cluster_id=cluster.id, event="stop", stop_reason="RED_FLAG",
        )
        return TurnResult(
            answers=merged, extracted={**extracted, **safety_extracted}, agent_message=protocol.emergency_message,
            next_cluster=None, llm_used=True, emergency=True,
            triage_level=rule_result.triage_level,
            reason_codes=rule_result.reason_codes, triggered_rules=rule_result.triggered_rules,
        )

    question = str(parsed.get("next_question") or "").strip()
    llm_used = parse_error is None and bool(question)
    if not question:
        question = following.script_hint if following is not None else ""

    stage_log.step(
        session_id, turn=turn, stage=stage, cluster_id=cluster.id, event="agent_message",
        input=None, output={"text": question}, llm_used=llm_used,
    )

    return TurnResult(
        answers=merged, extracted=extracted, agent_message=question,
        next_cluster=following, llm_used=True, emergency=False,
        triage_level=rule_result.triage_level,
        reason_codes=rule_result.reason_codes, triggered_rules=rule_result.triggered_rules,
    )


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
