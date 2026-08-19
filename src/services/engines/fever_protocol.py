"""Nội dung fever (field/cụm/rule/route/checklist) đăng ký vào engine chung `symptom_protocol/`.

Đây là "bản data" của fever sau khi tách cơ chế ra dùng chung (xem
`_guidance/fever-detect-agent-task.md`, mục "kế thừa được"). File này chứa:

- Rule catalog `R-E-xx`/`R-V-xx`/`R-G-01` (KM §6.1) - ánh xạ `RF-xx` sang mức triage.
- Các hook lâm sàng: `determine_route` (CS §4.3), `has_provisional_emergency_signal` (Part 1.3),
  `self_care_checklist_satisfied` (KM §5.4), `budget_key` (CS §6.5), `skip_rule` (CS Part 3 - điều
  kiện "Ask condition" khác "luôn hỏi").
- `FEVER_PROTOCOL`: gói tất cả lại thành 1 `SymptomProtocol`, dùng bởi
  `fever_stage_machine.py`/`fever_red_flag_engine.py`/`fever_intake_agent.py`/`fever_session.py`
  (các file đó giờ chỉ là lớp mỏng gọi vào engine chung với `FEVER_PROTOCOL`).

KHÔNG import LLM/provider_router ở đây - mọi hàm trong file này THUẦN rule-based.
"""

from __future__ import annotations

from typing import Literal

from src.services.checklists.fever_checklist import FIELDS_BY_KEY, QUESTION_CLUSTERS
from src.services.symptom_protocol.common_safety import rules as common_rules
from src.services.symptom_protocol.common_safety import screening_groups as common_screening
from src.services.symptom_protocol.common_safety.emergency_message import SUSPECTED_RED_FLAG_MESSAGE
from src.services.symptom_protocol.common_safety.predicates import age_in_months
from src.services.symptom_protocol.common_safety.predicates import array_has_any as _array_has_any
from src.services.symptom_protocol.common_safety.predicates import as_float as _as_float
from src.services.symptom_protocol.common_safety.predicates import is_true as _is_true
from src.services.symptom_protocol.models import QuestionCluster, RuleMatch
from src.services.symptom_protocol.protocol import SymptomProtocol

Route = Literal[
    "ROUTE_INFANT_HIGH",
    "ROUTE_HIGH_RISK",
    "ROUTE_STANDARD",
    "ROUTE_DENGUE_CONTEXT",
    "ROUTE_LOCALIZED_SOURCE",
]

STAGE_ORDER: tuple[str, ...] = ("0", "1", "2", "3A", "3B", "4", "5")
GATE_STAGES: tuple[str, str] = ("3A", "3B")
# Ngân sách CS §6.5 bắt đầu có hiệu lực từ Stage 4. Trước đây là "5" - cũng chính là stage CUỐI, nên
# ngân sách 12-16 cụm không bao giờ cắt được gì trước khi hội thoại đã đi hết Stage 4 (10 cụm). Đặt ở
# "4" cho ngân sách đúng vai trò của nó, trong khi Stage 3A/3B (quét đỏ, không được rút gọn) vẫn nằm
# ngoài tầm với của nó.
BUDGET_FLOOR_STAGE = "4"

# CS §6.5 - ngân sách câu hỏi tính theo CỤM (không phải field đơn lẻ), khoá theo route/kết luận.
# ROUTE_DENGUE_CONTEXT không có hàng riêng trong §6.5 - tài liệu mô tả nó "đào sâu" bộ câu hỏi trước
# khi kết luận, nên dùng chung ngân sách với nhóm ứng viên SELF_CARE (12-16) [EN - suy luận hợp lý từ
# §4.3/§6.5, không có con số riêng trong tài liệu nguồn].
BUDGET: dict[str, tuple[int, int]] = {
    "ROUTE_INFANT_HIGH": (3, 6),
    "EMERGENCY": (3, 6),
    "EARLY_VISIT": (8, 12),
    "ROUTE_HIGH_RISK": (8, 12),
    "SELF_CARE_CANDIDATE": (12, 16),
    "ROUTE_DENGUE_CONTEXT": (12, 16),
}

# Field M0 "đỏ tuyệt đối" dùng cho provisional scan (should_stop) VÀ cho việc quét kèm field an toàn
# ngoài cụm đang hỏi. Value coi là dương tính: chuỗi tri-state "true", hoặc enum/giá trị cụ thể liệt
# kê trong `_EMERGENCY_ENUM_MATCHES`.
#
# `worse_after_defervescence` (mệt hơn DÙ ĐÃ hạ sốt - RF-29 theo QĐ 2760) là dấu hiệu đỏ của riêng
# fever, nên nó nối thêm vào bộ phổ quát chứ không nằm trong `common_safety`.
EMERGENCY_TRI_STATE_FIELDS: tuple[str, ...] = common_rules.EMERGENCY_TRI_STATE_FIELDS + (
    "worse_after_defervescence",
)
# Field "hay được tự nguyện nói trước" (nhóm b trong docstring `SymptomProtocol.safety_signal_fields`)
# - không phải dấu hiệu đỏ, nhưng người dùng thường kể ngay ở tin nhắn đầu (vd "bé 38 độ", "sốt 2 ngày
# nay") dù chưa tới lượt hỏi cụm tương ứng. Thiếu quét kèm khiến hệ thống hỏi lại thông tin đã có
# (phát hiện qua test tay với LLM thật).
#
# Bộ bối cảnh nguy cơ (`is_pregnant`/`chronic_conditions`/`immunocompromised`) nằm ở Stage 4, cách
# lượt mở hơn cả cửa sổ `SAFETY_LOOKAHEAD_CLUSTERS` - nhưng đó lại đúng nhóm người bệnh tự khai sớm
# nhất ("em đang mang thai 20 tuần", "tôi bị tiểu đường"). Không quét kèm thì lời khai đó rơi mất và
# tới Stage 4 hệ thống hỏi lại nguyên văn. Chỉ MỞ SCHEMA trích xuất, không đụng rule nào.
_EARLY_VOLUNTEERED_FIELDS: tuple[str, ...] = (
    "temp_c",
    "temp_site",
    "fever_onset_at",
    "consciousness_level",
    "feeding_intake",
    "urine_output",
    "is_pregnant",
    "chronic_conditions",
    "immunocompromised",
)
SAFETY_SIGNAL_FIELDS: tuple[str, ...] = EMERGENCY_TRI_STATE_FIELDS + _EARLY_VOLUNTEERED_FIELDS
_EMERGENCY_ENUM_MATCHES: dict[str, frozenset[str]] = common_rules.EMERGENCY_ENUM_MATCHES

CHRONIC_SEVERE = common_rules.CHRONIC_SEVERE

# Quét cơ hội: field an toàn cốt lõi thường được người dùng chủ động mô tả ngay từ câu đầu tiên, trước
# khi tới lượt hỏi cụm tương ứng (đúng ví dụ O1, Part 8 CS). Toàn bộ danh sách là dấu hiệu đỏ phổ quát
# nên nằm ở `common_safety` - fever chưa có từ khoá đặc thù nào cần nối thêm.
OPPORTUNISTIC_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = common_rules.OPPORTUNISTIC_KEYWORDS


# Nhãn tiếng Việt của từng `RF-xx`, chép nguyên văn cột tên dấu hiệu ở bảng KM §6.1. Rule engine chỉ
# trả về MÃ (`reason_codes`) - mã là thứ ổn định để log/test, nhưng điều dưỡng đọc phiếu bàn giao thì
# "RF-13" không có nghĩa gì. Bảng này chỉ để HIỂN THỊ, không tham gia bất kỳ quyết định nào.
REASON_CODE_LABELS: dict[str, str] = {
    "RF-01": "Giảm ý thức",
    "RF-02": "Đang co giật / vừa co giật",
    "RF-03": "Co giật phức tạp",
    "RF-04": "Cứng gáy / thóp phồng / sợ ánh sáng",
    "RF-05": "Lú lẫn / thay đổi hành vi mới",
    "RF-06": "Dấu thần kinh khu trú mới",
    "RF-07": "Khó thở nặng",
    "RF-08": "Tím tái",
    "RF-09": "Dấu suy hô hấp ở trẻ",
    "RF-10": "Thở rít / chảy dãi, không nuốt được",
    "RF-11": "Thở nhanh + SpO2 <= 95% khí trời",
    "RF-12": "Đau ngực / ho ra máu kèm sốt",
    "RF-13": "Dấu hiệu sốc",
    "RF-14": "Không tiểu > 6 giờ",
    "RF-15": "Không uống được / nôn tất cả",
    "RF-16": "Mất nước có dấu hiệu",
    "RF-17": "Choáng / ngất khi đứng dậy",
    "RF-18": "Ban không mất khi ấn kính",
    "RF-19": "Xuất huyết niêm mạc",
    "RF-20": "Xuất huyết tiêu hóa",
    "RF-21": "Vàng da mới",
    "RF-22": "Sốt ở trẻ < 3 tháng",
    "RF-23": "Sốt cao ở trẻ 3-6 tháng",
    "RF-24": "Hạ thân nhiệt",
    "RF-25": "Nghi tăng thân nhiệt bệnh lý (say nắng / say nóng)",
    "RF-26": "Sốt kéo dài >= 5 ngày",
    "RF-27": "Sốt kéo dài >= 7 ngày",
    "RF-28": "Rét run dữ dội",
    "RF-29": "Khó chịu hơn dù đã hạ sốt",
    "RF-30": "Sốt + giảm bạch cầu hạt / hóa trị <= 6 tuần",
    "RF-31": "Sốt + suy giảm miễn dịch khác",
    "RF-32": "Sốt + thai kỳ hoặc hậu sản <= 6 tuần",
    "RF-33": "Sốt + phẫu thuật / thủ thuật <= 30 ngày",
    "RF-34": "Sốt + thiết bị lưu trong cơ thể",
    "RF-35": "Sốt sau du lịch vùng sốt rét <= 3 tháng",
    "RF-36": "Sốt + bệnh mạn tính nặng",
    "RF-37": "Sốt ở người >= 75 tuổi",
    "RF-38": "Sống một mình / không ai theo dõi / xa cơ sở y tế",
    "RF-39": "Đau bụng dữ dội / bụng cứng",
    "RF-40": "Nôn nhiều",
    "RF-41": "Sưng đau khớp/chi, không đi được, không dùng chi",
    "RF-42": "Triệu chứng tiết niệu ở trẻ < 5 tuổi sốt không rõ ổ",
    "RF-43": "Ổ nhiễm khuẩn khu trú tiến triển",
    "RF-44": 'Mức lo lắng người chăm sóc rất cao / "trông khác hẳn"',
}


def _fever_present(a: dict[str, object]) -> bool:
    return _is_true(a.get("fever_reported")) or a.get("fever_status") in ("objective", "subjective")


def _months_since(iso_date: object) -> float | None:
    """Ước lượng số tháng từ một ngày ISO tới "hiện tại" giả định trong tài liệu (2026-08-12, theo
    ngày soạn KM/CS). Chỉ dùng cho rule sốt rét (R-E-19/R-V-20) - không dùng cho quyết định lâm sàng
    khác."""
    if not isinstance(iso_date, str):
        return None
    from datetime import date

    try:
        year, month, day = (int(part) for part in iso_date[:10].split("-"))
        returned = date(year, month, day)
    except ValueError:
        return None
    reference = date(2026, 8, 12)
    return (reference - returned).days / 30.0


def derive_duration(answers: dict[str, object]) -> dict[str, object]:
    """Field DẪN XUẤT `fever_duration_days` = số ngày từ `fever_onset_at` tới NGÀY THỰC (khác
    `_months_since` ở trên, cố tình dùng mốc tài liệu cố định chỉ cho rule sốt rét). KHÔNG bắt LLM tự
    tính (không đáng tin), và KHÔNG ghi đè nếu đã có sẵn `fever_duration_days` hợp lệ (vd người dùng tự
    nói số ngày trực tiếp thay vì ngày khởi phát)."""
    onset = answers.get("fever_onset_at")
    if not isinstance(onset, str):
        return {}
    from datetime import date, timezone
    from datetime import datetime as _datetime

    try:
        year, month, day = (int(part) for part in onset[:10].split("-"))
        onset_date = date(year, month, day)
    except ValueError:
        return {}
    today = _datetime.now(timezone.utc).date()
    days = (today - onset_date).days
    if days < 0:
        return {}
    return {"fever_duration_days": days}


def _travel_within_months(a: dict[str, object], months: float) -> bool | None:
    history = a.get("travel_history_12m")
    if not isinstance(history, (list, tuple)) or not history:
        return None
    deltas = [_months_since(entry.get("return_date")) for entry in history if isinstance(entry, dict)]
    deltas = [delta for delta in deltas if delta is not None]
    if not deltas:
        return None
    return min(deltas) <= months


def conservatism_tier(a: dict[str, object]) -> int:
    """KM §5.1-5.2 - hệ số thận trọng theo quần thể. Dùng nội bộ cho rule hạ thân nhiệt (R-E-15)."""
    age_months = age_in_months(a)
    if age_months is not None and age_months < 3:
        return 2
    if _is_true(a.get("known_neutropenia")) or _array_has_any(a.get("immunocompromise_cause"), frozenset({"chemotherapy_6w"})):
        return 2
    if (
        _is_true(a.get("is_pregnant"))
        or _is_true(a.get("postpartum_6w"))
        or _is_true(a.get("immunocompromised"))
        or _array_has_any(a.get("chronic_conditions"), CHRONIC_SEVERE)
        or (age_months is not None and age_months >= 75 * 12)
    ):
        return 1
    return 0


def has_provisional_emergency_signal(answers: dict[str, object]) -> bool:
    """Quét rất nhẹ các field M0 đỏ tuyệt đối - CHỈ dùng để biết khi nào nên dừng hỏi thường quy
    (Part 1.3 CS điểm 1). Không sinh reason_codes/triggered_rules chính thức (đó là việc của
    `rule_engine.evaluate` với `FEVER_PROTOCOL.rule_catalog`)."""
    for key in EMERGENCY_TRI_STATE_FIELDS:
        if _is_true(answers.get(key)):
            return True
    for key, matches in _EMERGENCY_ENUM_MATCHES.items():
        if answers.get(key) in matches:
            return True
    age_months = age_in_months(answers)
    if age_months is not None and age_months < 3 and _is_true(answers.get("fever_reported")):
        return True  # RF-22: sốt ở trẻ < 3 tháng luôn EMERGENCY
    return False


def determine_route(answers: dict[str, object]) -> str:
    """CS §4.3. Thứ tự ưu tiên: infant > high_risk > dengue_context > localized_source > standard -
    route mạnh hơn không bao giờ bị route yếu hơn ghi đè, đúng tinh thần "không rule nào hạ mức"."""
    age_months = age_in_months(answers)
    if age_months is not None and age_months < 3:
        return "ROUTE_INFANT_HIGH"
    if _is_high_risk_tier(answers):
        return "ROUTE_HIGH_RISK"
    if _is_dengue_context(answers):
        return "ROUTE_DENGUE_CONTEXT"
    if _is_localized_source(answers):
        return "ROUTE_LOCALIZED_SOURCE"
    return "ROUTE_STANDARD"


def _is_high_risk_tier(answers: dict[str, object]) -> bool:
    if _is_true(answers.get("is_pregnant")) or _is_true(answers.get("postpartum_6w")):
        return True
    if _is_true(answers.get("immunocompromised")) or _is_true(answers.get("known_neutropenia")):
        return True
    if _is_true(answers.get("malaria_risk_area")):
        return True
    chronic = answers.get("chronic_conditions")
    if isinstance(chronic, (list, tuple)) and any(item not in ("none", "unknown") for item in chronic):
        return True
    age_months = age_in_months(answers)
    if age_months is not None and age_months >= 75 * 12:
        return True
    if _is_true(answers.get("lives_alone")) or answers.get("caregiver_available") == "false":
        return True
    return False


def _is_dengue_context(answers: dict[str, object]) -> bool:
    if _is_true(answers.get("mosquito_exposure")):
        return True
    outbreak = answers.get("outbreak_exposure")
    if isinstance(outbreak, (list, tuple)) and "dengue" in outbreak:
        return True
    if answers.get("abdominal_pain_severity") == "severe":
        return True
    if _is_true(answers.get("mucosal_bleeding")) or _is_true(answers.get("gi_bleeding")):
        return True
    if _is_true(answers.get("worse_after_defervescence")):
        return True
    if _is_true(answers.get("nsaid_use")):
        return True
    return False


def _is_localized_source(answers: dict[str, object]) -> bool:
    """Chỉ có ý nghĩa SAU Stage 3A sạch (CS §4.3) - caller đảm bảo không gọi sớm hơn."""
    localized_signals = (
        _is_true(answers.get("sore_throat")),
        _is_true(answers.get("ear_pain")),
        _is_true(answers.get("cough")),
        _is_true(answers.get("urinary_symptoms")),
        _is_true(answers.get("localized_infection_signs")),
    )
    return any(localized_signals) and not has_provisional_emergency_signal(answers)


def budget_key(answers: dict[str, object], route: str, known_triage_level: str | None = None) -> str:
    """Chọn đúng hàng ngân sách trong `BUDGET` theo route/kết luận hiện có (§6.5).

    `known_triage_level`: kết luận triage MỚI NHẤT do rule engine trả về, do caller (`session.py`)
    truyền vào - protocol không tự tính lại rule engine. Không truyền gì thì chỉ dựa vào provisional
    scan (chỉ bắt được EMERGENCY, không bắt được EARLY_VISIT sinh ra ở Stage 4 như RF-23)."""
    if route == "ROUTE_INFANT_HIGH" or has_provisional_emergency_signal(answers) or known_triage_level == "EMERGENCY":
        return "EMERGENCY"
    if route == "ROUTE_HIGH_RISK":
        return "ROUTE_HIGH_RISK"
    if route == "ROUTE_DENGUE_CONTEXT":
        return "ROUTE_DENGUE_CONTEXT"
    if known_triage_level == "EARLY_VISIT":
        return "EARLY_VISIT"
    return "SELF_CARE_CANDIDATE"


# ---------------------------------------------------------------------------------------------
# Skip condition riêng cho các cụm có "Ask condition" không đơn thuần là "luôn hỏi" (CS Part 3).
# Trả True => BỎ QUA cụm này dù còn field chưa điền. (Nhánh "Stage 3B chỉ chạy nếu 3A sạch" đã được
# engine chung xử lý qua `protocol.gate_stages`, không cần khai báo lại ở đây.)
# ---------------------------------------------------------------------------------------------


def _no_fever_confirmed(answers: dict[str, object]) -> bool:
    """Người bệnh đã xác nhận RÕ RÀNG là không sốt.

    Chỉ nhận giá trị xác định (`"false"` / `"none"`) - `"unknown"` KHÔNG được coi là không sốt, nếu
    không thì mọi cụm sốt bị skip ngay từ lượt đầu khi chưa hỏi gì."""
    return answers.get("fever_reported") == "false" or answers.get("fever_status") == "none"


def _skip_when_no_fever(answers: dict[str, object]) -> bool:
    """Đã xác nhận không sốt thì mọi cụm đặc điểm sốt đều vô nghĩa.

    Lỗi thật trong transcript `logs/fever/a421eb5f-...`: người dùng nói "à tôi nhầm, tôi không bị
    sốt" nhưng hệ thống vẫn hỏi hết Q2-01…Q2-05 ("sốt bao lâu rồi", "có rét run không", "đã uống hạ
    sốt chưa") vì không cụm nào trong Stage 2 có skip condition."""
    return _no_fever_confirmed(answers)


def _skip_q1_02(answers: dict[str, object]) -> bool:
    return _no_fever_confirmed(answers)


def _skip_q1_03(answers: dict[str, object]) -> bool:
    if _no_fever_confirmed(answers):
        return True
    return answers.get("fever_status") != "subjective"


def _skip_q2_05(answers: dict[str, object]) -> bool:
    if _no_fever_confirmed(answers):
        return True
    age_months = age_in_months(answers)
    young = age_months is not None and age_months < 3
    old = age_months is not None and age_months >= 65 * 12
    return not (young or old or _is_true(answers.get("immunocompromised")))


def _skip_q3_02(answers: dict[str, object]) -> bool:
    age_months = age_in_months(answers)
    return age_months is not None and age_months < 16 * 12


def _skip_q4_01(answers: dict[str, object]) -> bool:
    age_months = age_in_months(answers)
    if answers.get("sex") != "female" or age_months is None:
        return True
    age_years = age_months / 12.0
    return not (10 <= age_years <= 60)


def _skip_q4_01b(answers: dict[str, object]) -> bool:
    return not (_is_true(answers.get("is_pregnant")) or _is_true(answers.get("postpartum_6w")))


def _skip_q4_02(answers: dict[str, object]) -> bool:
    age_months = age_in_months(answers)
    if answers.get("sex") != "female" or age_months is None:
        return True
    age_years = age_months / 12.0
    if _is_true(answers.get("is_pregnant")):
        return True
    return not (15 <= age_years <= 55)


def _skip_q5_06(answers: dict[str, object]) -> bool:
    age_months = age_in_months(answers)
    return not (age_months is not None and age_months < 5 * 12)


_SKIP_RULES: dict[str, object] = {
    "Q1-02": _skip_q1_02,
    "Q1-03": _skip_q1_03,
    # Stage 2 (đặc điểm sốt) - toàn bộ cụm đều vô nghĩa khi đã xác nhận không sốt.
    "Q2-01": _skip_when_no_fever,
    "Q2-02": _skip_when_no_fever,
    "Q2-03": _skip_when_no_fever,
    "Q2-04": _skip_when_no_fever,
    "Q2-05": _skip_q2_05,
    "Q3-02": _skip_q3_02,
    "Q4-01": _skip_q4_01,
    "Q4-01b": _skip_q4_01b,
    "Q4-02": _skip_q4_02,
    "Q5-06": _skip_q5_06,
}


def skip_rule(cluster: QuestionCluster, answers: dict[str, object]) -> bool:
    rule = _SKIP_RULES.get(cluster.id)
    return bool(rule(answers)) if rule is not None else False


def self_care_checklist_satisfied(answers: dict[str, object]) -> bool:
    """KM §5.4 - checklist lâm sàng bắt buộc trước khi cho phép kết luận SELF_CARE (tuổi/tri
    giác/ăn uống/tiểu tiện/người theo dõi/khả năng tái khám). Hàm THUẦN theo giá trị field hiện có,
    không quan tâm đã "hỏi đủ cụm" chưa - đó là việc riêng của `stage_machine.should_stop`
    (SUFFICIENT_EVIDENCE chỉ xét ở stage cuối cùng, khi `next_cluster` đã trả `None` - tức toàn bộ
    stage trước đó chắc chắn đã đi qua tuần tự, nên không cần lặp lại kiểm tra "đã hỏi đủ chưa" ở
    đây). Tách 2 mối quan tâm này cho phép gọi hàm này ĐỘC LẬP để kiểm tra 1 bộ answers bất kỳ (vd
    test vàng Checkpoint 3 evaluate thẳng dữ liệu mẫu, không mô phỏng cả hội thoại)."""
    if has_provisional_emergency_signal(answers):
        return False
    age_months = age_in_months(answers)
    if age_months is None or age_months < 6:
        return False
    duration = _as_float(answers.get("fever_duration_days"))
    if duration is not None and duration >= 5:
        return False
    if answers.get("consciousness_level") != "alert":
        return False
    if answers.get("feeding_intake") not in ("normal", "reduced"):
        return False
    if answers.get("urine_output") != "normal":
        return False
    self_sufficient_adult = age_months >= 16 * 12 and answers.get("reporter_type") == "self"
    if not (_is_true(answers.get("caregiver_available")) or self_sufficient_adult):
        return False
    return bool(_is_true(answers.get("can_return_for_followup")))


# ---------------------------------------------------------------------------------------------
# Rule catalog - R-E-xx (EMERGENCY/now), R-V-xx (EARLY_VISIT), R-G-01 (KM §6.1)
# Mỗi hàm nhận (answers, matches_so_far) - đa số bỏ qua matches_so_far, chỉ R-E-21 dùng để biết đã có
# rule EMERGENCY nào khác khớp trước đó chưa (theo đúng thứ tự khai báo trong _RULE_CATALOG bên dưới).
# ---------------------------------------------------------------------------------------------


def _r_e_14(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    age_months = age_in_months(a)
    if age_months is not None and age_months < 3 and _fever_present(a):
        return RuleMatch("R-E-14", ("RF-22",), "EMERGENCY", "now")
    return None


def _r_e_16(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    temp = _as_float(a.get("temp_c"))
    if not (temp is not None and temp >= 40.0):
        return None
    heat_exposure = _is_true(a.get("heat_exposure_context"))
    if a.get("consciousness_level") not in ("alert", None) or heat_exposure:
        return RuleMatch("R-E-16", ("RF-25",), "EMERGENCY", "now")
    return None


def _r_e_17(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if _is_true(a.get("worse_after_defervescence")):
        return RuleMatch("R-E-17", ("RF-29",), "EMERGENCY", "now")
    return None


def _r_e_18(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    at_risk = _is_true(a.get("known_neutropenia")) or _array_has_any(a.get("immunocompromise_cause"), frozenset({"chemotherapy_6w"}))
    if not at_risk:
        return None
    temp = _as_float(a.get("temp_c"))
    threshold_met = temp is not None and temp >= 38.3
    if threshold_met or _is_true(a.get("fever_reported")):
        return RuleMatch("R-E-18", ("RF-30",), "EMERGENCY", "now")
    return None


def _r_e_19(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if not _is_true(a.get("malaria_risk_area")):
        return None
    within_month = _travel_within_months(a, 1)
    if within_month is None or within_month:
        return RuleMatch("R-E-19", ("RF-35",), "EMERGENCY", "now")
    return None


def _r_e_15(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    temp = _as_float(a.get("temp_c"))
    hypothermia = (temp is not None and temp < 36.0) or _is_true(a.get("hypothermia_reported"))
    if hypothermia and conservatism_tier(a) >= 1:
        return RuleMatch("R-E-15", ("RF-24",), "EMERGENCY", "now")
    return None


def _r_v_01(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    age_months = age_in_months(a)
    if age_months is None or not (3 <= age_months < 6):
        return None
    temp = _as_float(a.get("temp_c"))
    if temp is not None and temp >= 39.0:
        return RuleMatch("R-V-01", ("RF-23",), "EARLY_VISIT", "within_24h")
    return None


def _r_v_02(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    duration = _as_float(a.get("fever_duration_days"))
    if duration is not None and duration >= 5:
        return RuleMatch("R-V-02", ("RF-26",), "EARLY_VISIT", "within_24h")
    return None


def _r_v_03(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    duration = _as_float(a.get("fever_duration_days"))
    if duration is not None and duration >= 7:
        return RuleMatch("R-V-03", ("RF-27",), "EARLY_VISIT", "within_24h")
    return None


def _r_v_04(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if _is_true(a.get("rigors")):
        return RuleMatch("R-V-04", ("RF-28",), "EARLY_VISIT", "within_24h")
    return None


def _r_v_16(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    age_months = age_in_months(a)
    young = age_months is not None and age_months < 5 * 12
    has_clear_source = _is_true(a.get("localized_infection_signs")) or any(
        _is_true(a.get(key)) for key in ("sore_throat", "ear_pain", "cough")
    )
    if young and _fever_present(a) and not has_clear_source:
        return RuleMatch("R-V-16", ("RF-42",), "EARLY_VISIT", "within_24h")
    return None


def _r_v_20(a: dict[str, object], _matches: tuple[RuleMatch, ...]) -> RuleMatch | None:
    if not _is_true(a.get("malaria_risk_area")):
        return None
    within_month = _travel_within_months(a, 1)
    if within_month is False:
        return RuleMatch("R-V-20", ("RF-35",), "EARLY_VISIT", "within_24h")
    return None


_fallback_rule = common_rules.default_early_visit_rule


def _self_care_default_rule(_a: dict[str, object]) -> RuleMatch:
    return RuleMatch("R-S-01", (), "SELF_CARE", "monitor")


# Thứ tự khai báo QUAN TRỌNG: R-E-15 (hạ thân nhiệt) và R-E-21 (sản khoa) phải đứng SAU mọi rule
# R-E-xx khác trong cùng nhóm EMERGENCY, vì R-E-21 cần biết ĐÃ có rule EMERGENCY nào khác khớp chưa
# (đúng logic gốc trước khi tách generic engine).
#
# Danh sách viết THẲNG từng rule thay vì `*common_rules.EMERGENCY_RULES`: thứ tự ở đây đan xen rule
# phổ quát với rule đặc thù fever (R-E-14 sốt ở trẻ <3 tháng nằm giữa R-E-13 và R-E-16), nên nối khối
# sẽ làm sai thứ tự - và thứ tự là một phần của hợp đồng, không phải chi tiết trình bày.
RULE_CATALOG: tuple = (
    common_rules.r_e_01, common_rules.r_e_02, common_rules.r_e_03, common_rules.r_e_04,
    common_rules.r_e_05, common_rules.r_e_06, common_rules.r_e_07, common_rules.r_e_08,
    common_rules.r_e_09, common_rules.r_e_10, common_rules.r_e_11, common_rules.r_e_12,
    common_rules.r_e_13,
    _r_e_14, _r_e_16, _r_e_17, _r_e_18, _r_e_19,
    common_rules.r_e_20,
    _r_e_15, common_rules.r_e_21,
    _r_v_01, _r_v_02, _r_v_03, _r_v_04,
    common_rules.r_v_05, common_rules.r_v_06, common_rules.r_v_07, common_rules.r_v_08,
    common_rules.r_v_09, common_rules.r_v_10, common_rules.r_v_11, common_rules.r_v_12,
    common_rules.r_v_13, common_rules.r_v_14, common_rules.r_v_15,
    _r_v_16,
    common_rules.r_v_17, common_rules.r_v_18, common_rules.r_v_19,
    _r_v_20,
    common_rules.r_g_01,
)


# ---------------------------------------------------------------------------------------------
# Đính chính lời khai (`symptom_protocol/retraction.py`)
# ---------------------------------------------------------------------------------------------

# Field cha bị phủ định => field con mất ý nghĩa, phải xoá khỏi hồ sơ. Lỗi thật: sau khi người dùng
# nói "à tôi nhầm, tôi không bị sốt", phiếu bàn giao vẫn còn "39 độ, sốt 2 ngày".
FIELD_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "fever_reported": (
        "fever_status", "temp_c", "temp_site", "temp_measured_at", "temp_device_type",
        "fever_onset_at", "fever_duration_days", "rigors", "antipyretic_taken", "antipyretic_drug",
        "antipyretic_response", "worse_after_defervescence",
    ),
    "fever_status": (
        "temp_c", "temp_site", "temp_measured_at", "fever_onset_at", "fever_duration_days",
        "rigors", "antipyretic_taken", "antipyretic_drug", "antipyretic_response",
        "worse_after_defervescence",
    ),
    "antipyretic_taken": ("antipyretic_drug", "antipyretic_response", "worse_after_defervescence"),
    "is_pregnant": ("gestational_weeks", "obstetric_red_flags"),
    "immunocompromised": ("immunocompromise_cause", "known_neutropenia"),
    "recent_surgery_30d": ("surgical_site_signs",),
    # `non_blanching_rash` CỐ Ý không nằm dưới `rash_present`: nó là red flag M0 (RF-18) và "không có
    # ban" không làm nó VÔ NGHĨA - nó làm nó ÂM TÍNH, mà âm tính là dữ kiện phải giữ. Bản đầu có xếp
    # nó vào đây và đo được hậu quả khi chạy LLM thật: một câu "Không, không bị co giật" khiến model
    # tiện tay ghi `rash_present=false`, retraction xoá luôn `non_blanching_rash` đã xác nhận "false"
    # ở lượt trước về "unknown" -> checklist tự chăm sóc không bao giờ đủ và cụm ban bị hỏi lại. Nếu
    # hai field CHỌI nhau (không ban nhưng có ban không mất khi ấn kính) thì đó là việc của
    # `contradiction_rules` - hỏi lại, chứ không phải im lặng xoá một dấu hiệu đỏ.
    "rash_present": ("rash_type",),
}

# Ngưỡng "có sốt" theo nhiệt độ đo được (KM §2: >= 38.0°C là sốt). Dùng RIÊNG cho việc phát hiện mâu
# thuẫn, không phải để tự kết luận có sốt.
_FEVER_TEMP_THRESHOLD_C = 38.0


def _contradiction_no_fever_but_hot(answers: dict[str, object]) -> tuple[str, ...]:
    """Hồ sơ ghi "không sốt" nhưng người bệnh khai nhiệt độ từ 38°C trở lên.

    Vá nửa sau của bug C2: model hiểu nhầm "bé không sốt xuất huyết" thành `fever_status=none`, rồi
    dù người dùng nói rõ "39.2 độ, đo ở nách" ba lượt sau, hệ thống VẪN không sửa lại. `apply_retraction`
    không bắt được ca này vì nó chỉ so "dương -> âm", còn đây là "unknown -> âm" ngay lượt đầu.

    Không tự chọn bên nào đúng - trả về 2 field để engine mở lại cụm và hỏi cho rõ."""
    temp = _as_float(answers.get("temp_c"))
    if temp is None or temp < _FEVER_TEMP_THRESHOLD_C:
        return ()
    if answers.get("fever_reported") == "false" or answers.get("fever_status") == "none":
        return ("fever_reported", "fever_status", "temp_c")
    return ()


CONTRADICTION_RULES: tuple = (_contradiction_no_fever_but_hot,)


# ---------------------------------------------------------------------------------------------
# Sàng lọc theo nhóm cơ quan (`symptom_protocol/screening.py`)
# ---------------------------------------------------------------------------------------------
#
# Stage 3A đi tuần tự là 11 lượt, Stage 3B là 5 - kể cả với ca lành tính mà tất cả cùng ra âm tính,
# đúng nhóm ca ta muốn kết thúc sớm nhất (đo được: ca lành tính tốn 36 lượt khi chạy LLM thật).
# Gộp thành nhóm rút xuống 3 lượt cho 3A (Q3-01 + Q3-03 hỏi riêng + 1 câu sàng lọc) và 2 lượt cho 3B
# (1 câu sàng lọc + Q3-14).
#
# Nội dung nhóm nằm ở `common_safety` chứ không phải ở đây: chúng gộp các cụm dấu hiệu NGUY KỊCH phổ
# quát, không phải kiến thức về sốt (xem docstring `common_safety/screening_groups.py`).
# Stage 4 (quần thể nguy cơ) cũng cần nhóm: 10 cụm mà ca lành tính trả lời "không" cho gần hết, và
# `Q4-00` gộp sẵn KHÔNG đóng được `Q4-03`/`Q4-05` vì field con của chúng còn `unknown` - đo được đây
# là nút thắt lớn nhất còn lại sau khi 3A/3B đã được nén (~7-8 lượt cho một stage toàn câu trả lời
# "không").
SCREENING_GROUPS: tuple = (
    common_screening.emergency_scan_groups(GATE_STAGES[0])
    + common_screening.early_visit_scan_groups(GATE_STAGES[1])
    + common_screening.risk_context_groups("4")
)

# Xoá nhầm 2 field này là đắt nhất: chúng kéo theo TOÀN BỘ phần đặc điểm sốt (12 field) và làm câu
# chuyện lâm sàng đổi hẳn. Giữ đúng 2 field - mỗi field ở đây tốn của người bệnh một lượt xác nhận.
CONFIRM_BEFORE_RETRACT: frozenset[str] = frozenset({"fever_reported", "fever_status"})


FEVER_PROTOCOL = SymptomProtocol(
    name="fever",
    fields_by_key=FIELDS_BY_KEY,
    clusters=QUESTION_CLUSTERS,
    stage_order=STAGE_ORDER,
    gate_stages=GATE_STAGES,
    budget=BUDGET,
    budget_floor_stage=BUDGET_FLOOR_STAGE,
    determine_route=determine_route,
    budget_key=budget_key,
    provisional_emergency_signal=has_provisional_emergency_signal,
    self_care_checklist_satisfied=self_care_checklist_satisfied,
    skip_rule=skip_rule,
    rule_catalog=RULE_CATALOG,
    fallback_rule=_fallback_rule,
    self_care_default_rule=_self_care_default_rule,
    patient_red_flag_message=SUSPECTED_RED_FLAG_MESSAGE,
    safety_signal_fields=SAFETY_SIGNAL_FIELDS,
    opportunistic_keywords=OPPORTUNISTIC_KEYWORDS,
    screening_groups=SCREENING_GROUPS,
    field_dependencies=FIELD_DEPENDENCIES,
    contradiction_rules=CONTRADICTION_RULES,
    confirm_before_retract=CONFIRM_BEFORE_RETRACT,
    derive_fields=derive_duration,
    reason_code_labels=REASON_CODE_LABELS,
    # Protocol sốt biết trước than phiền là gì nên không có field `chief_complaint` để hỏi.
    default_chief_complaint="Sốt",
    onset_field="fever_onset_at",
    severity_field="temp_c",
)
