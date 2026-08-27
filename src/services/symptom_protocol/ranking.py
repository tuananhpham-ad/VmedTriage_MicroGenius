"""Xếp hạng cụm câu hỏi - THUẦN code, thay cho first-fit thuần vị trí.

Vấn đề đang giải: `next_cluster` cũ duyệt `clusters_for_stage` theo thứ tự khai báo và trả về cụm
đầu tiên còn thiếu. Người bệnh vừa kể về khó thở mà cụm khó thở đứng thứ 7 thì vẫn phải trả lời 6
cụm khác trước - đó là nguồn chính của cảm giác "nó không nghe mình nói".

**Model KHÔNG tham gia.** Mọi thành phần điểm tính được từ `answers` + `asked_ids` + field vừa thu
được ở lượt trước, nên cùng input luôn cho cùng output, transcript lặp lại được, và test bằng fake
LLM vẫn kiểm được toàn bộ hành vi. Đây là ranh giới của §8: nới THỨ TỰ hỏi, không nới quyền quyết
định.

Bốn thành phần, trọng số là HẰNG SỐ trong code (đổi trọng số phải chạy lại eval):

| Thành phần | Ý nghĩa |
| --- | --- |
| `safety`    | Cụm chứa field an toàn ⇒ điểm áp đảo, không bao giờ bị hoãn (§8.2 bất biến 2) |
| `overdue`   | Cụm đã chạm trần hoãn ⇒ chắc chắn thắng lượt này (§8.5 quy tắc 1) |
| `relevance` | Người bệnh VỪA nhắc tới field của cụm này ở lượt trước (§8.4 follow-the-user) |
| `yield`     | Cụm còn lấp được field bắt buộc M0/M1 ⇒ đứng trước cụm thuần tuỳ chọn |
| `debt`      | Số lượt đã bị hoãn, cộng dần theo thời gian chờ |

**Hoà điểm giữ nguyên thứ tự khai báo**, nên hành vi first-fit cũ là TRƯỜNG HỢP ĐẶC BIỆT của hành vi
mới: không có tín hiệu nào (lượt đầu, chưa ai nhắc gì, chưa hoãn gì) thì thứ tự y hệt bản cũ trong
cùng một nhóm `yield`.

`yield` cố ý là NHỊ PHÂN chứ không đếm số field thiếu. Đếm thì gần như cụm nào cũng lệch điểm nhau
và cả bảng câu hỏi bị xáo lại - thay đổi lớn về hành vi để đổi lấy một lợi ích không ai đo được.
Nhị phân chỉ tách đúng một ranh giới có ý nghĩa lâm sàng: cụm mang độ phủ bắt buộc đứng trước cụm
thuần làm giàu (tier O/H).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from src.services.symptom_protocol import protocol as protocol_mod
from src.services.symptom_protocol.models import QuestionCluster
from src.services.symptom_protocol.protocol import SymptomProtocol, clusters_for_stage
from src.services.symptom_protocol.stage_machine import MANDATORY_TIERS, field_is_settled

WEIGHT_SAFETY = 10_000
WEIGHT_OVERDUE = 5_000
WEIGHT_RELEVANCE = 1_000
WEIGHT_KEYWORD_RELEVANCE = 500
WEIGHT_MANDATORY_YIELD = 100
WEIGHT_DEBT_PER_TURN = 10
"""Khoảng cách giữa các bậc đủ lớn để không bậc thấp nào cộng dồn vượt được bậc cao hơn: trần hoãn
là 3 nên `debt` tối đa ~30, không bao giờ tới `WEIGHT_MANDATORY_YIELD`. Đây là điều kiện để bảng
điểm còn ĐỌC ĐƯỢC - một bảng mà mọi thứ đều có thể lật nhau thì không giải thích được vì sao agent
hỏi câu này."""


@dataclass(frozen=True, slots=True)
class RankingContext:
    """Tín hiệu của lượt vừa rồi. Rỗng (mặc định) ⇒ xếp hạng suy biến về thứ tự khai báo."""

    recent_fields: frozenset[str] = frozenset()
    """Field vừa thu được căn cứ ở lượt trước - nguồn của `relevance`. Ở kiến trúc mục tiêu đây là
    `field_events` của lượt vừa rồi (§8.4); hiện lấy từ kết quả trích xuất, cùng ý nghĩa."""

    recent_text: str = ""
    """Tin nhắn thô vừa nhận, dùng cho relevance từ khoá khi extractor chưa ghi được field."""

    deferred: dict[str, int] = field(default_factory=dict)
    """`cluster_id -> số lượt đã bị hoãn`, lấy từ `coverage.CoverageLedger`."""

    overdue: frozenset[str] = frozenset()
    """Cụm đã chạm `coverage.DEFERRAL_LIMIT`."""


_KEYWORD_STOPWORDS = frozenset({
    "ban", "khong", "thay", "nao", "muc", "do", "hien", "tai", "dang", "bat", "dau",
    "kem", "hoac", "moi", "binh", "thuong", "tu", "khi", "co", "cho", "mot", "nhung",
})


def _keyword_tokens(text: str) -> frozenset[str]:
    normalized = unicodedata.normalize("NFC", text.casefold())

    def is_stopword(token: str) -> bool:
        folded = unicodedata.normalize("NFD", token.replace("đ", "d"))
        plain = "".join(char for char in folded if unicodedata.category(char) != "Mn")
        return plain in _KEYWORD_STOPWORDS

    return frozenset(
        token for token in re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)
        if len(token) >= 3 and not is_stopword(token)
    )


def _matches_script_keyword(cluster: QuestionCluster, recent_text: str) -> bool:
    if not recent_text or not cluster.script_hint:
        return False
    return bool(_keyword_tokens(recent_text) & _keyword_tokens(cluster.script_hint))


def safety_field_keys(protocol: SymptomProtocol) -> frozenset[str]:
    """Field được coi là an toàn cốt lõi của protocol này: field của các cụm thuộc stage QUÉT ĐỎ.

    Suy ra từ dữ liệu ĐÃ khai báo (`emergency_scan_stage` + `clusters`) chứ không thêm một danh sách mới:
    một danh sách thứ hai sẽ lệch khỏi bảng câu hỏi ngay lần đầu ai đó sửa protocol.

    KHÔNG dùng `protocol.safety_signal_fields` cho việc này: tập đó trộn hai nhóm khác nhau (field đỏ
    tuyệt đối VÀ field "hay được nói sớm" như nhiệt độ, ngày khởi phát), nên dùng nó ở đây sẽ gắn
    nhãn an toàn cho cụm hỏi nhiệt độ."""
    scan_stages = protocol_mod.emergency_scan_stages(protocol)
    return frozenset(
        key
        for cluster in protocol.clusters
        if cluster.stage in scan_stages
        for key in cluster.fields
    )


def cluster_is_safety_critical(protocol: SymptomProtocol, cluster: QuestionCluster) -> bool:
    return bool(safety_field_keys(protocol) & set(cluster.fields))


def _fills_mandatory_field(protocol: SymptomProtocol, cluster: QuestionCluster, answers: dict[str, object]) -> bool:
    return any(
        protocol.fields_by_key[key].tier in MANDATORY_TIERS and not field_is_settled(protocol, key, answers)
        for key in cluster.fields
        if key in protocol.fields_by_key
    )


def score_cluster(
    protocol: SymptomProtocol,
    cluster: QuestionCluster,
    answers: dict[str, object],
    context: RankingContext,
) -> int:
    """Điểm của MỘT cụm. Hàm thuần - không đọc trạng thái nào ngoài tham số."""
    score = 0
    if cluster_is_safety_critical(protocol, cluster):
        score += WEIGHT_SAFETY
    if cluster.id in context.overdue:
        score += WEIGHT_OVERDUE
    if context.recent_fields & set(cluster.fields):
        score += WEIGHT_RELEVANCE
    if _matches_script_keyword(cluster, context.recent_text):
        score += WEIGHT_KEYWORD_RELEVANCE
    if _fills_mandatory_field(protocol, cluster, answers):
        score += WEIGHT_MANDATORY_YIELD
    score += WEIGHT_DEBT_PER_TURN * context.deferred.get(cluster.id, 0)
    return score


def rank_clusters(
    protocol: SymptomProtocol,
    stage: str,
    answers: dict[str, object],
    candidates: tuple[QuestionCluster, ...],
    context: RankingContext,
) -> tuple[QuestionCluster, ...]:
    """Sắp lại các cụm ĐÃ HỢP LỆ theo điểm giảm dần; hoà điểm giữ thứ tự khai báo.

    Không mở thêm cụm nào: việc lọc (`cluster_is_skipped`, `cluster_needs_answer`, ranh giới stage)
    chạy TRƯỚC và không đổi. Ranking chỉ đổi thứ tự bên trong tập vốn đã được phép hỏi."""
    declaration_order = {cluster.id: index for index, cluster in enumerate(clusters_for_stage(protocol, stage))}
    return tuple(
        sorted(
            candidates,
            key=lambda cluster: (
                -score_cluster(protocol, cluster, answers, context),
                declaration_order.get(cluster.id, len(declaration_order)),
            ),
        )
    )
