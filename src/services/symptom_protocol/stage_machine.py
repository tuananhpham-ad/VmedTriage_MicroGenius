"""State machine THUẦN rule-based, dùng chung cho mọi symptom_group: chọn cụm câu hỏi kế tiếp, và
quyết định khi nào dừng hội thoại. Không gọi LLM, không import `provider_router`/`llm`.

Mọi quyết định lâm sàng (route/emergency-scan/self-care checklist/ngân sách theo mức) đều đi qua các
hook trên `protocol: SymptomProtocol` - module này chỉ lo phần "duyệt danh sách cụm theo đúng thứ tự,
tôn trọng điều kiện skip, và biết khi nào nên dừng".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.services.symptom_protocol.models import QuestionCluster
from src.services.symptom_protocol.protocol import SymptomProtocol, clusters_for_stage

StopReason = Literal["RED_FLAG", "SUFFICIENT_EVIDENCE", "BUDGET_EXHAUSTED", "USER_CANNOT_CONTINUE"]


def is_filled(value: object) -> bool:
    """Field đã có câu trả lời XÁC ĐỊNH chưa. Nguồn duy nhất của khái niệm này cho toàn hệ thống -
    `intake_agent` và `retraction` cùng dùng, để "đã điền" không có 2 định nghĩa lệch nhau."""
    return value is not None and value != "unknown" and value != ""


# Giá trị coi là PHỦ ĐỊNH field cha. Hẹp có chủ đích: "unknown" KHÔNG phải phủ định - người bệnh im
# lặng không có nghĩa là họ trả lời "không". `retraction.py` import lại đúng tập này để khái niệm
# "phủ định field cha" chỉ có MỘT định nghĩa trong hệ thống.
NEGATED_PARENT_VALUES: frozenset[str] = frozenset({"false", "none"})

# Tier BẮT BUỘC phải có căn cứ trước khi được kết luận - xem `mandatory_fields_covered`.
MANDATORY_TIERS: frozenset[str] = frozenset({"M0", "M1"})


def field_not_applicable(protocol: SymptomProtocol, key: str, answers: dict[str, object]) -> bool:
    """Field này có mất hết ý nghĩa vì field CHA của nó đã bị phủ định không.

    `protocol.field_dependencies` từ trước tới nay chỉ được `retraction.py` đọc, và chỉ theo một
    chiều: XOÁ field con khi người bệnh rút lại lời khai. Nhưng quan hệ đó còn một hệ quả thứ hai
    chưa ai dùng - đã trả lời "không suy giảm miễn dịch" thì "nguyên nhân suy giảm miễn dịch là gì"
    không phải câu hỏi CÒN THIẾU, nó là câu hỏi VÔ NGHĨA. Thiếu hàm này, `cluster_needs_answer` thấy
    field con vẫn `unknown` nên hỏi lại đúng thứ người bệnh vừa loại trừ (Q4-03/Q4-05 của fever vẫn
    bị hỏi sau khi câu sàng lọc rủi ro Q4-00 đã phủ định cả cụm)."""
    for parent, dependents in protocol.field_dependencies.items():
        if key in dependents and answers.get(parent) in NEGATED_PARENT_VALUES:
            return True
    return False


def field_is_settled(protocol: SymptomProtocol, key: str, answers: dict[str, object]) -> bool:
    """Field đã có căn cứ: hoặc điền thật, hoặc không áp dụng vì field cha đã bị phủ định."""
    return is_filled(answers.get(key)) or field_not_applicable(protocol, key, answers)


def cluster_needs_answer(
    protocol: SymptomProtocol, cluster: QuestionCluster, answers: dict[str, object],
) -> bool:
    """Cụm còn field nào chưa có căn cứ không. Public vì `screening.py` phải dùng ĐÚNG định nghĩa này
    để biết một nhóm cơ quan đã giải quyết xong chưa - hai định nghĩa lệch nhau sẽ làm câu sàng lọc
    liệt kê nhóm mà `next_cluster` không còn định hỏi (hoặc ngược lại)."""
    return any(not field_is_settled(protocol, key, answers) for key in cluster.fields)


def mandatory_fields_covered(protocol: SymptomProtocol, answers: dict[str, object]) -> bool:
    """Mọi field tier M0/M1 đã có căn cứ chưa - điều kiện AN TOÀN của việc dừng sớm.

    `self_care_checklist_satisfied` một mình KHÔNG đủ để cho phép dừng: checklist của fever (KM §5.4)
    chỉ đọc 8 field và không đụng tới bất kỳ field nào của Stage 4 (thai sản, suy giảm miễn dịch,
    bệnh mạn tính). Dừng khi checklist xanh mà chưa quét Stage 4 sẽ gán "tự theo dõi" cho người đang
    mang thai chỉ vì chưa bao giờ hỏi họ. CS Part 4.2 nói rõ thứ được phép rút gọn là phần tier O/H
    của Stage 4/5, KHÔNG phải field M1 liên quan route.

    Giá trị ÂM thu được từ câu sàng lọc gộp cũng tính là "đã có căn cứ" - đó chính là thứ làm việc
    dừng sớm khả thi mà không phải hỏi tuần tự từng cụm một."""
    return all(
        field_is_settled(protocol, key, answers)
        for key, spec in protocol.fields_by_key.items()
        if spec.tier in MANDATORY_TIERS
    )


_cluster_needs_answer = cluster_needs_answer


def _cluster_is_optional_tier(protocol: SymptomProtocol, cluster: QuestionCluster) -> bool:
    """Ngân sách chỉ được cắt cụm mà TOÀN BỘ field bên trong là tier O/H (làm giàu/handoff) - cụm có
    bất kỳ field M0/M1/C nào vẫn phải hỏi dù đã vượt ngân sách danh nghĩa (bài học rút ra khi chạy
    fever qua LLM thật: cắt nhầm field bắt buộc khiến hệ thống không bao giờ đủ dữ kiện kết luận)."""
    return all(protocol.fields_by_key[key].tier in ("O", "H") for key in cluster.fields)


def cluster_is_skipped(protocol: SymptomProtocol, stage: str, cluster: QuestionCluster, answers: dict[str, object]) -> bool:
    """Cụm này có bị bỏ qua theo điều kiện tuổi/giới/nhánh không. Public vì `screening.py` phải tôn
    trọng đúng các điều kiện đó: một nhóm chỉ còn cụm bị skip (vd `G3B-COG` = Q3-02, tự loại khi dưới
    16 tuổi) phải được coi là ĐÃ giải quyết, nếu không câu sàng lọc sẽ liệt kê dấu hiệu không áp dụng
    được cho người bệnh này."""
    emergency_scan_stage, early_visit_scan_stage = protocol.gate_stages
    if stage == early_visit_scan_stage and protocol.provisional_emergency_signal(answers):
        return True
    return protocol.skip_rule(cluster, answers)


_cluster_is_skipped = cluster_is_skipped


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
        if not _cluster_needs_answer(protocol, cluster, answers):
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


@dataclass(frozen=True, slots=True)
class Advance:
    """Kết quả duyệt tới cụm kế tiếp, có thể đã BĂNG QUA ranh giới stage."""

    cluster: QuestionCluster | None
    stage: str
    """Stage của `cluster`, hoặc stage cuối cùng đã tới nếu dừng."""
    stop_reason: StopReason | None
    """Chỉ khác `None` khi `cluster is None` - lý do phiên nên kết thúc."""


def advance(
    protocol: SymptomProtocol,
    stage: str,
    answers: dict[str, object],
    *,
    asked_ids: frozenset[str] = frozenset(),
    asked_count: int | None = None,
    known_triage_level: str | None = None,
) -> Advance:
    """Cụm kế tiếp THẬT SỰ sẽ được hỏi, băng qua stage nếu stage hiện tại đã hết cụm.

    `next_cluster` một mình KHÔNG đủ để sinh câu hỏi: nó chỉ nhìn trong MỘT stage, nên khi cụm cuối
    của stage vừa được trả lời nó trả `None` - và người bệnh nhận về một tin nhắn RỖNG trong khi phiên
    vẫn đang chờ họ trả lời cụm đầu của stage sau (lỗi thật, đo được ở 5/40 lượt khi chạy LLM thật:
    lượt 1, 3, 8, 16, 22 của ca lành tính đều trả câu hỏi rỗng). Hàm này là chỗ DUY NHẤT biết cách đi
    tiếp, để `intake_agent` (sinh câu hỏi) và `session` (cập nhật trạng thái) không thể lệch nhau về
    việc "cụm kế tiếp là cụm nào".

    Hàm THUẦN - không side-effect, không log."""
    current_stage = stage
    count = len(asked_ids) if asked_count is None else asked_count
    while True:
        stop = should_stop(
            protocol, current_stage, answers, asked_count=count,
            known_triage_level=known_triage_level,
        )
        if stop is not None:
            return Advance(None, current_stage, stop)
        cluster = next_cluster(protocol, current_stage, answers, asked_ids=asked_ids)
        if cluster is not None:
            return Advance(cluster, current_stage, None)
        following = next_stage(protocol, current_stage)
        if following is None:
            stop = "SUFFICIENT_EVIDENCE" if protocol.self_care_checklist_satisfied(answers) else "BUDGET_EXHAUSTED"
            return Advance(None, current_stage, stop)
        current_stage = following


def _gate_stages_cleared(protocol: SymptomProtocol, stage: str, answers: dict[str, object]) -> bool:
    """Đã quét xong CẢ HAI gate stage chưa (3A emergency-scan + 3B early-visit-scan với fever).

    Đây là ràng buộc lâm sàng CỨNG, không phải tối ưu: CS §3.3A gọi Stage 3A là "minimum scan" bắt
    buộc cho MỌI route, không route nào được rút gọn. Mọi đường dừng sớm phải đi qua đây trước."""
    last_gate = protocol.gate_stages[-1]
    try:
        gate_index = protocol.stage_order.index(last_gate)
        stage_index = protocol.stage_order.index(stage)
    except ValueError:
        return False
    if stage_index > gate_index:
        return True
    # Đang đứng ở đúng gate cuối: chỉ tính là xong khi không còn cụm nào của nó để hỏi.
    return stage_index == gate_index and next_cluster(protocol, stage, answers) is None


def _has_sufficient_evidence(
    protocol: SymptomProtocol, stage: str, answers: dict[str, object],
) -> bool:
    """Đã đủ căn cứ kết luận, được phép dừng dù chưa đi hết bộ câu hỏi.

    Trước đây điều kiện này chỉ được xét ở stage CUỐI CÙNG. Với fever, `stage_order[-1]` là "5" nên
    engine buộc đi hết Stage 4 (10 cụm) + Stage 5 (8 cụm) dù checklist tự chăm sóc đã xanh từ sau
    Stage 3B - đo được ~24 lượt cho một ca lành tính, trong khi CS §6.5 cấp ngân sách 12-16 cụm và CS
    Part 4.2 nói thẳng: "Một khi checklist §5.4 đã toàn bộ xanh và không còn unknown ảnh hưởng rule ->
    dừng ngay, không cố hỏi thêm cho 'chắc'".

    Ba điều kiện, thiếu một là không được dừng:
    1. đã quét xong cả hai gate stage (ràng buộc cứng của tài liệu);
    2. mọi field M0/M1 đã có căn cứ - chặn việc kết luận "tự theo dõi" cho người mang thai/suy giảm
       miễn dịch mà chưa bao giờ hỏi tới (xem `mandatory_fields_covered`);
    3. checklist tự chăm sóc của protocol xanh.

    Nhánh cũ ở stage cuối được GIỮ NGUYÊN bên dưới: nó là đường dừng cho ca đã đi hết bộ câu hỏi."""
    if stage == protocol.stage_order[-1] and next_cluster(protocol, stage, answers) is None:
        return protocol.self_care_checklist_satisfied(answers)
    return (
        _gate_stages_cleared(protocol, stage, answers)
        and mandatory_fields_covered(protocol, answers)
        and protocol.self_care_checklist_satisfied(answers)
    )


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

    if _has_sufficient_evidence(protocol, stage, answers):
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
