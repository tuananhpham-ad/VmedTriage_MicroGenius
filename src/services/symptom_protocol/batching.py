"""Gộp 2-3 cụm câu hỏi LIỀN KỀ vào một tin nhắn, cho phần hỏi thường (không phải sàng lọc phủ định).

Vấn đề: engine hỏi đúng MỘT cụm mỗi lượt, nên Stage 0/1/2 của fever (10 cụm) tốn 10 lượt chỉ để lấy
tuổi, giới, có sốt không, sốt mấy ngày. Người bệnh cảm nhận đây là bị tra hỏi từng câu một, và đó là
phản hồi trực tiếp từ người dùng thật.

**Khác `screening.py` chỗ nào - đừng nhầm hai cơ chế:**

| | `screening.py` (sàng lọc gộp) | module này (hỏi gộp) |
|---|---|---|
| Loại câu | đọc danh sách dấu hiệu để PHỦ ĐỊNH hàng loạt | hỏi thẳng vài thông tin khác nhau |
| Văn bản | ghép TĨNH, không qua LLM (ràng buộc an toàn) | qua LLM diễn đạt lại như câu hỏi thường |
| Đóng cụm | qua verdict theo nhóm + `closed_cluster_ids` | KHÔNG có gì đặc biệt - cụm đóng theo DỮ LIỆU |
| Phạm vi | chỉ ở `gate_stages` | chỉ NGOÀI `gate_stages` |

Hai cơ chế không bao giờ chạy cùng lượt: `next_batch` tự loại mọi stage nằm trong `gate_stages`.

**Vì sao không cần cơ chế "đóng nhiều cụm" như screening:** cụm tổng hợp chỉ tồn tại đúng một lượt để
sinh câu hỏi và làm schema trích xuất. Sau đó `next_cluster` bỏ qua cụm thành phần theo `answers` -
`cluster_needs_answer` đã là nguồn sự thật cho việc đó. Cụm nào người bệnh trả lời rồi thì tự biến
mất; cụm nào họ bỏ qua thì được hỏi lại đúng một mình nó. Thêm một tập "đã đóng" song song ở đây chỉ
tạo cơ hội cho nó lệch khỏi dữ liệu - đúng lớp bug C3.
"""

from __future__ import annotations

from src.services.symptom_protocol import stage_machine
from src.services.symptom_protocol.models import QuestionCluster
from src.services.symptom_protocol.protocol import SymptomProtocol, clusters_for_stage

BATCH_ID_PREFIX = "BATCH-"
"""Mã cụm gộp là TỔNG HỢP (`BATCH-1-2`), không phải mã trong tài liệu lâm sàng. Cùng quy ước với
`screening.PROBE_ID_PREFIX`: nó không nằm trong `protocol.clusters` nên `next_cluster` không bao giờ
tự chọn phải nó."""

MAX_CLUSTERS_PER_BATCH = 3
"""Trần số cụm gộp trong MỘT tin nhắn. 2-3 là mức người dùng chốt: đủ để hội thoại bớt lắt nhắt,
chưa tới mức thành một biểu mẫu bắt điền. Trên 3 ý thì người bệnh bắt đầu chỉ trả lời ý cuối - và
mỗi ý rơi mất là một lượt hỏi lại, tức là gộp nhiều hơn lại hoá chậm hơn."""


def is_batch(cluster: QuestionCluster | None) -> bool:
    return cluster is not None and cluster.id.startswith(BATCH_ID_PREFIX)


def _components_of(batch_id: str) -> tuple[str, ...]:
    """Mã cụm thành phần nằm ngay trong mã gói (`BATCH-0-Q0-01+Q0-02`).

    Mã tự mô tả thay vì lưu thêm một trường trong `Session`: cụm gộp chỉ sống đúng một lượt, còn
    `Session` thì được ghi/đọc ở 5 chỗ. Một trường nữa để đồng bộ là một chỗ nữa để lệch - mà lệch ở
    đây nghĩa là hội thoại quay vòng (xem `already_batched`). Stage không chứa dấu `-` nên `partition`
    tách được chắc chắn."""
    _stage, _, joined = batch_id[len(BATCH_ID_PREFIX) :].partition("-")
    return tuple(part for part in joined.split("+") if part)


def already_batched(asked_ids: frozenset[str]) -> frozenset[str]:
    """Cụm ĐÃ từng được đọc lên trong một gói trước đó.

    Đây là chốt chống vòng lặp, không phải tối ưu. Sổ sách retry/hoàn tất của `session` ghi theo mã
    cụm VỪA HỎI - tức mã gói - còn `next_cluster` lại duyệt theo mã cụm THẬT. Không có hàm này thì:
    gói không thu được gì -> cụm thành phần vẫn trống -> `next_cluster` trả lại đúng cụm đầu -> gói y
    hệt được dựng lại -> lặp vô hạn (đo được: hội thoại không kết thúc sau 60 lượt). Đã đọc lên rồi
    mà người bệnh không trả lời thì đường lùi đúng là hỏi RIÊNG từng cụm."""
    return frozenset(
        cluster_id
        for asked in asked_ids
        if asked.startswith(BATCH_ID_PREFIX)
        for cluster_id in _components_of(asked)
    )


def _screening_bound_cluster_ids(protocol: SymptomProtocol) -> frozenset[str]:
    """Cụm KHÔNG được gộp kiểu hỏi thường vì nó phục vụ cơ chế sàng lọc.

    Hai nhóm, và nhóm thứ hai là bài học đo được:

    1. Cụm nằm trong một `ScreeningGroup`. Chúng được viết để phủ định hàng loạt qua `screening.py`;
       kéo vào câu hỏi thường là tiêu mất cơ hội đóng cả nhóm bằng một câu "không có gì cả".
    2. Cụm CHIA SẺ FIELD với nhóm ở (1) - điển hình là `Q4-00`, câu hỏi rủi ro gộp của Stage 4. Nó
       không thuộc nhóm nào nên luật (1) cho qua, nhưng field của nó là enum/danh sách
       (`chronic_conditions`, `indwelling_device`) mà một câu trả lời gộp hiếm khi điền đủ. Đo được:
       gói `Q4-00+Q4-06+Q4-07` phát ra rồi cả ba cụm vẫn phải hỏi lại từng cái - gộp thành ra TỐN
       thêm một lượt thay vì tiết kiệm. Cụm nào đã có đường rút ngắn riêng thì để nguyên đường đó."""
    in_group = {
        cluster_id for group in protocol.screening_groups for cluster_id in group.cluster_ids
    }
    group_fields = {
        key
        for cluster in protocol.clusters
        if cluster.id in in_group
        for key in cluster.fields
    }
    overlapping = {
        cluster.id
        for cluster in protocol.clusters
        if cluster.id not in in_group and group_fields.intersection(cluster.fields)
    }
    return frozenset(in_group | overlapping)


def _is_narrative_stage(protocol: SymptomProtocol, stage: str) -> bool:
    """Stage này có nằm TRƯỚC các gate stage không - tức phần người bệnh đang kể chuyện nền.

    Gộp chỉ có lãi ở đây, và đây là số đo chứ không phải cảm tính. Gói chỉ tiết kiệm được lượt khi
    người bệnh trả lời ĐỦ mọi ý trong đó; trả lời thiếu một ý thì cụm tương ứng vẫn phải hỏi lại và
    gói hoá ra tốn THÊM một lượt. Phần trước gate là các câu kể được liền mạch trong một hơi ("bé 3
    tuổi, gái, sốt 2 hôm nay, uống hạ sốt rồi") nên tỉ lệ trả lời đủ cao. Stage sau gate là bảng kiểm
    làm giàu, mỗi cụm hỏi một con số/danh sách riêng (đi vùng dịch nào, khoảng cách tới cơ sở y tế,
    đang dùng thuốc gì) - đo trên ca H1 thì gộp ở đó làm hội thoại DÀI thêm một lượt mỗi gói.

    Phần sau gate đã có hai đường rút ngắn riêng và cả hai đều hiệu quả hơn gộp: câu sàng lọc theo
    nhóm (`screening.py`) và luật dừng sớm + ngân sách (`stage_machine.should_stop`)."""
    order = protocol.stage_order
    try:
        return order.index(stage) < order.index(protocol.gate_stages[0])
    except ValueError:
        return False


def next_batch(
    protocol: SymptomProtocol,
    stage: str,
    answers: dict[str, object],
    first: QuestionCluster | None,
    *,
    asked_ids: frozenset[str] = frozenset(),
    max_clusters: int = MAX_CLUSTERS_PER_BATCH,
) -> tuple[QuestionCluster, ...]:
    """Các cụm sẽ được hỏi CHUNG một tin nhắn, `first` luôn đứng đầu. Rỗng = hỏi lẻ như cũ.

    Điều kiện gộp, đều là chặn deterministic bằng code:

    1. `stage` nằm TRƯỚC các gate stage (xem `_is_narrative_stage`). Riêng việc loại chính hai gate
       stage là ràng buộc an toàn: CS §3.3A bắt xác nhận riêng từng dấu hiệu nguy kịch theo script
       chuẩn, và `screening.py` đã lo phần rút ngắn cho chúng theo cách an toàn hơn.
    2. `first` không phải cụm phủ định-cả-cụm (`batch_negation`) và không thuộc `ScreeningGroup` nào.
    3. Cụm ghép thêm phải CÙNG stage, chưa hỏi, không bị `skip_rule` loại, còn field cần trả lời, và
       cũng thoả điều kiện 2.
    4. Mọi cụm phải có `script_hint` - không có kịch bản hỏi thì không có gì để ghép vào tin nhắn.
    5. Cụm CHƯA từng nằm trong một gói nào trước đó (`already_batched`) - đọc lại nguyên gói khi
       người bệnh đã bỏ qua nó một lần là vòng lặp, không phải kiên trì.
    """
    if first is None or max_clusters < 2 or not _is_narrative_stage(protocol, stage):
        return ()
    grouped = _screening_bound_cluster_ids(protocol)
    heard_before = already_batched(asked_ids)
    if first.id in heard_before or not _is_batchable(protocol, first, grouped):
        return ()

    picked = [first]
    for candidate in clusters_for_stage(protocol, stage):
        if len(picked) >= max_clusters:
            break
        if candidate.id == first.id or candidate.id in asked_ids or candidate.id in heard_before:
            continue
        if not _is_batchable(protocol, candidate, grouped):
            continue
        if stage_machine.cluster_is_skipped(protocol, stage, candidate, answers):
            continue
        if not stage_machine.cluster_needs_answer(protocol, candidate, answers):
            continue
        picked.append(candidate)

    return tuple(picked) if len(picked) >= 2 else ()


def _is_batchable(
    protocol: SymptomProtocol, cluster: QuestionCluster, grouped: frozenset[str],
) -> bool:
    return bool(cluster.script_hint) and not cluster.batch_negation and cluster.id not in grouped


BATCH_INTRO = "Mình hỏi nhanh vài ý"


def batch_question(clusters: tuple[QuestionCluster, ...]) -> str:
    """Ý cần hỏi, đánh số để LLM thấy rõ có mấy ý phải hỏi đủ.

    Vai trò CHÍNH là đầu vào cho bước diễn đạt lại - prompt yêu cầu LLM gộp thành câu liền mạch chứ
    không chép lại danh sách. Nhưng nó còn là phương án dự phòng khi LLM lỗi, và là văn bản dùng
    thẳng cho câu mở phiên (`session.start_session` không gọi LLM), nên phải đọc lọt tai với người
    bệnh chứ không được là một mẩu prompt lộ ra ngoài."""
    numbered = "; ".join(
        f"({index}) {cluster.script_hint}" for index, cluster in enumerate(clusters, start=1)
    )
    return f"{BATCH_INTRO}: {numbered}"


def batch_cluster(stage: str, clusters: tuple[QuestionCluster, ...]) -> QuestionCluster:
    """Gói các cụm thành MỘT `QuestionCluster` tổng hợp, sống đúng một lượt.

    Mượn đúng kiểu cụm thay vì thêm một loại "lượt" mới, cùng lý do như `screening.probe_cluster`:
    toàn bộ vòng đời phiên (`current_cluster`, `_record_cluster_outcome`, log theo `cluster_id`, sinh
    câu hỏi, schema trích xuất) đã xoay quanh khái niệm cụm. Thêm một loại lượt song song nghĩa là
    mỗi chỗ đó mọc thêm một nhánh `if`."""
    fields: list[str] = []
    for cluster in clusters:
        fields.extend(key for key in cluster.fields if key not in fields)
    return QuestionCluster(
        id=f"{BATCH_ID_PREFIX}{stage}-{'+'.join(cluster.id for cluster in clusters)}",
        stage=stage,
        fields=tuple(fields),
        batch_negation=False,  # gộp ở đây là hỏi thẳng, không phải phủ định hàng loạt
        script_hint=batch_question(clusters),
    )
