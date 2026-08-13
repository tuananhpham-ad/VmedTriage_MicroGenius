"""State machine THUẦN rule-based, dùng chung cho mọi symptom_group: chọn cụm câu hỏi kế tiếp, và
quyết định khi nào dừng hội thoại. Không gọi LLM, không import `provider_router`/`llm`.

Mọi quyết định lâm sàng (route/emergency-scan/self-care checklist/ngân sách theo mức) đều đi qua các
hook trên `protocol: SymptomProtocol` - module này chỉ lo phần "duyệt danh sách cụm theo đúng thứ tự,
tôn trọng điều kiện skip, và biết khi nào nên dừng".
"""

from __future__ import annotations

from typing import Literal

from src.services.symptom_protocol.models import QuestionCluster
from src.services.symptom_protocol.protocol import SymptomProtocol, clusters_for_stage

StopReason = Literal["RED_FLAG", "SUFFICIENT_EVIDENCE", "BUDGET_EXHAUSTED", "USER_CANNOT_CONTINUE"]


def _is_filled(value: object) -> bool:
    return value is not None and value != "unknown" and value != ""


def _cluster_needs_answer(cluster: QuestionCluster, answers: dict[str, object]) -> bool:
    return any(not _is_filled(answers.get(key)) for key in cluster.fields)


def _cluster_is_optional_tier(protocol: SymptomProtocol, cluster: QuestionCluster) -> bool:
    """Ngân sách chỉ được cắt cụm mà TOÀN BỘ field bên trong là tier O/H (làm giàu/handoff) - cụm có
    bất kỳ field M0/M1/C nào vẫn phải hỏi dù đã vượt ngân sách danh nghĩa (bài học rút ra khi chạy
    fever qua LLM thật: cắt nhầm field bắt buộc khiến hệ thống không bao giờ đủ dữ kiện kết luận)."""
    return all(protocol.fields_by_key[key].tier in ("O", "H") for key in cluster.fields)


def _cluster_is_skipped(protocol: SymptomProtocol, stage: str, cluster: QuestionCluster, answers: dict[str, object]) -> bool:
    emergency_scan_stage, early_visit_scan_stage = protocol.gate_stages
    if stage == early_visit_scan_stage and protocol.provisional_emergency_signal(answers):
        return True
    return protocol.skip_rule(cluster, answers)


def next_cluster(
    protocol: SymptomProtocol,
    stage: str,
    answers: dict[str, object],
    *,
    asked_ids: frozenset[str] = frozenset(),
) -> QuestionCluster | None:
    """Cụm câu hỏi kế tiếp trong `stage` hiện tại, hoặc `None` nếu đã hết cụm khả dụng (caller khi đó
    tự chuyển sang `next_stage(protocol, stage)`)."""
    for cluster in clusters_for_stage(protocol, stage):
        if cluster.id in asked_ids:
            continue
        if _cluster_is_skipped(protocol, stage, cluster, answers):
            continue
        if not _cluster_needs_answer(cluster, answers):
            continue
        return cluster
    return None


def next_stage(protocol: SymptomProtocol, stage: str) -> str | None:
    try:
        index = protocol.stage_order.index(stage)
    except ValueError:
        return None
    if index + 1 >= len(protocol.stage_order):
        return None
    return protocol.stage_order[index + 1]


def should_stop(
    protocol: SymptomProtocol,
    stage: str,
    answers: dict[str, object],
    *,
    asked_count: int,
    route: str | None = None,
    known_triage_level: str | None = None,
    user_can_continue: bool = True,
) -> StopReason | None:
    """Áp theo thứ tự: chốt đỏ > đủ căn cứ > hết ngân sách > người dùng không tiếp tục được.
    `asked_count` là số CỤM đã hỏi trong toàn phiên (không phải field đơn lẻ)."""
    if not user_can_continue:
        return "USER_CANNOT_CONTINUE"

    if protocol.provisional_emergency_signal(answers) or known_triage_level == "EMERGENCY":
        return "RED_FLAG"

    resolved_route = route or protocol.determine_route(answers)

    if (
        stage == protocol.stage_order[-1]
        and next_cluster(protocol, stage, answers) is None
        and protocol.self_care_checklist_satisfied(answers)
    ):
        return "SUFFICIENT_EVIDENCE"

    if protocol.stage_order.index(stage) < protocol.stage_order.index(protocol.budget_floor_stage):
        return None

    budget_max = protocol.budget[protocol.budget_key(answers, resolved_route, known_triage_level)][1]
    if asked_count < budget_max:
        return None

    candidate = next_cluster(protocol, stage, answers)
    if candidate is None or _cluster_is_optional_tier(protocol, candidate):
        return "BUDGET_EXHAUSTED"

    return None
