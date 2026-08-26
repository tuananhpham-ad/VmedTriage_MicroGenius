"""Field và cụm câu hỏi cho protocol khó thở (F09 §3.6.3)."""

from __future__ import annotations

from src.services.symptom_protocol.common_safety import clusters as common_clusters
from src.services.symptom_protocol.common_safety import fields as common_fields
from src.services.symptom_protocol.models import FieldSpec, QuestionCluster

BREATHING_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        "dyspnea_onset_mode", "Kiểu khởi phát khó thở", "M0",
        "sudden = đột ngột; gradual = từ từ",
        tri_state=False, allowed_values=("sudden", "gradual", "unknown"),
    ),
    FieldSpec("dyspnea_at_rest", "Khó thở khi nghỉ", "M0", "Khó thở ngay cả khi đang ngồi hoặc nằm nghỉ"),
    FieldSpec("leg_swelling", "Sưng chân mới xuất hiện", "M1", "Sưng một hoặc hai chân mới xuất hiện"),
    FieldSpec(
        "functional_impact", "Ảnh hưởng chức năng do khó thở", "M0",
        "none/mild/marked theo khả năng nói, đi lại và làm việc thường ngày",
        tri_state=False, allowed_values=("none", "mild", "marked", "unknown"),
    ),
)

BREATHING_ALL_FIELDS: tuple[FieldSpec, ...] = (
    common_fields.DEMOGRAPHIC_FIELDS
    + common_fields.SAFETY_NETTING_FIELDS
    + BREATHING_FIELDS
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

FIELDS_BY_KEY: dict[str, FieldSpec] = {field.key: field for field in BREATHING_ALL_FIELDS}

STAGE_ORDER: tuple[str, ...] = ("E", "0", "1", "2", "3", "4")
GATE_STAGES: tuple[str, ...] = ("E", "2", "3")
CRITICAL_SCAN_STAGE = "E"
EMERGENCY_SCAN_STAGE = "2"
EARLY_VISIT_SCAN_STAGE = "3"

QUESTION_CLUSTERS: tuple[QuestionCluster, ...] = (
    *common_clusters.critical_scan_clusters("E"),
    *common_clusters.demographic_clusters("0"),
    QuestionCluster(
        "BR-01", "1", ("dyspnea_onset_mode", "complaint_onset_at"),
        script_hint="Khó thở bắt đầu đột ngột hay từ từ, bắt đầu từ khi nào",
    ),
    QuestionCluster(
        "BR-02", "1", ("dyspnea_at_rest", "rapid_breathing"),
        script_hint="Có khó thở ngay cả khi ngồi hoặc nằm nghỉ không, có thở nhanh hơn bình thường không",
    ),
    common_clusters.chest_dyspnea_cluster("1", "BR-03"),
    *common_clusters.emergency_scan_clusters("2"),
    *common_clusters.early_visit_scan_clusters("3"),
    QuestionCluster(
        "BR-04", "4",
        ("functional_impact", "activity_vs_baseline", "leg_swelling", "fever_reported", "fever_status", "temp_c"),
        script_hint="Khó thở ảnh hưởng việc nói, đi lại hay sinh hoạt đến mức nào; có sưng chân hoặc sốt không",
    ),
    *common_clusters.risk_context_clusters("4"),
    *common_clusters.medication_clusters("4"),
    common_clusters.safety_netting_cluster("4"),
    common_clusters.closing_cluster("4", "BR-99"),
)

CLUSTERS_BY_ID: dict[str, QuestionCluster] = {cluster.id: cluster for cluster in QUESTION_CLUSTERS}
