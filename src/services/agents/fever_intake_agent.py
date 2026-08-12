"""LLM extraction theo cụm cho agent fever (Bước 4, `_guidance/fever-detect-agent-task.md`).

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
import time

from src.services.agents.intake_agent import _parse_json_object
from src.services.checklists.fever_checklist import FIELDS_BY_KEY, QuestionCluster
from src.services.engines.semantic_mapper import _contains_any
from src.services.infra import fever_stage_log, provider_router

logger = logging.getLogger("vmedtriage.fever_intake")

TriState = str  # "true" | "false" | "unknown"

_TRUE_TOKENS = frozenset({"true", "có", "co", "yes", "dương tính", "duong tinh"})
_FALSE_TOKENS = frozenset({"false", "không", "khong", "no", "âm tính", "am tinh"})

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


def _field_specs(cluster: QuestionCluster) -> str:
    lines = []
    for key in cluster.fields:
        field = FIELDS_BY_KEY[key]
        kind = "true|false|unknown" if field.tri_state else "giá trị cụ thể hoặc null"
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
    system_prompt = _EXTRACTION_SYSTEM.format(batch_negation_rule=batch_rule, field_specs=_field_specs(cluster))
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
    except Exception as exc:  # JSON hỏng - không phải lỗi gọi provider
        logger.warning("fever_intake.parse_failed reason=%s", type(exc).__name__)
        return None, f"{type(exc).__name__}: {exc}", result.provider, result.model, result.text, latency_ms

    return parsed, None, result.provider, result.model, result.text, latency_ms


def _collect(cluster: QuestionCluster, parsed: dict) -> dict[str, TriState]:
    cluster_negative = bool(parsed.get("cluster_all_negative")) if cluster.batch_negation else False

    collected: dict[str, TriState] = {}
    for key in cluster.fields:
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
