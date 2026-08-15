"""Lớp mỏng: fever "cắm" vào rule engine dùng chung (`src/services/symptom_protocol/rule_engine.py`)
qua `FEVER_PROTOCOL` (`fever_protocol.py` - chứa toàn bộ rule catalog `R-E-xx`/`R-V-xx`/`R-G-01`).

Chữ ký `evaluate(answers) -> RuleEngineResult` GIỮ NGUYÊN như bản fever-riêng trước khi tách generic
engine (xem `_guidance/fever-detect-agent-task.md`, mục "kế thừa được") - caller cũ
(`fever_intake_agent`, `fever_session`, toàn bộ test Checkpoint 3) không cần sửa gì.

Ranh giới không đổi: module THUẦN rule-based - không gọi LLM, là gate giữa `extract` và
`next_question` ở gate stage (kiến trúc hướng C), và là nguồn thật duy nhất cho
`triage_level`/`reason_codes`/`triggered_rules`.
"""

from __future__ import annotations

from src.services.engines.fever_protocol import FEVER_PROTOCOL
from src.services.symptom_protocol import rule_engine as _engine
from src.services.symptom_protocol.models import RuleMatch, TimeTarget, TriageLevel
from src.services.symptom_protocol.rule_engine import RuleEngineResult

__all__ = ["RuleEngineResult", "RuleMatch", "TimeTarget", "TriageLevel", "evaluate"]


def evaluate(answers: dict[str, object]) -> RuleEngineResult:
    """Chạy TOÀN BỘ `FEVER_PROTOCOL.rule_catalog` (KM §6.1), lấy mức triage CAO NHẤT trong các rule
    khớp (KM §0.2 - không rule nào được hạ mức đã đặt bởi rule khác)."""
    return _engine.evaluate(FEVER_PROTOCOL, answers)
