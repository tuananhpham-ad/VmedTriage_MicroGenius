"""Field + cụm câu hỏi cho protocol ĐAU NGỰC (F09 §3.6.1).

Nguồn lâm sàng: **Schmitt-Thompson Telephone Triage Protocols — Chest Pain, Adult (2015)**, bổ sung
danh mục discriminator của The Sullivan Group. Mục tiêu bộ câu hỏi: loại trừ hội chứng vành cấp,
thuyên tắc phổi, bóc tách động mạch chủ — KHÔNG phải chẩn đoán chúng.

Theo khuôn **fever**, không phải generic: nhóm triệu chứng ĐÃ LÀ than phiền chính, nên protocol không
hỏi `chief_complaint` mà khai `default_chief_complaint="Đau ngực"`, và `onset_field`/`severity_field`
trỏ vào field riêng của nhóm. Generic phải hỏi `chief_complaint` vì nó không biết trước than phiền là
gì — đây là khác biệt về hoàn cảnh, không phải về phong cách.

**Câu 1 của tài liệu KHÔNG có cụm riêng ở đây.** *"Khó thở nặng đến mức không nói được hết câu, không
còn tỉnh táo"* đã là `Q3-06` (`breathing_difficulty`) + `Q3-01` (`consciousness_level`) trong
`common_clusters`, hỏi ở stage `E` trước cả tuổi/giới. Viết lại thành cụm riêng là dựng bản sao thứ
hai của cùng một dấu hiệu; hai bản sẽ lệch nhau ngay lần đầu ai đó sửa một bên.

**`CP-03` mượn `chest_dyspnea_cluster`** — cụm dùng chung với protocol khó thở. Xem docstring của nó:
đây là cặp phủ chéo duy nhất giữa 4 nhóm, và cả hai bảng mapping đều chốt cấp cứu trên cùng tổ hợp.
"""

from __future__ import annotations

from src.services.symptom_protocol.common_safety import clusters as common_clusters
from src.services.symptom_protocol.common_safety import fields as common_fields
from src.services.symptom_protocol.models import FieldSpec, QuestionCluster

# --- Field đặc thù đau ngực (phần DUY NHẤT không dùng chung được) ---------------------------------
CHEST_PAIN_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        "chest_pain_character", "Tính chất cơn đau ngực", "M0",
        "Đè ép/bóp nghẹt/nặng ngực (pressure|crushing|tightness) là discriminator hội chứng vành cấp; đau nhói như dao đâm (sharp) thì khác hẳn",
        tri_state=False,
        allowed_values=("pressure", "crushing", "tightness", "sharp", "burning", "other", "unknown"),
    ),
    FieldSpec(
        "chest_pain_radiation", "Hướng lan của cơn đau", "M0",
        "Lan ra vai/cánh tay/hàm là discriminator kinh điển hội chứng vành cấp; lan ra lưng gợi ý bóc tách động mạch chủ",
        tri_state=False,
        allowed_values=("shoulder", "arm", "jaw", "back", "none", "unknown"),
    ),
    FieldSpec(
        "chest_pain_location", "Vị trí đau ngực", "M1",
        "Giữa ngực/sau xương ức/bên trái/bên phải - theo lời người bệnh, không quy về tên bệnh",
        tri_state=False,
    ),
    FieldSpec(
        "chest_pain_onset_at", "Thời điểm bắt đầu đau", "M0",
        "YYYY-MM-DD hoặc mô tả giờ; quy đổi 'từ sáng', 'hôm qua' theo ngày hiện tại",
        tri_state=False,
    ),
    FieldSpec(
        "chest_pain_duration_min", "Thời gian mỗi cơn đau (phút)", "M0",
        "NGƯỠNG QUYẾT ĐỊNH CHÍNH của protocol gốc: >5 phút. Quy đổi 'nửa tiếng' -> 30, 'vài giây' -> 0.5",
        tri_state=False,
    ),
    FieldSpec(
        "chest_pain_pattern", "Kiểu đau", "M0",
        "continuous = liên tục không dứt; intermittent = từng cơn rồi hết hẳn",
        tri_state=False,
        allowed_values=("continuous", "intermittent", "unknown"),
    ),
    FieldSpec(
        "chest_pain_severity", "Mức đau ngực (0-10)", "M1",
        "Thang 0-10 theo cảm nhận người bệnh",
        tri_state=False,
    ),
    FieldSpec(
        "chest_pain_worsening", "Cơn đau đang nặng lên / dày hơn", "M1",
        "Đau từng cơn nhưng tăng dần mức độ hoặc tần suất - tiêu chí 'Cần khám sớm' của protocol gốc",
    ),
    FieldSpec("diaphoresis", "Vã mồ hôi lạnh", "M0", "Diaphoresis kèm đau ngực - dấu hiệu hội chứng vành cấp"),
    FieldSpec("palpitations", "Tim đập nhanh / không đều", "M0", "Rối loạn nhịp kèm đau ngực - tiêu chí Cấp cứu"),
    FieldSpec(
        "immobility_or_long_travel", "Nằm bất động lâu / đi máy bay chặng dài gần đây", "M1",
        "Yếu tố nguy cơ thuyên tắc huyết khối tĩnh mạch (VTE), đi cùng recent_surgery_30d",
    ),
    FieldSpec(
        "cardiac_risk_factors", "Yếu tố nguy cơ tim mạch", "M1",
        "Cao huyết áp, tiểu đường, mỡ máu cao, hút thuốc, tiền sử bệnh tim. Ghi những cái người bệnh NÓI RÕ - KHÔNG suy từ tuổi hay từ tên bệnh khác",
        tri_state=False,
    ),
)

CHEST_PAIN_ALL_FIELDS: tuple[FieldSpec, ...] = (
    common_fields.DEMOGRAPHIC_FIELDS
    + common_fields.SAFETY_NETTING_FIELDS
    + CHEST_PAIN_FIELDS
    + common_fields.FEVER_SIGNAL_FIELDS
    + common_fields.GENERAL_FIELDS
    + common_fields.RESPIRATORY_FIELDS
    + common_fields.CIRCULATION_FIELDS
    + common_fields.NEUROLOGICAL_FIELDS
    + common_fields.SKIN_BLEEDING_FIELDS
    + tuple(field for field in common_fields.ASSOCIATED_FIELDS if field.key != "diarrhea")
    + common_fields.RISK_CONTEXT_FIELDS
    + common_fields.MEDICATION_FIELDS
    + common_fields.CLOSING_FIELDS
)
"""`FEVER_SIGNAL_FIELDS` có mặt vì bảng mapping đau ngực chốt "khám sớm" khi *sốt >38.1°C kèm đau
ngực* - không có `temp_c` thì dòng đó không bao giờ khớp. Nó cũng là `SWITCH_DETECTION_FIELDS`, tức
chỗ để ghi khi người bệnh khai sốt giữa phiên."""

FIELDS_BY_KEY: dict[str, FieldSpec] = {field.key: field for field in CHEST_PAIN_ALL_FIELDS}


# --- Stage: pipeline 5 bước của F09 §3.2 ---------------------------------------------------------
STAGE_ORDER: tuple[str, ...] = ("E", "0", "1", "2", "3", "4")
GATE_STAGES: tuple[str, ...] = ("E", "2", "3")
CRITICAL_SCAN_STAGE = "E"
EMERGENCY_SCAN_STAGE = "2"
EARLY_VISIT_SCAN_STAGE = "3"

QUESTION_CLUSTERS: tuple[QuestionCluster, ...] = (
    # --- Bước 1: KIỂM TRA CẤP CỨU (đã chứa câu 1 của tài liệu) ---
    *common_clusters.critical_scan_clusters("E"),
    # --- Bước 2: LẤY HỒ SƠ ---
    *common_clusters.demographic_clusters("0"),
    # --- Bước 3-4: LẤY TRIỆU CHỨNG — 3 cụm đặc thù (câu 2, 3, 5 của tài liệu) ---
    QuestionCluster(
        "CP-01", "1",
        ("chest_pain", "chest_pain_character", "chest_pain_radiation", "chest_pain_location"),
        script_hint="Cơn đau ở vị trí nào, có cảm giác đè ép/bóp nghẹt/nặng ngực không, có lan ra vai, cánh tay hoặc hàm không",
    ),
    QuestionCluster(
        "CP-02", "1",
        ("chest_pain_onset_at", "chest_pain_duration_min", "chest_pain_pattern", "chest_pain_severity", "chest_pain_worsening"),
        script_hint="Cơn đau bắt đầu từ khi nào, kéo dài liên tục hay từng cơn, mỗi lần đã hơn 5 phút chưa",
    ),
    common_clusters.chest_dyspnea_cluster("1", "CP-03"),
    # --- Quét đỏ phổ quát + quét khám sớm (nén bằng screening group) ---
    *common_clusters.emergency_scan_clusters("2"),
    *common_clusters.early_visit_scan_clusters("3"),
    # --- Bước 5: QUÉT RỦI RO / TIỀN SỬ — 2 cụm đặc thù (câu 4 + nhánh VTE của câu 5) ---
    QuestionCluster(
        "CP-04", "4", ("recent_surgery_30d", "immobility_or_long_travel"),
        script_hint="Gần đây có phẫu thuật, nằm bất động lâu ngày, hoặc đi máy bay chặng dài không",
    ),
    QuestionCluster(
        "CP-05", "4",
        ("cardiac_risk_factors", "chronic_conditions", "fever_reported", "fever_status", "temp_c"),
        script_hint="Có cao huyết áp, tiểu đường, mỡ máu cao, hút thuốc, tiền sử bệnh tim hoặc sốt không; nếu có sốt thì bao nhiêu độ",
    ),
    *common_clusters.risk_context_clusters("4"),
    *common_clusters.medication_clusters("4"),
    common_clusters.safety_netting_cluster("4"),
    common_clusters.closing_cluster("4", "CP-99"),
)

CLUSTERS_BY_ID: dict[str, QuestionCluster] = {cluster.id: cluster for cluster in QUESTION_CLUSTERS}
