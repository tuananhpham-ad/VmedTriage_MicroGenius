"""Field và cụm câu hỏi cho protocol đau bụng (F09 §3.6.2)."""

from __future__ import annotations

from src.services.symptom_protocol.common_safety import clusters as common_clusters
from src.services.symptom_protocol.common_safety import fields as common_fields
from src.services.symptom_protocol.models import FieldSpec, QuestionCluster

ABDOMINAL_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        "abdominal_pain_radiation", "Hướng lan của đau bụng", "M0",
        "Đau có lan lên ngực, ra lưng hay không",
        tri_state=False, allowed_values=("chest", "back", "none", "unknown"),
    ),
    FieldSpec(
        "abdominal_pain_onset_mode", "Kiểu khởi phát đau bụng", "M0",
        "sudden = đột ngột; gradual = từ từ",
        tri_state=False, allowed_values=("sudden", "gradual", "unknown"),
    ),
    FieldSpec(
        "abdominal_pain_pattern", "Kiểu diễn tiến đau bụng", "M0",
        "continuous = liên tục; intermittent = từng cơn",
        tri_state=False, allowed_values=("continuous", "intermittent", "unknown"),
    ),
    FieldSpec(
        "abdominal_pain_duration_hours", "Thời gian đau bụng (giờ)", "M0",
        "Số giờ đau; ngưỡng quyết định gồm đau nặng >1 giờ và đau vừa liên tục >2 giờ",
        tri_state=False,
    ),
    FieldSpec("urinary_retention_gt_4h", "Bí tiểu trên 4 giờ", "M0", "Không thể đi tiểu trong hơn 4 giờ"),
    FieldSpec("abdominal_distension", "Chướng bụng", "M1", "Bụng chướng hoặc căng lên bất thường"),
)

ABDOMINAL_ALL_FIELDS: tuple[FieldSpec, ...] = (
    common_fields.DEMOGRAPHIC_FIELDS
    + common_fields.SAFETY_NETTING_FIELDS
    + ABDOMINAL_FIELDS
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

FIELDS_BY_KEY: dict[str, FieldSpec] = {field.key: field for field in ABDOMINAL_ALL_FIELDS}

STAGE_ORDER: tuple[str, ...] = ("E", "0", "1", "2", "3", "4")
GATE_STAGES: tuple[str, ...] = ("E", "2", "3")
CRITICAL_SCAN_STAGE = "E"
EMERGENCY_SCAN_STAGE = "2"
EARLY_VISIT_SCAN_STAGE = "3"

QUESTION_CLUSTERS: tuple[QuestionCluster, ...] = (
    *common_clusters.critical_scan_clusters("E"),
    *common_clusters.demographic_clusters("0"),
    QuestionCluster(
        "AB-01", "1",
        ("abdominal_pain_location", "abdominal_pain_severity", "abdominal_pain_radiation"),
        script_hint="Đau ở vùng nào, mức độ nhẹ/vừa/dữ dội, có lan lên ngực hoặc ra lưng không",
    ),
    QuestionCluster(
        "AB-02", "1",
        ("complaint_onset_at", "abdominal_pain_onset_mode", "abdominal_pain_pattern", "abdominal_pain_duration_hours"),
        script_hint="Đau bắt đầu đột ngột hay từ từ, liên tục hay từng cơn, đã kéo dài bao nhiêu giờ",
    ),
    QuestionCluster(
        "AB-03", "1", ("gi_bleeding", "urinary_retention_gt_4h"),
        script_hint="Có nôn ra máu, đi ngoài phân đen, hoặc hơn 4 giờ không thể đi tiểu không",
    ),
    *common_clusters.emergency_scan_clusters("2"),
    *common_clusters.early_visit_scan_clusters("3"),
    QuestionCluster(
        "AB-04", "4",
        ("fever_reported", "fever_status", "temp_c", "jaundice_new", "abdominal_distension", "age_value"),
        script_hint="Có đo sốt không, có vàng da mới hoặc bụng chướng căng lên không",
    ),
    *common_clusters.risk_context_clusters("4"),
    *common_clusters.medication_clusters("4"),
    common_clusters.safety_netting_cluster("4"),
    common_clusters.closing_cluster("4", "AB-99"),
)

CLUSTERS_BY_ID: dict[str, QuestionCluster] = {cluster.id: cluster for cluster in QUESTION_CLUSTERS}
