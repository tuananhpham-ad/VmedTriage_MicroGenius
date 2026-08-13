"""Rule engine THUẦN, dùng chung cho mọi symptom_group: chạy toàn bộ `protocol.rule_catalog`, lấy
mức triage CAO NHẤT trong các rule khớp - không rule nào được phép hạ mức đã đặt bởi rule khác.

`triggered_rules` chỉ gồm rule ở ĐÚNG mức thắng; `reason_codes` gom từ MỌI rule khớp (kể cả mức thấp
hơn) làm bằng chứng bổ trợ - đúng cách tài liệu Part 8 CS trình bày ca có nhiều rule cùng khớp
(rule phụ ở mức thấp hơn vẫn góp reason_code dù không phải rule "thắng").
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.services.symptom_protocol.models import LEVEL_RANK, TIME_RANK, RuleMatch, TimeTarget, TriageLevel
from src.services.symptom_protocol.protocol import SymptomProtocol


@dataclass(frozen=True, slots=True)
class RuleEngineResult:
    triage_level: TriageLevel
    time_target: TimeTarget
    reason_codes: tuple[str, ...]
    triggered_rules: tuple[str, ...]
    matches: tuple[RuleMatch, ...] = field(default_factory=tuple)


def evaluate(protocol: SymptomProtocol, answers: dict[str, object]) -> RuleEngineResult:
    matches: list[RuleMatch] = []
    for rule in protocol.rule_catalog:
        match = rule(answers, tuple(matches))
        if match is not None:
            matches.append(match)

    if not matches:
        if protocol.self_care_checklist_satisfied(answers):
            matches.append(protocol.self_care_default_rule(answers))
        else:
            matches.append(protocol.fallback_rule(answers))

    best_level: TriageLevel = max((m.level for m in matches), key=lambda level: LEVEL_RANK[level])
    winning = [m for m in matches if m.level == best_level]
    best_time_target: TimeTarget = min((m.time_target for m in winning), key=lambda t: TIME_RANK[t])

    reason_codes: list[str] = []
    triggered_rules: list[str] = []
    for match in matches:
        if match.level == best_level:
            triggered_rules.append(match.rule_id)
        for code in match.reason_codes:
            if code not in reason_codes:
                reason_codes.append(code)

    return RuleEngineResult(
        triage_level=best_level,
        time_target=best_time_target,
        reason_codes=tuple(reason_codes),
        triggered_rules=tuple(triggered_rules),
        matches=tuple(matches),
    )
