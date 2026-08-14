"""`SymptomProtocol` - "hồ sơ cắm vào engine" của một symptom_group cụ thể (fever, chest_pain, ...).

Đây là RANH GIỚI DUY NHẤT giữa cơ chế (`stage_machine.py`/`rule_engine.py`/`intake_agent.py`/
`session.py`) và nội dung lâm sàng của từng bệnh. Thêm bệnh mới = tạo một `SymptomProtocol` mới, KHÔNG
đụng vào engine.

Các hàm `determine_route`/`provisional_emergency_signal`/`self_care_checklist_satisfied`/`budget_key`/
`skip_rule` vẫn là "nội dung" (mang phán đoán lâm sàng đặc thù bệnh), chỉ khác field/rule data ở chỗ
chúng là HÀM thay vì DATA thuần - vì logic route/ngân sách của mỗi bệnh có thể khác nhau về hình dạng,
không ép được về một bảng tra cứu chung. Engine chỉ GỌI các hàm này qua đúng chữ ký chuẩn hoá dưới đây,
không tự đoán nội dung bên trong.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field as dataclass_field

from src.services.infra.provider_router import LLMCredential
from src.services.symptom_protocol.models import FieldSpec, QuestionCluster, RuleMatch, ScreeningGroup

RouteFn = Callable[[dict[str, object]], str]
BudgetKeyFn = Callable[[dict[str, object], str, "str | None"], str]
BoolPredicate = Callable[[dict[str, object]], bool]
SkipRuleFn = Callable[[QuestionCluster, dict[str, object]], bool]
RuleFn = Callable[[dict[str, object], "tuple[RuleMatch, ...]"], "RuleMatch | None"]
FallbackRuleFn = Callable[[dict[str, object]], RuleMatch]
DeriveFieldsFn = Callable[[dict[str, object]], dict[str, object]]
ContradictionFn = Callable[[dict[str, object]], "tuple[str, ...]"]


@dataclass(frozen=True, slots=True)
class SymptomProtocol:
    name: str
    """Tên symptom_group, khớp `src/config.py` (`fever`, `chest_pain`, `breathing`, ...)."""

    fields_by_key: dict[str, FieldSpec]
    clusters: tuple[QuestionCluster, ...]
    """Đúng thứ tự bảng câu hỏi trong tài liệu nguồn của bệnh - stage_machine duyệt theo thứ tự này."""

    stage_order: tuple[str, ...]
    """Thứ tự stage cố định, vd `("0","1","2","3A","3B","4","5")`."""

    gate_stages: tuple[str, str]
    """2 stage dùng hướng C (extract -> rule-gate -> next_question tách biệt): (scan khẩn cấp, scan
    sớm/tự chăm sóc). Stage thứ 2 tự động bị skip nếu stage thứ 1 còn dấu hiệu khẩn cấp chưa loại trừ
    (đúng nguyên tắc "chỉ quét early-visit khi emergency-scan đã sạch")."""

    budget: dict[str, tuple[int, int]]
    budget_floor_stage: str
    """Ngân sách chỉ có hiệu lực TỪ stage này trở đi (CS Part 6(b): không được cắt field M0/M1/C dù
    đã vượt ngân sách danh nghĩa - stage_machine còn tự kiểm thêm việc cụm ứng viên có thuần tier
    O/H hay không trước khi thực sự cho dừng, xem `stage_machine.should_stop`)."""

    determine_route: RouteFn
    budget_key: BudgetKeyFn
    """`(answers, route, known_triage_level) -> khoá trong self.budget`."""

    provisional_emergency_signal: BoolPredicate
    """Quét RẤT NHẸ để `should_stop` biết khi nào nên dừng hỏi thường quy - KHÔNG phải rule engine
    đầy đủ, không sinh reason_codes/triggered_rules chính thức (đó là việc của `rule_engine.evaluate`)."""

    self_care_checklist_satisfied: BoolPredicate
    """Checklist bắt buộc trước khi được kết luận mức nhẹ nhất (SELF_CARE) - dùng bởi cả
    `stage_machine.should_stop` (điều kiện SUFFICIENT_EVIDENCE) lẫn `rule_engine.evaluate` (fallback
    khi không rule nào khớp)."""

    skip_rule: SkipRuleFn
    """`(cluster, answers) -> True` nếu cụm này nên bị bỏ qua (điều kiện tuổi/giới/nhánh phụ thuộc câu
    sàng lọc trước đó, vd Q4-00 gộp của fever) - trả `False` cho hầu hết cụm."""

    rule_catalog: tuple[RuleFn, ...]
    """Mỗi hàm nhận `(answers, matches_so_far)`, trả `RuleMatch` nếu khớp hoặc `None`. `matches_so_far`
    là tuple các match ĐÃ tìm được từ các rule đứng TRƯỚC trong catalog (theo đúng thứ tự khai báo) -
    dùng cho rule phụ thuộc kết quả rule khác (vd "nâng mức nếu ĐÃ có bất kỳ rule khẩn cấp nào khác
    khớp"). Đa số rule bỏ qua tham số này."""

    fallback_rule: FallbackRuleFn
    """Rule chạy khi KHÔNG rule nào trong catalog khớp VÀ `self_care_checklist_satisfied` cũng False -
    fever dùng để trả `R-G-02`/`EARLY_VISIT` (an toàn hơn mặc định `SELF_CARE`, đúng P0-6)."""

    self_care_default_rule: FallbackRuleFn
    """Rule chạy khi KHÔNG rule nào khớp VÀ `self_care_checklist_satisfied` True - fever dùng để trả
    `R-S-01`/`SELF_CARE`. Nhận `answers` để giữ chữ ký thống nhất với `fallback_rule`, thường bỏ qua."""

    emergency_message: str
    """Thông điệp cấp cứu TĨNH, không qua LLM (đúng P0-2 - không được để LLM tự sinh văn bản báo cấp
    cứu, rủi ro lỡ chẩn đoán/diễn đạt sai)."""

    safety_signal_fields: tuple[str, ...]
    """Field LUÔN được quét kèm trong schema trích xuất hướng E (stage ngoài `gate_stages`), dù không
    thuộc cụm đang hỏi - gồm 2 nhóm: (a) field đỏ tuyệt đối, để bắt red-flag người dùng tự mô tả trước
    khi hội thoại kịp tới gate stage; (b) field "hay được tự nguyện cung cấp sớm" (vd nhiệt độ, ngày
    khởi phát) - thiếu nhóm (b) khiến hội thoại có cảm giác "cứng", cứ hỏi lại thông tin người dùng đã
    lỡ nói ở lượt trước chỉ vì lúc đó chưa tới lượt cụm tương ứng (phát hiện qua test tay với LLM
    thật). KHÔNG đưa cả field registry vào đây - chỉ nhóm field thực sự hay bị "nói trước" tự nhiên."""

    opportunistic_keywords: tuple[tuple[str, tuple[str, ...]], ...]
    """Quét từ khoá nhẹ bổ trợ (kỹ thuật `_contains_any`), mỗi phần tử `(field_key, keywords)`."""

    screening_groups: tuple[ScreeningGroup, ...] = ()
    """Nhóm cơ quan được sàng lọc bằng một câu hỏi gộp (xem `ScreeningGroup`). Rỗng (mặc định) =
    protocol hỏi tuần tự từng cụm như trước - `screening.py` không có gì để làm nên không lượt nào
    đổi hành vi."""

    max_screening_rounds: int = 2
    """Số lượt sàng lọc tối đa cho MỖI stage. Chống lặp vô hạn khi người bệnh trả lời mãi không rõ:
    hết hạn mức thì tự rơi về đường hỏi từng cụm, không có nhánh nào làm hội thoại treo."""

    field_dependencies: dict[str, tuple[str, ...]] = dataclass_field(default_factory=dict)
    """`{field cha: (field con...)}` - khi field cha bị PHỦ ĐỊNH ("false"/"none"), các field con mất
    hết ý nghĩa và phải bị xoá về "unknown" (`retraction.apply_retraction`). Vd `fever_reported=false`
    ⇒ bỏ `temp_c`, `fever_onset_at`, `antipyretic_taken`... Không khai báo = protocol không có quan hệ
    phụ thuộc nào (mặc định an toàn: không xoá gì)."""

    contradiction_rules: tuple[ContradictionFn, ...] = ()
    """Mỗi hàm nhận `answers`, trả về các field ĐANG CHỌI NHAU (rỗng nếu không có mâu thuẫn). Đây là
    chiều NGƯỢC với `field_dependencies`: không xoá gì cả, chỉ mở lại cụm chứa các field đó để hỏi
    cho rõ. Vd hồ sơ ghi `fever_status=none` mà người bệnh vừa khai `temp_c=39.2` - hệ thống không có
    căn cứ để chọn bên nào, việc duy nhất đúng là hỏi lại."""

    confirm_before_retract: frozenset[str] = frozenset()
    """Field hệ trọng tới mức phải XIN XÁC NHẬN trước khi xoá dây chuyền, thay vì xoá thẳng. Chặn
    đúng bug C2: model hiểu nhầm "bé không **sốt xuất huyết**" (tên bệnh) thành "bé không **sốt**" rồi
    xoá sạch phần nhiệt độ đã khai. Giữ HẸP - mỗi field trong tập này tốn của người bệnh một lượt hội
    thoại, nên chỉ đưa vào field mà việc xoá nhầm thực sự đắt."""

    derive_fields: DeriveFieldsFn | None = None
    """Tính field DẪN XUẤT (derived) từ field khác sau khi merge mỗi lượt - vd
    `fever_duration_days` tính từ `fever_onset_at`. KHÔNG bắt LLM tự nhẩm ngày tháng (không đáng tin
    cậy, LLM không biết "hôm nay" nếu không được cho biết) - đây là phép tính THUẦN, xác định. Trả
    `None` (mặc định) nếu protocol không cần field dẫn xuất nào."""

    reason_code_labels: dict[str, str] = dataclass_field(default_factory=dict)
    """`RF-xx` -> nhãn tiếng Việt, CHỈ để hiển thị trên phiếu bàn giao. Rule engine chỉ trả về MÃ (mã
    là thứ ổn định để log/test), nhưng điều dưỡng đọc "RF-13" thì không có nghĩa gì. Bảng này KHÔNG
    tham gia bất kỳ quyết định nào - thiếu một mã chỉ làm phiếu hiện mã thô, không đổi kết luận."""

    # --- 4 field dưới đây CHỈ phục vụ phiếu bàn giao (`symptom_case_bridge.py`) -------------------
    # Chúng tồn tại để lớp bridge không phải biết tên field của từng bệnh. Bridge từng ghi cứng
    # `fever_onset_at`/`temp_c`/"Sốt", nên ca ngoài sốt vẫn bị gắn nhãn "Sốt" trong dữ liệu gửi đi -
    # sai DỮ LIỆU downstream, không phải sai hiển thị.
    chief_complaint_field: str = ""
    """Field chứa lời người bệnh tự mô tả than phiền. Rỗng = protocol không hỏi (fever biết trước
    than phiền là gì)."""

    default_chief_complaint: str = ""
    """Dùng khi `chief_complaint_field` rỗng hoặc chưa điền."""

    onset_field: str = ""
    severity_field: str = ""

    default_credential: LLMCredential | None = None


def clusters_for_stage(protocol: SymptomProtocol, stage: str) -> tuple[QuestionCluster, ...]:
    return tuple(cluster for cluster in protocol.clusters if cluster.stage == stage)


def clusters_by_id(protocol: SymptomProtocol) -> dict[str, QuestionCluster]:
    return {cluster.id: cluster for cluster in protocol.clusters}
