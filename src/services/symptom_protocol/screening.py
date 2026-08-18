"""Sàng lọc THEO NHÓM CƠ QUAN: một câu hỏi gộp đóng được nhiều cụm cùng lúc.

Vấn đề: agent đi tuần tự từng cụm, nên ca lành tính - nhóm đông nhất, cũng là nhóm ta muốn kết thúc
sớm nhất - phải trả lời đủ 11 cụm Stage 3A + 5 cụm Stage 3B chỉ để tất cả cùng ra âm tính (đo được
36 lượt khi chạy LLM thật). CS §3.3A cho phép kỹ thuật phủ định gộp và CS §8.4 O1 minh hoạ một câu
phủ định trải NHIỀU cụm; code trước đó mới chỉ áp dụng trong phạm vi MỘT cụm
(`QuestionCluster.batch_negation`). Module này nâng phạm vi lên NHÓM.

Module THUẦN: không gọi LLM, không dựng prompt, không ghi log. Prompt/verdict do `intake_agent` lo
(nó sở hữu mọi prompt), việc kiểm bằng chứng được TRUYỀN VÀO dạng hàm (`evidence_ok`) chứ không tự
viết lại - hai định nghĩa "bằng chứng hợp lệ" lệch nhau là đúng cách mở lại lỗ hổng C1. Nhờ vậy
`screening` không import ngược `intake_agent`, và `apply_verdicts` test được không cần LLM.

**Hai lớp đóng, cố ý làm cả hai** (chỉ một lớp là không đủ):

1. *Ghi giá trị âm tính vào `answers`* - `false` cho field tri-state, `negative_values[key]` cho field
   enum. Cần cho RULE và cho checklist tự chăm sóc: `self_care_checklist_satisfied` đòi
   `urine_output == "normal"`, không phải "chưa biết".
2. *Đóng theo MÃ CỤM* (`closed_cluster_ids`) - cần vì nhiều cụm có field mô tả chi tiết chỉ có nghĩa
   khi DƯƠNG tính (`rash_type`, `abdominal_pain_location`) mà ta cố ý không bịa giá trị âm tính. Chỉ
   ghi giá trị thôi thì `cluster_needs_answer` vẫn trả `True` và cụm vẫn bị hỏi lại - đúng cơ chế mà
   `asked_ids` đang dùng cho phủ định gộp trong phạm vi một cụm.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from src.services.symptom_protocol import stage_machine
from src.services.symptom_protocol.models import QuestionCluster, ScreeningGroup
from src.services.symptom_protocol.protocol import SymptomProtocol, clusters_by_id

Verdict = str  # "negative" | "positive" | "unknown"

_VERDICTS: frozenset[str] = frozenset({"negative", "positive", "unknown"})
_DEFAULT_VERDICT = "unknown"

PROBE_ID_PREFIX = "SCREEN-"
"""Mã cụm sàng lọc là TỔNG HỢP (`SCREEN-3A`), không phải mã trong tài liệu lâm sàng - tiền tố này là
cách phân biệt nó với mọi `Q<x>-<y>` có thật. Nó không nằm trong `protocol.clusters` nên
`next_cluster` không bao giờ tự chọn phải nó."""

MIN_GROUPS_PER_PROBE = 2
"""Dưới 2 nhóm thì hỏi gộp không tiết kiệm được lượt nào, mà lại đánh đổi: câu hỏi dài hơn và phải
qua đường verdict thay vì hỏi thẳng đúng script chuẩn của cụm."""

MAX_GROUPS_PER_PROBE = 3
"""Trần TRÊN, đối trọng của `MIN_GROUPS_PER_PROBE`. Cả cơ chế này dựa trên tiền đề "nhóm chỉ được
đóng khi người bệnh đã THỰC SỰ nhìn thấy danh sách dấu hiệu của nó" - tiền đề đó yếu dần theo độ dài
câu hỏi. Stage 3A của fever có 5 nhóm: đọc liền 5 dòng dấu hiệu rồi nhận về "không có gì cả" là đóng
5 nhóm bằng một câu trả lời mà người bệnh nhiều khả năng đã đọc lướt.

Cắt ở 3 KHÔNG làm mất nhóm nào: phần dư rơi vào vòng sàng lọc kế tiếp (`max_screening_rounds`), và
điều kiện "vòng sau phải là tập con thực sự của vòng trước" trong `next_probe` vẫn giữ nguyên vì tập
NHÓM CHƯA GIẢI QUYẾT co lại sau mỗi vòng - không phải tập nhóm vừa được hỏi."""


@dataclass(frozen=True, slots=True)
class ScreeningOutcome:
    """Kết quả áp verdict cho MỘT lượt sàng lọc. Thuần dữ liệu - caller quyết định làm gì với nó."""

    negatives: dict[str, object]
    """Giá trị âm tính ghi thêm vào `answers`. CHỈ gồm field đang `unknown` - một nhóm bị phủ định
    KHÔNG được ghi đè điều người bệnh đã khẳng định trước đó."""

    closed_cluster_ids: frozenset[str]
    negative_group_ids: tuple[str, ...]
    positive_group_ids: tuple[str, ...]
    rejected_group_ids: tuple[str, ...]
    """Nhóm model khai "âm tính" nhưng KHÔNG trích được câu phủ định nào trong tin nhắn ⇒ verdict bị
    bỏ, nhóm vẫn phải hỏi. Ghi lại để log nói rõ vì sao lượt sàng lọc không rút ngắn được gì."""

    @property
    def changed(self) -> bool:
        return bool(self.negatives or self.closed_cluster_ids or self.positive_group_ids)


def groups_for_stage(protocol: SymptomProtocol, stage: str) -> tuple[ScreeningGroup, ...]:
    return tuple(group for group in protocol.screening_groups if group.stage == stage)


def clusters_of(protocol: SymptomProtocol, group: ScreeningGroup) -> tuple[QuestionCluster, ...]:
    """Cụm thật của nhóm. Mã lạ (khai sai trong protocol) bị BỎ QUA im lặng ở đây và bị bắt bằng test
    `test_fever_screening_groups_reference_real_clusters` - fail lúc dựng protocol sẽ làm sập cả
    service vì một lỗi chính tả trong data."""
    by_id = clusters_by_id(protocol)
    return tuple(by_id[cluster_id] for cluster_id in group.cluster_ids if cluster_id in by_id)


def _cluster_is_open(
    protocol: SymptomProtocol,
    stage: str,
    cluster: QuestionCluster,
    answers: dict[str, object],
    closed_ids: frozenset[str],
) -> bool:
    if cluster.id in closed_ids:
        return False
    if stage_machine.cluster_is_skipped(protocol, stage, cluster, answers):
        return False
    return stage_machine.cluster_needs_answer(protocol, cluster, answers)


def unresolved_groups(
    protocol: SymptomProtocol,
    stage: str,
    answers: dict[str, object],
    *,
    closed_ids: frozenset[str] = frozenset(),
) -> tuple[ScreeningGroup, ...]:
    """Nhóm còn ít nhất một cụm THỰC SỰ sẽ được hỏi.

    Dùng đúng `cluster_needs_answer`/`cluster_is_skipped` của `stage_machine` chứ không tự định nghĩa
    lại: nếu hai bên lệch nhau, câu sàng lọc sẽ liệt kê dấu hiệu của một nhóm mà `next_cluster` không
    còn định hỏi (người bệnh trả lời thừa), hoặc bỏ sót nhóm sắp bị hỏi (không rút ngắn được gì)."""
    return tuple(
        group
        for group in groups_for_stage(protocol, stage)
        if any(
            _cluster_is_open(protocol, stage, cluster, answers, closed_ids)
            for cluster in clusters_of(protocol, group)
        )
    )


def next_probe(
    protocol: SymptomProtocol,
    stage: str,
    answers: dict[str, object],
    candidate: QuestionCluster | None,
    *,
    closed_ids: frozenset[str] = frozenset(),
    history: tuple[frozenset[str], ...] = (),
) -> tuple[ScreeningGroup, ...]:
    """Lượt tới có nên phát câu sàng lọc gộp thay vì câu hỏi của `candidate` không.

    Bốn điều kiện, đều là chặn deterministic bằng code:

    1. `candidate` phải THUỘC một nhóm. Cụm đứng ngoài mọi nhóm (fever: Q3-01 tri giác, Q3-03 co
       giật - CS §3.3A cấm suy diễn 2 cụm này từ phủ định gộp) vẫn được hỏi riêng đúng script, không
       cần luật đặc biệt nào: chúng đứng TRƯỚC trong thứ tự tài liệu nên `next_cluster` trả chúng ra
       trước, và điều kiện này tự loại lượt sàng lọc.
    2. Ít nhất `MIN_GROUPS_PER_PROBE` nhóm chưa giải quyết - dưới ngưỡng thì hỏi thẳng cụm rẻ hơn.
    3. Chưa hết hạn mức vòng sàng lọc của stage (`history` là các tập nhóm đã sàng lọc ở stage này).
    4. Vòng sau phải ĐỌC LÊN ít nhất một nhóm CHƯA từng đọc. Đây là điều đo được khi chạy thử chứ
       không phải suy đoán: nếu vòng đầu không thu được gì (người bệnh trả lời "em không hiểu ý câu
       hỏi"), tập nhóm chưa giải quyết y nguyên, và vòng hai sẽ đọc lại NGUYÊN VĂN cùng một danh sách
       dài - cách nhanh nhất để người bệnh bỏ cuộc.

    Điều kiện 4 trước đây là "tập nhóm chưa giải quyết phải là con THỰC SỰ của vòng trước". Nó đúng
    khi một vòng đọc HẾT các nhóm còn lại, nhưng `MAX_GROUPS_PER_PROBE` đã bỏ tiền đề đó: vòng đầu
    chỉ đọc 3/5 nhóm, nên 2 nhóm còn dư KHÔNG phải tập con của những nhóm đã đọc và vòng hai bị chặn
    oan - đúng lúc nó cần chạy nhất. Diễn đạt "phải có nhóm chưa đọc" giữ nguyên ý định gốc (không
    đọc lại đúng danh sách vừa đọc) mà không dựa vào tiền đề đã mất.
    """
    if candidate is None or len(history) >= protocol.max_screening_rounds:
        return ()
    groups = unresolved_groups(protocol, stage, answers, closed_ids=closed_ids)
    if len(groups) < MIN_GROUPS_PER_PROBE:
        return ()
    if not any(candidate.id in group.cluster_ids for group in groups):
        return ()
    selected = _select_groups(groups, history)
    if len(selected) < MIN_GROUPS_PER_PROBE:
        return ()
    already_read = frozenset().union(*history) if history else frozenset()
    if all(group.id in already_read for group in selected):
        return ()
    return selected


def _select_groups(
    groups: tuple[ScreeningGroup, ...], history: tuple[frozenset[str], ...],
) -> tuple[ScreeningGroup, ...]:
    """Chọn tối đa `MAX_GROUPS_PER_PROBE` nhóm cho MỘT câu, nhóm CHƯA đọc lên trước.

    Thứ tự này là thứ làm điều kiện 4 của `next_probe` có ý nghĩa: cắt danh sách mà vẫn lấy từ đầu
    thì vòng hai đọc lại đúng những dòng vòng một vừa đọc, còn các nhóm chưa ai nghe thì không bao
    giờ tới lượt."""
    already_read = frozenset().union(*history) if history else frozenset()
    fresh = [group for group in groups if group.id not in already_read]
    reread = [group for group in groups if group.id in already_read]
    return tuple((fresh + reread)[:MAX_GROUPS_PER_PROBE])


def probe_fields(protocol: SymptomProtocol, groups: tuple[ScreeningGroup, ...]) -> tuple[str, ...]:
    """Field đưa vào schema trích xuất của lượt sàng lọc - hợp của mọi cụm trong các nhóm được hỏi.

    Người bệnh trả lời câu gộp vẫn hay nói thẳng một chi tiết ("có, bé không tiểu từ sáng"); không có
    các field này trong schema thì chi tiết đó rơi mất và nhóm chỉ còn cách hỏi lại từ đầu."""
    seen: set[str] = set()
    ordered: list[str] = []
    for group in groups:
        for cluster in clusters_of(protocol, group):
            for key in cluster.fields:
                if key not in seen and key in protocol.fields_by_key:
                    seen.add(key)
                    ordered.append(key)
    return tuple(ordered)


PROBE_INTRO = "Mình hỏi nhanh một loạt dấu hiệu quan trọng để loại trừ, bạn xem có dấu hiệu nào không nhé:"
PROBE_OUTRO = 'Nếu không có dấu hiệu nào trong số trên, bạn chỉ cần trả lời "không có dấu hiệu nào" là được ạ.'


def probe_question(groups: tuple[ScreeningGroup, ...]) -> str:
    """Câu sàng lọc, ghép TĨNH từ `probe_hint` - KHÔNG qua LLM diễn đạt lại.

    Đây là ràng buộc an toàn, không phải tiết kiệm một call: cả cơ chế này dựa trên tiền đề "nhóm chỉ
    được đóng khi người bệnh đã thực sự nhìn thấy danh sách dấu hiệu của nó". LLM diễn đạt lại một
    danh sách 5 nhóm rất dễ gộp/lược vài ý cho gọn, và khi đó một câu "không có gì cả" sẽ đóng cả
    những dấu hiệu chưa bao giờ được đọc lên - đúng lỗi C1 ở quy mô lớn nhất."""
    lines = [f"{index}) {group.probe_hint}" for index, group in enumerate(groups, start=1)]
    return "\n".join([PROBE_INTRO, *lines, PROBE_OUTRO])


def probe_cluster(protocol: SymptomProtocol, stage: str, groups: tuple[ScreeningGroup, ...]) -> QuestionCluster:
    """Gói lượt sàng lọc thành một `QuestionCluster` TỔNG HỢP.

    Vì sao mượn đúng kiểu cụm thay vì thêm một loại "lượt" mới: toàn bộ vòng đời phiên
    (`session.current_cluster`, `_record_cluster_outcome`, log theo `cluster_id`, sinh câu hỏi) đã
    xoay quanh khái niệm cụm. Thêm một loại lượt song song nghĩa là mỗi chỗ đó phải mọc thêm một
    nhánh `if`. Cụm này KHÔNG nằm trong `protocol.clusters` nên `next_cluster` không bao giờ tự chọn
    phải nó - nó chỉ tồn tại đúng một lượt, do `next_probe` dựng ra."""
    return QuestionCluster(
        id=f"{PROBE_ID_PREFIX}{stage}",
        stage=stage,
        fields=probe_fields(protocol, groups),
        batch_negation=False,  # phủ định gộp ở đây đi qua verdict theo NHÓM, không qua cờ cả-cụm
        script_hint=probe_question(groups),
    )


def is_probe(cluster: QuestionCluster | None) -> bool:
    return cluster is not None and cluster.id.startswith(PROBE_ID_PREFIX)


def _verdict_and_evidence(raw: object) -> tuple[Verdict, object]:
    if isinstance(raw, dict):
        verdict = str(raw.get("verdict") or "").strip().casefold()
        return (verdict if verdict in _VERDICTS else _DEFAULT_VERDICT), raw.get("evidence")
    verdict = str(raw or "").strip().casefold()
    # Dạng phẳng `"G3A-RESP": "negative"` không kèm trích dẫn ⇒ không bao giờ đủ điều kiện đóng nhóm
    # (`evidence_ok(None)` luôn False). Vẫn nhận `positive` vì chiều đó không đóng gì cả.
    return (verdict if verdict in _VERDICTS else _DEFAULT_VERDICT), None


def parse_verdicts(parsed: dict) -> dict[str, tuple[Verdict, object]]:
    groups = parsed.get("groups")
    if not isinstance(groups, dict):
        return {}
    return {str(key): _verdict_and_evidence(value) for key, value in groups.items()}


def apply_verdicts(
    protocol: SymptomProtocol,
    stage: str,
    groups: tuple[ScreeningGroup, ...],
    parsed: dict,
    answers: dict[str, object],
    *,
    evidence_ok: Callable[[object], bool],
) -> ScreeningOutcome:
    """Áp verdict của model lên hồ sơ. THUẦN - không LLM, không side-effect.

    | Verdict | Hành động |
    |---|---|
    | `negative` + trích dẫn verify được | Ghi giá trị âm tính + đóng mọi cụm trong nhóm |
    | `negative` + trích dẫn hỏng/thiếu | BỎ verdict - nhóm vẫn phải hỏi (`rejected_group_ids`) |
    | `positive` | Không ghi gì. Các cụm giữ `unknown` ⇒ `next_cluster` hỏi từng cụm đúng script chuẩn |
    | `unknown` | Không ghi gì. Vòng sàng lọc sau gộp lại hỏi phần còn dư |

    `positive` cố ý KHÔNG ghi `"true"` cho field nào: người bệnh mới xác nhận "nhóm này có vấn đề",
    chưa nói dấu hiệu cụ thể nào trong nhóm. Ghi bừa `"true"` là dựng một dấu hiệu đỏ không ai khai -
    và vì `true` là chiều LÀM NẶNG ca, nó sẽ chốt cấp cứu trên dữ liệu bịa."""
    verdicts = parse_verdicts(parsed)

    negatives: dict[str, object] = {}
    closed: set[str] = set()
    negative_ids: list[str] = []
    positive_ids: list[str] = []
    rejected_ids: list[str] = []

    for group in groups:
        verdict, evidence = verdicts.get(group.id, (_DEFAULT_VERDICT, None))
        if verdict == "positive":
            positive_ids.append(group.id)
            continue
        if verdict != "negative":
            continue
        if not evidence_ok(evidence):
            rejected_ids.append(group.id)
            continue

        negative_ids.append(group.id)
        for cluster in clusters_of(protocol, group):
            if stage_machine.cluster_is_skipped(protocol, stage, cluster, answers):
                continue
            closed.add(cluster.id)
            for key in cluster.fields:
                if stage_machine.is_filled(answers.get(key)) or key in negatives:
                    continue
                spec = protocol.fields_by_key.get(key)
                if spec is None:
                    continue
                if spec.tri_state:
                    negatives[key] = "false"
                elif key in group.negative_values:
                    negatives[key] = group.negative_values[key]

    return ScreeningOutcome(
        negatives=negatives,
        closed_cluster_ids=frozenset(closed),
        negative_group_ids=tuple(negative_ids),
        positive_group_ids=tuple(positive_ids),
        rejected_group_ids=tuple(rejected_ids),
    )
