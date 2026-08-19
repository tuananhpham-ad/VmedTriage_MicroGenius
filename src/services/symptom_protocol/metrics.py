"""Metric TRẢI NGHIỆM + ĐỘ PHỦ của một phiên (§12) - P4.3.

VÌ SAO CẦN. §12 đặt ra một loạt ngưỡng (`user_led_ratio`, `repeat_question_rate`, `deferral_depth`,
`catch_all_yield`, `mandatory_coverage_at_close`) nhưng **không chỗ nào trong hệ thống tính ra được
những con số đó**. Một ngưỡng không đo được thì không phải gate, nó chỉ là một câu trong tài liệu.

HAI NHÓM PHẢI ĐỌC CÙNG NHAU. §12 nói rõ: cải thiện trải nghiệm bằng cách hy sinh độ phủ là hỏng, và
ngược lại. Vì thế `summary()` trả cả hai nhóm trong một dict chứ không tách hai hàm - tách ra là mời
người đọc trích một nửa.

ĐO TẠI CHỖ, KHÔNG SUY LẠI TỪ LOG. Ba lý do: (a) `user_led` cần `recent_fields` của ĐÚNG lượt đó, mà
sau khi merge vào `answers` thì không còn phân biệt được field nào vừa được nhắc tới; (b) `deferral_
depth` cần số nợ TẠI THỜI ĐIỂM cụm được chọn - `CoverageLedger` xoá nợ ngay khi cụm được hỏi;
(c) một bộ phân tích log là một bản định nghĩa thứ hai của cùng khái niệm, và hai bản sẽ lệch nhau.

TẦNG NÀY KHÔNG QUYẾT ĐỊNH GÌ. Nó chỉ đếm. Không nhánh nào trong `session`/`stage_machine` được đọc
`ConversationMetrics` để đổi hành vi - một chỉ số vừa đo vừa điều khiển là chỉ số không còn đo được
cái gì (và §8.8 đã cấm hệ thống xếp hạng tự điều chỉnh theo phiên).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.services.symptom_protocol import coverage, stage_machine
from src.services.symptom_protocol.models import QuestionCluster
from src.services.symptom_protocol.protocol import SymptomProtocol


@dataclass(slots=True)
class ConversationMetrics:
    """Bộ đếm cộng dồn theo lượt. Một phiên một bản, sống cùng `Session`."""

    questions_asked: int = 0
    """Số câu hỏi CỤM đã phát ra. Mẫu số của `user_led_ratio` và `repeat_question_rate` - mọi tỉ lệ
    phải đi kèm mẫu số, không có mẫu số thì không phải gate (§12)."""
    user_led_questions: int = 0
    """Câu hỏi thuộc cụm mà người bệnh VỪA tự nhắc tới ở lượt trước (§8.4)."""
    repeated_questions: int = 0
    """Câu hỏi cho một cụm đã hỏi trước đó VÀ đã đi qua cụm khác ở giữa - tức QUAY VÒNG thật.

    Phải gần 0. Khác 0 nghĩa là một cụm đã đóng được chọn lại, đúng lớp bug C3."""
    retried_questions: int = 0
    """Hỏi LẠI NGAY cùng một cụm vì lượt trước không thu được gì - **đúng thiết kế**
    (`MAX_RETRIES_PER_CLUSTER`), không phải lỗi.

    Tách khỏi `repeated_questions` sau khi đọc log ngày 2026-08-19: `repeat_question_rate` đo ra 0.32
    (ca tệ nhất 0.50) và trông như hệ thống đang quay vòng, nhưng đọc chuỗi cụm thì thấy mẫu
    `G1-02 -> G1-02 -> G1-02` - đúng 3 lần, tức 1 lần hỏi + 2 lần retry theo hằng số. Gộp hai khái
    niệm vào một con số làm chỉ số vừa báo động giả vừa che mất ca quay vòng thật.

    Đọc chỉ số này như "câu hỏi nào người bệnh không trả lời được" - cao nghĩa là câu hỏi khó hiểu
    hoặc extractor không khớp, chứ không phải state machine sai."""
    asked_cluster_ids: list[str] = field(default_factory=list)
    """Lịch sử cụm đã hỏi, theo thứ tự. Giữ danh sách chứ không giữ set: `repeated_questions` cần
    biết một cụm quay lại LẦN THỨ MẤY, và thứ tự là thứ duy nhất trả lời được "vì sao agent hỏi câu
    này" khi đọc lại."""
    asked_field_keys: set[str] = field(default_factory=set)
    """Field đã từng nằm trong schema của một câu hỏi. Tách khỏi `asked_cluster_ids` vì cụm TỔNG HỢP
    (`BATCH-`, `SCREEN-`, cụm quét sót) mang mã tự sinh không có trong `protocol.clusters` - so mã cụm
    sẽ báo bỏ sót giả cho mọi field chỉ được hỏi qua đường gộp."""
    deferral_depth_samples: list[int] = field(default_factory=list)
    """Số lượt một cụm đã bị hoãn TẠI THỜI ĐIỂM nó được chọn. Đo ở đây vì ledger xoá nợ ngay sau đó."""
    catch_all_asked: bool = False
    catch_all_yielded: bool = False
    """Bước quét sót có thu được dữ kiện mới không. Gần 0 trên toàn tập nghĩa là hoặc checklist đã đủ,
    hoặc câu quét sót đang được hỏi sai cách - hai kết luận rất khác nhau, nên chỉ số này vô nghĩa
    nếu không đọc kèm `catch_all_asked`."""

    def record_question(
        self, cluster: QuestionCluster | None, *, recent_fields: frozenset[str], deferral_count: int,
    ) -> None:
        """Ghi nhận MỘT câu hỏi cụm sắp phát ra.

        `recent_fields` là field thu được từ chính tin nhắn vừa rồi - nếu cụm sắp hỏi chạm vào một
        trong số đó thì agent đang đi theo mạch người bệnh, đúng thứ §8.4 nhắm tới. Đây cũng là lý do
        phải đo TẠI CHỖ: sau khi merge, `answers` không còn phân biệt "vừa nói" với "đã biết từ lâu"."""
        if cluster is None:
            return
        self.questions_asked += 1
        if recent_fields & frozenset(cluster.fields):
            self.user_led_questions += 1
        if self.asked_cluster_ids and cluster.id == self.asked_cluster_ids[-1]:
            # Cụm NGAY TRƯỚC cũng là cụm này -> hỏi lại vì chưa thu được gì (đúng thiết kế).
            self.retried_questions += 1
        elif cluster.id in self.asked_cluster_ids:
            # Đã đi qua cụm khác rồi mới quay lại -> QUAY VÒNG. Đây mới là thứ phải gần 0.
            self.repeated_questions += 1
        self.asked_cluster_ids.append(cluster.id)
        self.asked_field_keys.update(cluster.fields)
        self.deferral_depth_samples.append(deferral_count)

    def record_catch_all_asked(self) -> None:
        """Câu quét sót vừa PHÁT RA. Tách khỏi `record_catch_all_answer` vì hai việc xảy ra ở hai
        lượt khác nhau, và phiên có thể kết thúc giữa chừng - lúc đó `asked=True, yielded=False` là
        mô tả đúng, không phải dữ liệu thiếu."""
        self.catch_all_asked = True

    def record_catch_all_answer(self, *, yielded: bool) -> None:
        self.catch_all_yielded = yielded

    def summary(
        self,
        protocol: SymptomProtocol,
        answers: dict[str, object],
        *,
        turns: int,
        stop_reason: str | None,
        triage_level: str | None,
    ) -> dict[str, object]:
        """Bản đọc được của một phiên đã đóng. Tỉ lệ trả `None` khi mẫu số bằng 0.

        `None` chứ không phải `0.0`: một phiên chưa hỏi câu nào có `user_led_ratio` KHÔNG XÁC ĐỊNH,
        và gộp nó vào trung bình dưới dạng 0 sẽ kéo chỉ số của cả tập xuống bằng những phiên chưa hề
        chạy. Đây đúng là cách §12 đọc sai một con số 100% trên 20 ca."""
        return {
            "turns": turns,
            "stop_reason": stop_reason,
            "triage_level": triage_level,
            # --- độ phủ: loại 1 của §8.1, không được đánh đổi lấy trải nghiệm ---
            #
            # HAI chỉ số, và đọc nhầm cái nào cho cái kia là hiểu sai hệ thống:
            #
            # - `mandatory_coverage_at_close` = mọi field M0/M1 CÓ CĂN CỨ. Hệ thống **không bảo đảm**
            #   chỉ số này đạt 100%, và đó là quyết định có chủ đích: người bệnh trả lời "không biết"
            #   là một kết quả HỢP LỆ (§8.5 quy tắc 3), nhưng field vẫn `unknown`. Đặt gate 100% lên
            #   nó (§12) là đặt một gate không bao giờ qua được.
            # - `mandatory_unasked` = field M0/M1 chưa có căn cứ VÀ cụm chứa nó CHƯA HỀ ĐƯỢC HỎI.
            #   **Đây mới là bất biến hệ thống thật sự giữ** (§8.2 mục 1 + `should_stop`): linh hoạt
            #   được đổi thứ tự hỏi, không được BỎ hỏi. Rỗng = không bỏ sót cụm nào.
            "mandatory_coverage_at_close": stage_machine.mandatory_fields_covered(protocol, answers),
            "mandatory_remaining": list(coverage.mandatory_remaining(protocol, answers)),
            "mandatory_unasked": self._mandatory_unasked(protocol, answers),
            # --- trải nghiệm ---
            "questions_asked": self.questions_asked,
            "user_led_ratio": _ratio(self.user_led_questions, self.questions_asked),
            "repeat_question_rate": _ratio(self.repeated_questions, self.questions_asked),
            "retry_rate": _ratio(self.retried_questions, self.questions_asked),
            "deferral_depth": _mean(self.deferral_depth_samples),
            "catch_all_asked": self.catch_all_asked,
            "catch_all_yielded": self.catch_all_yielded,
            # §8: phiên kết thúc vì người bệnh không khai tiếp - ba mã, đọc RIÊNG chứ không gộp.
            # `abandoned` là chỉ số trải nghiệm THẬT NHẤT (§1 bất biến 10), và nó chỉ có nghĩa khi
            # tách khỏi `NO_MORE_SYMPTOMS`: người bệnh nói "hết rồi" là kết thúc BÌNH THƯỜNG, còn
            # người bỏ dở giữa chừng mới là ca ta muốn giảm.
            "abandoned": stop_reason in _ABANDON_STOP_REASONS,
            "uncooperative_stop": stop_reason == "USER_UNCOOPERATIVE",
        }


    def _mandatory_unasked(
        self, protocol: SymptomProtocol, answers: dict[str, object],
    ) -> list[str]:
        """Field M0/M1 chưa có căn cứ mà CHƯA HỀ nằm trong schema của câu hỏi nào - tức bỏ sót thật.

        Phân biệt hai thứ mà `mandatory_remaining` gộp làm một: "đã hỏi, người bệnh không biết" (hợp
        lệ theo §8.5 quy tắc 3) và "chưa bao giờ hỏi" (bỏ sót). Không có phân biệt này thì không đọc
        được số liệu nào - mọi phiên có người bệnh trả lời "không rõ" đều trông giống một lỗi độ phủ.

        ĐẾM THEO FIELD, KHÔNG THEO MÃ CỤM. Bản đầu so mã cụm và báo `indwelling_device` bỏ sót ở 6/6
        phiên - sai, vì các cụm TỔNG HỢP mang mã tự sinh không có trong `protocol.clusters`:
        `BATCH-<stage>-<id>+<id>` mã hoá cụm thành phần, còn `SCREEN-<stage>` thì KHÔNG mã hoá gì cả.
        Cả hai đều mang **hợp field** của các cụm bên trong (`batching`/`screening.probe_fields`), nên
        field là đơn vị duy nhất đúng cho mọi loại cụm - kể cả cụm quét sót dựng tại chỗ."""
        remaining = set(coverage.mandatory_remaining(protocol, answers))
        # Field DẪN XUẤT không bao giờ nằm trong schema của một câu hỏi - đó là đúng thiết kế, không
        # phải bỏ sót. Không trừ chúng ra thì `mandatory_unasked` khác 0 ở MỌI phiên của protocol có
        # field dẫn xuất, và một chỉ số không bao giờ về 0 thì không ai còn đọc nó nữa (đo được
        # 2026-08-19: `complaint_duration_days` của generic bị đếm là bỏ sót dù field nguồn
        # `complaint_onset_at` đã được hỏi ở G1-01).
        return sorted(remaining - self.asked_field_keys - set(protocol.derived_field_keys))


_ABANDON_STOP_REASONS = frozenset({"USER_CANNOT_CONTINUE", "USER_UNCOOPERATIVE"})
"""Mã dừng đọc là "người bệnh bỏ dở".

`NO_MORE_SYMPTOMS` **không** nằm ở đây dù nó cũng đến từ ý định người bệnh: nói "không còn triệu
chứng nào khác" khi hệ thống cũng không còn cụm bắt buộc nào là một phiên kết thúc ĐÚNG, không phải
một ca bỏ cuộc. Gộp lại thì `abandonment_rate` tăng mỗi khi hội thoại chạy trơn tru - tức là chỉ số
sẽ thưởng cho đúng cái nó cần phạt."""


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator <= 0 else round(numerator / denominator, 4)


def _mean(values: list[int]) -> float | None:
    return None if not values else round(sum(values) / len(values), 4)


def aggregate(summaries: list[dict[str, object]]) -> dict[str, object]:
    """Gộp nhiều phiên thành một bảng. Mọi tỉ lệ đi KÈM MẪU SỐ (§12 câu cuối).

    MẪU SỐ CỦA `mandatory_coverage_at_close` LOẠI HAI NHÓM, và cả hai đều là quyết định có chủ đích:

    1. **Phiên dừng vì `RED_FLAG`** - được phép thiếu field (§8.2 mục 1: escalate ngay quan trọng hơn
       hỏi nốt checklist). Gộp vào thì chỉ số không bao giờ đạt 100% dù hệ thống chạy đúng.
    2. **Phiên CHƯA ĐÓNG** (`stop_reason is None`) - phiên chạm trần lượt của harness, hoặc bị cắt
       giữa chừng. Tên chỉ số là "at close"; một phiên chưa đóng chưa có cơ hội đạt độ phủ, nên tính
       nó là "đóng mà thiếu field" là đọc sai theo hướng nguy hiểm: nó biến một giới hạn của công cụ
       đo thành một lỗi của hệ thống, và ngược lại có thể che một lỗi thật.

    Cả hai nhóm vẫn được ĐẾM và báo cáo riêng - loại khỏi mẫu số không phải là giấu đi."""
    closed = [item for item in summaries if item.get("stop_reason") is not None]
    unclosed = len(summaries) - len(closed)
    normal = [item for item in closed if item.get("stop_reason") != "RED_FLAG"]
    covered = [item for item in normal if item.get("mandatory_coverage_at_close")]
    return {
        "sessions": len(summaries),
        "sessions_normal_close": len(normal),
        "sessions_red_flag": len(closed) - len(normal),
        "sessions_never_closed": unclosed,
        "mandatory_coverage_at_close": {
            "value": _ratio(len(covered), len(normal)),
            "n": len(normal),
            "covered": len(covered),
        },
        # BẤT BIẾN THẬT của hệ thống, và là con số nên đọc trước hai con số phía trên: linh hoạt được
        # đổi THỨ TỰ hỏi, không được BỎ hỏi. Khác 0 = có cụm mang field M0/M1 bị bỏ qua im lặng, tức
        # §8.2 mục 1 đã vỡ và phải dừng lại.
        "sessions_with_unasked_mandatory": sum(
            1 for item in normal if item.get("mandatory_unasked")
        ),
        "turns_median": _median([_as_float(item.get("turns")) for item in summaries]),
        # Tách riêng vì §12 yêu cầu đọc "số lượt trung vị" theo NHÓM: ca cần khoan sâu và ca lành
        # tính có phân bố rất khác nhau, gộp lại thì một con số trung vị không nói lên điều gì.
        "turns_median_normal_close": _median([_as_float(item.get("turns")) for item in normal]),
        "user_led_ratio": _weighted(summaries, "user_led_ratio", "questions_asked"),
        "repeat_question_rate": _weighted(summaries, "repeat_question_rate", "questions_asked"),
        "retry_rate": _weighted(summaries, "retry_rate", "questions_asked"),
        "deferral_depth": _mean_of(summaries, "deferral_depth"),
        "catch_all_yield": _catch_all_yield(summaries),
        # Mẫu số là phiên ĐÃ ĐÓNG: một phiên chưa đóng chưa có cơ hội bị bỏ dở, và tính nó vào sẽ
        # làm chỉ số phụ thuộc vào trần lượt của harness thay vì vào hành vi người bệnh.
        "abandonment_rate": _rate_over(closed, "abandoned"),
        "uncooperative_stop_rate": _rate_over(closed, "uncooperative_stop"),
        "stop_reasons": _stop_reason_histogram(closed),
        "red_flag_agreement": _red_flag_agreement(summaries),
    }


def _red_flag_agreement(summaries: list[dict[str, object]]) -> dict[str, object]:
    """Gộp bản đối chiếu ba nhánh red-flag của mọi phiên (§4.1).

    `model_only` là **output có giá trị nhất của cả cơ chế** - danh sách ứng viên để bổ sung vào
    rule, tức là câu trả lời cho "rule của chúng ta có bỏ sót gì không" mà baseline `emergency
    recall 48.9%` đang đặt ra mà chưa có cách trả lời. Vì thế nó được liệt kê ĐÍCH DANH kèm số lần
    xuất hiện, không gộp thành một con số.

    Mẫu số LOẠI phiên có `model_branch_status == "failed"`: một provider chết cả ngày sẽ trông y hệt
    một ngày không ca nào có red flag, và gộp hai thứ đó lại làm `agreement_rate` mất hết ý nghĩa.
    Số phiên lỗi vẫn được đếm và báo riêng - loại khỏi mẫu số không phải là giấu đi."""
    blocks = [
        item["red_flag_agreement"] for item in summaries
        if isinstance(item.get("red_flag_agreement"), dict)
    ]
    scored = [b for b in blocks if b.get("model_branch_status") == "ok"]
    failed = sum(1 for b in blocks if b.get("model_branch_status") == "failed")
    rule_only: dict[str, int] = {}
    model_only: dict[str, int] = {}
    both = 0
    for block in scored:
        for code in block.get("rule_only") or []:
            rule_only[code] = rule_only.get(code, 0) + 1
        for code in block.get("model_only") or []:
            model_only[code] = model_only.get(code, 0) + 1
        both += len(block.get("both") or [])
    total = sum(rule_only.values()) + sum(model_only.values()) + both
    return {
        "value": None if total == 0 else round(both / total, 4),
        "n": len(scored),
        "model_branch_failed_sessions": failed,
        "model_only": dict(sorted(model_only.items(), key=lambda kv: -kv[1])),
        "rule_only": dict(sorted(rule_only.items(), key=lambda kv: -kv[1])),
    }


def _rate_over(summaries: list[dict[str, object]], key: str) -> dict[str, object]:
    hits = [item for item in summaries if item.get(key)]
    return {"value": _ratio(len(hits), len(summaries)), "n": len(summaries), "hits": len(hits)}


def _stop_reason_histogram(summaries: list[dict[str, object]]) -> dict[str, int]:
    """Đếm theo TỪNG mã dừng. §7.2 mục 4 đòi ba lý do dừng phải phân biệt được trên phiếu; ở tầng
    tổng hợp thì "phân biệt được" nghĩa là chúng có ba ô đếm riêng, không phải một ô "đã dừng"."""
    histogram: dict[str, int] = {}
    for item in summaries:
        reason = str(item.get("stop_reason") or "UNKNOWN")
        histogram[reason] = histogram.get(reason, 0) + 1
    return dict(sorted(histogram.items()))


def _catch_all_yield(summaries: list[dict[str, object]]) -> dict[str, object]:
    """Mẫu số là các phiên THẬT SỰ chạy bước quét sót, không phải toàn bộ phiên: ca cấp cứu cố ý bỏ
    bước này (§8.6), gộp vào sẽ làm chỉ số trông như câu quét sót đang vô dụng."""
    asked = [item for item in summaries if item.get("catch_all_asked")]
    yielded = [item for item in asked if item.get("catch_all_yielded")]
    return {"value": _ratio(len(yielded), len(asked)), "n": len(asked), "yielded": len(yielded)}


def _weighted(summaries: list[dict[str, object]], key: str, weight_key: str) -> dict[str, object]:
    """Trung bình có TRỌNG SỐ theo số câu hỏi, không phải trung bình của các tỉ lệ.

    Trung bình của tỉ lệ cho một phiên 2 câu hỏi cùng sức nặng với một phiên 20 câu - trong khi cái ta
    muốn biết là "trong tất cả câu hỏi hệ thống đã đặt ra, bao nhiêu phần trăm đi theo mạch người
    bệnh"."""
    numerator = 0.0
    denominator = 0
    for item in summaries:
        value, weight = item.get(key), item.get(weight_key)
        if value is None or not isinstance(weight, int) or weight <= 0:
            continue
        numerator += float(value) * weight
        denominator += weight
    return {
        "value": None if denominator == 0 else round(numerator / denominator, 4),
        "n": denominator,
    }


def _mean_of(summaries: list[dict[str, object]], key: str) -> dict[str, object]:
    values = [float(item[key]) for item in summaries if item.get(key) is not None]
    return {
        "value": None if not values else round(sum(values) / len(values), 4),
        "n": len(values),
    }


def _as_float(value: object) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return round((ordered[middle - 1] + ordered[middle]) / 2, 4)
