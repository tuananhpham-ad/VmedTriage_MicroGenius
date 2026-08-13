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

from src.services.infra.provider_router import LLMCredential
from src.services.symptom_protocol.models import FieldSpec, QuestionCluster, RuleMatch

RouteFn = Callable[[dict[str, object]], str]
BudgetKeyFn = Callable[[dict[str, object], str, "str | None"], str]
BoolPredicate = Callable[[dict[str, object]], bool]
SkipRuleFn = Callable[[QuestionCluster, dict[str, object]], bool]
RuleFn = Callable[[dict[str, object], "tuple[RuleMatch, ...]"], "RuleMatch | None"]
FallbackRuleFn = Callable[[dict[str, object]], RuleMatch]
DeriveFieldsFn = Callable[[dict[str, object]], dict[str, object]]


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

    derive_fields: DeriveFieldsFn | None = None
    """Tính field DẪN XUẤT (derived) từ field khác sau khi merge mỗi lượt - vd
    `fever_duration_days` tính từ `fever_onset_at`. KHÔNG bắt LLM tự nhẩm ngày tháng (không đáng tin
    cậy, LLM không biết "hôm nay" nếu không được cho biết) - đây là phép tính THUẦN, xác định. Trả
    `None` (mặc định) nếu protocol không cần field dẫn xuất nào."""

    default_credential: LLMCredential | None = None


def clusters_for_stage(protocol: SymptomProtocol, stage: str) -> tuple[QuestionCluster, ...]:
    return tuple(cluster for cluster in protocol.clusters if cluster.stage == stage)


def clusters_by_id(protocol: SymptomProtocol) -> dict[str, QuestionCluster]:
    return {cluster.id: cluster for cluster in protocol.clusters}
