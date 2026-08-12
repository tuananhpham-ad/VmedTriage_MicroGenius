"""LLM extraction theo cụm + ghép hướng C/E theo stage cho agent fever (Bước 4-5,
`_guidance/fever-detect-agent-task.md`).

Tái dùng hạ tầng đã có, không viết lại: `provider_router.complete()` +
`intake_agent._parse_json_object()` để gọi LLM/bóc JSON, và kỹ thuật `_contains_any` của
`semantic_mapper.py` để quét từ khoá nhẹ cho field "cơ hội" (field không thuộc cụm đang hỏi nhưng
xuất hiện tự nhiên trong câu trả lời tự do - đúng quy ước CS §3 "không hỏi lại field đã có giá trị
xác định").

LLM ở đây CHỈ làm một việc: trích field từ free text vào đúng schema của MỘT cụm câu hỏi
(`cluster.fields`), không bao giờ nhận toàn bộ 101 field mỗi lượt. Quyết định next_cluster/route/dừng
KHÔNG nằm ở đây - đó là việc của `fever_stage_machine.py` (Bước 2) + `fever_red_flag_engine.py`
(Bước 3), đúng `coding_convention.md` rule 1-2.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field

from src.services.agents.intake_agent import _parse_json_object
from src.services.checklists.fever_checklist import FIELDS_BY_KEY, QuestionCluster
from src.services.engines import fever_red_flag_engine, fever_stage_machine
from src.services.engines.semantic_mapper import _contains_any
from src.services.infra import fever_stage_log, provider_router

logger = logging.getLogger("vmedtriage.fever_intake")

# Thông điệp cấp cứu TĨNH, không qua LLM - đảm bảo (a) không bao giờ vi phạm P0-2 (không chẩn đoán,
# không nêu tên bệnh) vì không phụ thuộc mô hình sinh văn bản, và (b) lượt EMERGENCY chỉ tốn ĐÚNG 1
# call LLM (extract) - không có call thứ 2 cho next_question, đúng kiến trúc hướng C (mục 2 task spec)
# và P0-5 (dừng ngay, không chờ sinh câu hỏi routine).
EMERGENCY_MESSAGE = (
    "Đây là tình huống cần được cấp cứu ngay bây giờ — vui lòng gọi 115 hoặc đến ngay cơ sở y tế/"
    "khoa cấp cứu gần nhất, không chờ thêm. Thông tin đã được chuyển cho điều dưỡng ưu tiên hỗ trợ."
)

# Field an toàn "đỏ tuyệt đối" (dùng chung với provisional scan của fever_stage_machine). Ở Stage
# 0/1/2/4/5 (hướng E), schema trích xuất LUÔN kèm thêm nhóm field này dù không thuộc cụm đang hỏi -
# lý do: P0-5 ("chốt đỏ ngắt hội thoại NGAY, không chờ hỏi hết checklist") không được phép chờ tới
# lượt Stage 3A mới phát hiện. Ví dụ CS Part 8 ca E2: người dùng mô tả "tay chân đang giật, mắt trợn
# lên" ngay ở tin nhắn ĐẦU TIÊN (còn đang ở Stage 0) - hệ thống phải chốt đỏ ngay lượt đó, không đợi
# đi hết Stage 0->1->2 rồi mới tới cụm Q3-03 hỏi co giật.

TriState = str  # "true" | "false" | "unknown"

_TRUE_TOKENS = frozenset({"true", "có", "co", "yes", "dương tính", "duong tinh"})
_FALSE_TOKENS = frozenset({"false", "không", "khong", "no", "âm tính", "am tinh"})

# Xem giải thích ở EMERGENCY_MESSAGE - dùng chung danh sách field "đỏ tuyệt đối" với state machine
# để hướng E cũng quét được emergency signal tình cờ xuất hiện ngoài Stage 3A/3B.
_SAFETY_SIGNAL_FIELDS: tuple[str, ...] = fever_stage_machine.EMERGENCY_TRI_STATE_FIELDS

# Quét cơ hội: các field an toàn cốt lõi thường được người dùng chủ động mô tả ngay từ câu đầu tiên,
# trước khi tới lượt cụm hỏi tương ứng (đúng ví dụ O1, Part 8 CS). Danh sách CỐ Ý ngắn - chỉ phủ field
# `M0` có hậu quả bỏ sót cao nhất; không thay thế LLM extraction theo cụm, chỉ bổ trợ.
_OPPORTUNISTIC_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("seizure_active_now", ("đang co giật", "dang co giat", "co giật ngay", "co giat ngay")),
    ("seizure_occurred", ("co giật", "co giat")),
    ("non_blanching_rash", ("ban tím không mất", "ban tim khong mat", "ấn không mất", "an khong mat")),
    ("cyanosis", ("tím môi", "tim moi", "tím tái", "tim tai")),
    ("neck_stiffness", ("cứng gáy", "cung gay")),
    ("cold_clammy_skin", ("lạnh ẩm", "lanh am", "nổi vân tím", "noi van tim")),
)


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


def _field_specs(field_keys: tuple[str, ...]) -> str:
    lines = []
    for key in field_keys:
        field = FIELDS_BY_KEY[key]
        # Ghi rõ ngoặc kép trong chính hint để giảm khả năng model trả bareword unknown (không quote)
        # - lỗi thật gặp phải với gpt-4o-mini qua OpenRouter khi chạy Checkpoint 6(b), xem
        # _repair_bareword_unknown ở dưới (vẫn giữ lớp sửa lỗi đó làm lưới an toàn, không chỉ dựa
        # vào việc nhắc prompt).
        kind = '"true" | "false" | "unknown" (luôn có dấu ngoặc kép)' if field.tri_state else "giá trị cụ thể hoặc null"
        lines.append(f"- {key} ({field.label}) [{kind}]: {field.hint}")
    return "\n".join(lines)


_EXTRACTION_SYSTEM = """Bạn là bộ trích xuất thông tin y tế cho một hệ thống phân loại mức độ khẩn cấp.

NHIỆM VỤ DUY NHẤT: đọc tin nhắn của người dùng và điền vào ĐÚNG các trường liệt kê dưới đây, KHÔNG
được điền trường nào khác ngoài danh sách này.

QUY TẮC BẮT BUỘC:
- CHỈ trích xuất thông tin ĐÃ CÓ trong tin nhắn. TUYỆT ĐỐI KHÔNG suy diễn, KHÔNG phỏng đoán con số.
- Với trường [true|false|unknown]: trả "true" nếu người dùng xác nhận CÓ, "false" nếu XÁC NHẬN RÕ
  RÀNG không có, "unknown" nếu không nhắc tới hoặc mơ hồ. TUYỆT ĐỐI KHÔNG suy diễn im lặng thành
  "false" - im lặng luôn là "unknown".
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
"""


def extract_cluster(
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
        fever_stage_log.step(
            session_id, turn=turn, stage=log_stage, cluster_id=cluster.id, event="retrieve",
            input={"cluster_id": cluster.id}, output={"fields": list(cluster.fields), "schema_size": len(cluster.fields)},
        )

    batch_rule = _BATCH_NEGATION_RULE if cluster.batch_negation else ""
    system_prompt = _EXTRACTION_SYSTEM.format(batch_negation_rule=batch_rule, field_specs=_field_specs(cluster.fields))
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ]

    parsed, parse_error, provider_name, model_name, response_text, latency_ms = _invoke_json(messages, credential)

    if session_id is not None:
        fever_stage_log.llm_io(
            session_id, turn=turn, stage=log_stage, cluster_id=cluster.id, purpose="extract",
            provider=provider_name, model=model_name, messages=messages, response_text=response_text,
            parsed=parsed, tokens=None, latency_ms=latency_ms, parse_error=parse_error,
        )

    extracted = _collect(cluster, parsed or {})

    if session_id is not None:
        fever_stage_log.step(
            session_id, turn=turn, stage=log_stage, cluster_id=cluster.id, event="extract",
            input=None, output=extracted,
            answers_delta={key: f"unknown -> {value}" for key, value in extracted.items()},
        )

    return extracted


_BAREWORD_UNKNOWN_RE = re.compile(r'(:\s*)unknown\b(?!")')


def _repair_bareword_unknown(text: str) -> str:
    """Sửa lỗi JSON thật gặp phải với gpt-4o-mini (qua OpenRouter) khi chạy Checkpoint 6(b): model
    đọc thấy `[true|false|unknown]` trong mô tả schema rồi coi "unknown" như 1 literal JSON kiểu
    `true`/`false`/`null` và trả về KHÔNG có dấu ngoặc kép (vd `"seizure_occurred": unknown,`), khiến
    `json.loads` hỏng toàn bộ - kể cả field khác trong CÙNG response đã trích đúng (vd
    `seizure_active_now: true`) cũng bị mất theo. Chỉ thay bareword `unknown` ngay sau dấu `:` (không
    đụng tới "unknown" đã nằm trong chuỗi có ngoặc kép, vd giá trị field enum hợp lệ)."""
    return _BAREWORD_UNKNOWN_RE.sub(r'\1"unknown"', text)


def _invoke_json(
    messages: list[dict[str, str]],
    credential: provider_router.LLMCredential | None,
) -> tuple[dict | None, str | None, str, str, str, int]:
    started = time.monotonic()
    try:
        result = provider_router.complete(messages, credential=credential)
    except Exception as exc:
        logger.warning("fever_intake.extract_failed reason=%s", type(exc).__name__)
        latency_ms = int((time.monotonic() - started) * 1000)
        return None, f"{type(exc).__name__}: {exc}", "(none)", "(none)", "", latency_ms

    latency_ms = int((time.monotonic() - started) * 1000)
    try:
        parsed = _parse_json_object(result.text)
    except Exception:
        try:
            parsed = _parse_json_object(_repair_bareword_unknown(result.text))
        except Exception as exc:  # JSON vẫn hỏng sau khi đã thử sửa - không phải lỗi gọi provider
            logger.warning("fever_intake.parse_failed reason=%s", type(exc).__name__)
            return None, f"{type(exc).__name__}: {exc}", result.provider, result.model, result.text, latency_ms

    return parsed, None, result.provider, result.model, result.text, latency_ms


def _collect_fields(field_keys: tuple[str, ...], parsed: dict, *, batch_negation: bool = False) -> dict[str, TriState]:
    cluster_negative = bool(parsed.get("cluster_all_negative")) if batch_negation else False

    collected: dict[str, TriState] = {}
    for key in field_keys:
        field = FIELDS_BY_KEY[key]
        if not field.tri_state:
            raw = parsed.get(key)
            if raw not in (None, "", "null"):
                collected[key] = str(raw).strip() if not isinstance(raw, (list, tuple)) else raw
            continue

        value = _tri_state_value(parsed.get(key))
        if value == "unknown" and cluster_negative:
            value = "false"
        collected[key] = value

    return collected


def _collect(cluster: QuestionCluster, parsed: dict) -> dict[str, TriState]:
    return _collect_fields(cluster.fields, parsed, batch_negation=cluster.batch_negation)


def _merge_answers(answers: dict[str, TriState], *updates: dict[str, TriState]) -> dict[str, TriState]:
    """Gộp answers, ưu tiên giá trị TƯỜNG MINH đã trích được hơn suy đoán cơ hội - `updates` sau ghi
    đè `updates` trước, nhưng KHÔNG ghi đè giá trị answers gốc đã có (đúng CS §3: không hỏi lại field
    đã có giá trị xác định) trừ khi chính update đó là bản trích mới nhất cho field đó."""
    merged = dict(answers)
    for update in updates:
        merged.update(update)
    return merged


# --- Bước 5 — Ghép hướng C/E theo stage --------------------------------------------------------


@dataclass(slots=True)
class FeverTurnResult:
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

QUY TẮC BẮT BUỘC:
- TUYỆT ĐỐI KHÔNG chẩn đoán bệnh, KHÔNG nêu tên bệnh, KHÔNG nhận định mức độ nguy hiểm.
- Chỉ trả về đúng câu hỏi, không thêm lời dẫn hay giải thích."""

_COMBINED_SYSTEM = """Bạn là trợ lý y tế vừa trích xuất thông tin vừa hỏi tiếp câu tiếp theo.

BƯỚC 1 - TRÍCH XUẤT: đọc tin nhắn người dùng, điền vào ĐÚNG các trường liệt kê dưới đây, KHÔNG được
điền trường nào khác:
{field_specs}

NGOÀI RA, dù KHÔNG thuộc lượt hỏi này, nếu tin nhắn có TỰ MÔ TẢ bất kỳ dấu hiệu nào dưới đây, vẫn PHẢI
điền vào JSON (đây là dấu hiệu an toàn khẩn cấp, không được bỏ sót dù chưa tới lượt hỏi):
{safety_field_specs}

QUY TẮC TRÍCH XUẤT:
- CHỈ trích xuất thông tin ĐÃ CÓ trong tin nhắn. TUYỆT ĐỐI KHÔNG suy diễn, KHÔNG phỏng đoán.
- Với trường [true|false|unknown]: "true" nếu xác nhận CÓ, "false" nếu XÁC NHẬN RÕ RÀNG không có,
  "unknown" nếu không nhắc tới/mơ hồ. Im lặng KHÔNG BAO GIỜ là "false".

BƯỚC 2 - HỎI TIẾP: viết MỘT câu hỏi tiếng Việt tự nhiên, ngắn gọn, diễn đạt lại ý sau:
"{next_script_hint}"

QUY TẮC CHUNG:
- TUYỆT ĐỐI KHÔNG chẩn đoán bệnh, KHÔNG đề xuất mức độ khẩn cấp, KHÔNG đưa hướng xử trí - đó không
  phải việc của bạn.
- Chỉ trả về MỘT JSON phẳng đúng 2 khoá: {{"extracted": {{...}}, "next_question": "..."}}"""


def _generate_question(
    cluster: QuestionCluster,
    *,
    credential: provider_router.LLMCredential | None,
) -> tuple[str, bool]:
    """Gọi LLM 1 lần CHỈ để diễn đạt câu hỏi (hướng C, call thứ 2). Trả (câu hỏi, llm_used)."""
    system_prompt = _QUESTION_ONLY_SYSTEM.format(script_hint=cluster.script_hint)
    try:
        result = provider_router.complete([{"role": "user", "content": system_prompt}], credential=credential)
        question = result.text.strip().strip('"')
        if question:
            return question, True
    except Exception as exc:
        logger.warning("fever_intake.question_failed reason=%s", type(exc).__name__)
    return cluster.script_hint, False


def run_turn(
    session_id: str,
    *,
    turn: int,
    stage: str,
    cluster: QuestionCluster,
    message: str,
    answers: dict[str, TriState],
    next_cluster: QuestionCluster | None = None,
    asked_ids: frozenset[str] = frozenset(),
    credential: provider_router.LLMCredential | None = None,
) -> FeverTurnResult:
    """Một lượt hỏi-đáp, ghép đúng hướng C/E theo stage (mục 2 task spec).

    `cluster`: cụm câu hỏi mà `message` đang trả lời.
    `next_cluster`: cụm kế tiếp ĐÃ BIẾT TRƯỚC từ `fever_stage_machine.next_cluster(stage, answers)`
    (tính trên `answers` TRƯỚC lượt này) - không phụ thuộc kết quả extract lượt này, đúng kiến trúc.
    `asked_ids`: các cụm ĐÃ hỏi trong toàn phiên (kể cả những cụm trả lời "unknown") - BẮT BUỘC
    truyền đúng, nếu không hướng C (Stage 3A/3B) sẽ chọn lại đúng cụm vừa hỏi thay vì tiến tới cụm kế
    tiếp khi field vẫn còn "unknown" (bug đã phát hiện qua Checkpoint 6: hội thoại treo vô hạn ở
    Stage 3A vì `fever_stage_machine.next_cluster` không biết cụm nào đã hỏi rồi).
    """
    fever_stage_log.step(
        session_id, turn=turn, stage=stage, cluster_id=cluster.id, event="user_message",
        input=None, output={"text": message},
    )

    if stage in ("3A", "3B"):
        return _run_turn_gate(
            session_id, turn=turn, stage=stage, cluster=cluster, message=message, answers=answers,
            asked_ids=asked_ids, credential=credential,
        )
    return _run_turn_combined(
        session_id, turn=turn, stage=stage, cluster=cluster, message=message, answers=answers,
        next_cluster=next_cluster, asked_ids=asked_ids, credential=credential,
    )


def _run_turn_gate(
    session_id: str,
    *,
    turn: int,
    stage: str,
    cluster: QuestionCluster,
    message: str,
    answers: dict[str, TriState],
    asked_ids: frozenset[str],
    credential: provider_router.LLMCredential | None,
) -> FeverTurnResult:
    """Hướng C (Stage 3A/3B): extract -> rule-based red-flag gate -> next_question/thông báo cấp cứu.
    2 call LLM TÁCH BIỆT, và call thứ 2 (next_question) CHỈ chạy khi KHÔNG phải EMERGENCY."""
    extracted = extract_cluster(cluster, message, session_id=session_id, turn=turn, stage=stage, credential=credential)
    opportunistic = scan_opportunistic_fields(message)
    merged = _merge_answers(answers, opportunistic, extracted)

    with fever_stage_log.tool(
        session_id, turn=turn, stage=stage, cluster_id=cluster.id,
        tool="red_flag_engine.evaluate", input=merged,
    ) as rec:
        rule_result = fever_red_flag_engine.evaluate(merged)
        rec.output = {
            "triage_level": rule_result.triage_level,
            "reason_codes": list(rule_result.reason_codes),
            "triggered_rules": list(rule_result.triggered_rules),
        }

    is_emergency = rule_result.triage_level == "EMERGENCY"
    fever_stage_log.step(
        session_id, turn=turn, stage=stage, cluster_id=cluster.id, event="rule_gate",
        input=None, output={"triage_level": rule_result.triage_level},
        stop_reason="RED_FLAG" if is_emergency else None,
    )

    if is_emergency:
        # KHÔNG gọi next_question - dừng ngay theo P0-5, không chờ hỏi hết checklist.
        fever_stage_log.step(
            session_id, turn=turn, stage=stage, cluster_id=cluster.id, event="agent_message",
            input=None, output={"text": EMERGENCY_MESSAGE}, llm_used=False,
        )
        fever_stage_log.step(
            session_id, turn=turn, stage=stage, cluster_id=cluster.id, event="stop", stop_reason="RED_FLAG",
        )
        return FeverTurnResult(
            answers=merged, extracted=extracted, agent_message=EMERGENCY_MESSAGE,
            next_cluster=None, llm_used=True, emergency=True,
            triage_level=rule_result.triage_level,
            reason_codes=rule_result.reason_codes, triggered_rules=rule_result.triggered_rules,
        )

    with fever_stage_log.tool(
        session_id, turn=turn, stage=stage, cluster_id=cluster.id,
        tool="fever_stage_machine.next_cluster", input={"stage": stage},
    ) as rec:
        following = fever_stage_machine.next_cluster(stage, merged, asked_ids=asked_ids | {cluster.id})
        rec.output = {"cluster_id": following.id if following else None}

    question, question_llm_used = (
        _generate_question(following, credential=credential) if following is not None else ("", False)
    )
    fever_stage_log.step(
        session_id, turn=turn, stage=stage, cluster_id=cluster.id, event="agent_message",
        input=None, output={"text": question}, llm_used=question_llm_used,
    )

    return FeverTurnResult(
        answers=merged, extracted=extracted, agent_message=question,
        next_cluster=following, llm_used=True, emergency=False,
        triage_level=rule_result.triage_level,
        reason_codes=rule_result.reason_codes, triggered_rules=rule_result.triggered_rules,
    )


def _run_turn_combined(
    session_id: str,
    *,
    turn: int,
    stage: str,
    cluster: QuestionCluster,
    message: str,
    answers: dict[str, TriState],
    next_cluster: QuestionCluster | None,
    asked_ids: frozenset[str],
    credential: provider_router.LLMCredential | None,
) -> FeverTurnResult:
    """Hướng E (Stage 0,1,2,4,5): 1 call JSON gộp extract + next_question. `next_cluster` được chọn
    TRƯỚC lượt này từ `answers` cũ - không phụ thuộc kết quả extract lượt này (đúng kiến trúc)."""
    with fever_stage_log.tool(
        session_id, turn=turn, stage=stage, cluster_id=cluster.id,
        tool="fever_stage_machine.next_cluster", input={"stage": stage},
    ) as rec:
        following = (
            next_cluster
            if next_cluster is not None
            else fever_stage_machine.next_cluster(stage, answers, asked_ids=asked_ids | {cluster.id})
        )
        rec.output = {"cluster_id": following.id if following else None}

    fever_stage_log.step(
        session_id, turn=turn, stage=stage, cluster_id=cluster.id, event="retrieve",
        input={"cluster_id": cluster.id}, output={"fields": list(cluster.fields), "schema_size": len(cluster.fields)},
    )

    safety_extra_keys = tuple(key for key in _SAFETY_SIGNAL_FIELDS if key not in cluster.fields)
    system_prompt = _COMBINED_SYSTEM.format(
        field_specs=_field_specs(cluster.fields),
        safety_field_specs=_field_specs(safety_extra_keys),
        next_script_hint=following.script_hint if following is not None else "(đã đủ thông tin, không cần hỏi thêm)",
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ]
    parsed, parse_error, provider_name, model_name, response_text, latency_ms = _invoke_json(messages, credential)

    fever_stage_log.llm_io(
        session_id, turn=turn, stage=stage, cluster_id=cluster.id, purpose="extract+next_question",
        provider=provider_name, model=model_name, messages=messages, response_text=response_text,
        parsed=parsed, tokens=None, latency_ms=latency_ms, parse_error=parse_error,
    )

    parsed = parsed or {}
    extracted = _collect(cluster, parsed.get("extracted") or {})
    safety_extracted = _collect_fields(safety_extra_keys, parsed.get("extracted") or {})
    opportunistic = scan_opportunistic_fields(message)
    merged = _merge_answers(answers, opportunistic, safety_extracted, extracted)

    fever_stage_log.step(
        session_id, turn=turn, stage=stage, cluster_id=cluster.id, event="extract",
        input=None, output=extracted,
        answers_delta={key: f"unknown -> {value}" for key, value in extracted.items()},
    )

    # P0-5: dấu hiệu khẩn cấp có thể được mô tả TÌNH CỜ dù chưa tới lượt hỏi Stage 3A/3B (vd ca E2,
    # CS Part 8: co giật được mô tả ngay ở tin nhắn đầu tiên trong khi đang ở Stage 0) - phải chốt đỏ
    # NGAY, không đợi hết Stage 0->1->2 rồi mới quét ở Stage 3A. Dùng lại 1 call đã gọi, không tốn
    # thêm call nào (hướng E vốn đã là 1 call gộp).
    with fever_stage_log.tool(
        session_id, turn=turn, stage=stage, cluster_id=cluster.id,
        tool="red_flag_engine.evaluate", input=merged,
    ) as rec:
        rule_result = fever_red_flag_engine.evaluate(merged)
        rec.output = {
            "triage_level": rule_result.triage_level,
            "reason_codes": list(rule_result.reason_codes),
            "triggered_rules": list(rule_result.triggered_rules),
        }
    is_emergency = rule_result.triage_level == "EMERGENCY"
    fever_stage_log.step(
        session_id, turn=turn, stage=stage, cluster_id=cluster.id, event="rule_gate",
        input=None, output={"triage_level": rule_result.triage_level},
        stop_reason="RED_FLAG" if is_emergency else None,
    )

    if is_emergency:
        fever_stage_log.step(
            session_id, turn=turn, stage=stage, cluster_id=cluster.id, event="agent_message",
            input=None, output={"text": EMERGENCY_MESSAGE}, llm_used=False,
        )
        fever_stage_log.step(
            session_id, turn=turn, stage=stage, cluster_id=cluster.id, event="stop", stop_reason="RED_FLAG",
        )
        return FeverTurnResult(
            answers=merged, extracted={**extracted, **safety_extracted}, agent_message=EMERGENCY_MESSAGE,
            next_cluster=None, llm_used=True, emergency=True,
            triage_level=rule_result.triage_level,
            reason_codes=rule_result.reason_codes, triggered_rules=rule_result.triggered_rules,
        )

    question = str(parsed.get("next_question") or "").strip()
    llm_used = parse_error is None and bool(question)
    if not question:
        question = following.script_hint if following is not None else ""

    fever_stage_log.step(
        session_id, turn=turn, stage=stage, cluster_id=cluster.id, event="agent_message",
        input=None, output={"text": question}, llm_used=llm_used,
    )

    return FeverTurnResult(
        answers=merged, extracted=extracted, agent_message=question,
        next_cluster=following, llm_used=True, emergency=False,
        triage_level=rule_result.triage_level,
        reason_codes=rule_result.reason_codes, triggered_rules=rule_result.triggered_rules,
    )


def scan_opportunistic_fields(message: str) -> dict[str, TriState]:
    """Quét từ khoá nhẹ (kỹ thuật `_contains_any` của `semantic_mapper.py`) cho field an toàn cốt
    lõi có thể xuất hiện tự nhiên trước khi tới lượt hỏi cụm tương ứng. CHỈ trả `"true"` khi khớp từ
    khoá - không bao giờ trả `"false"` (im lặng không phải bằng chứng phủ định, đúng P0-4). Caller
    (`run_turn`, Bước 5) chịu trách nhiệm không ghi đè giá trị đã có."""
    normalized = (message or "").casefold()
    found: dict[str, TriState] = {}
    for key, keywords in _OPPORTUNISTIC_KEYWORDS:
        if _contains_any(normalized, keywords):
            found[key] = "true"
    return found
