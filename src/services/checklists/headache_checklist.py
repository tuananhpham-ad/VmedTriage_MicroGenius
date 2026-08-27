"""Field và cụm câu hỏi cho protocol đau đầu theo SNNOOP10 (F09 §3.6.4)."""

from __future__ import annotations

from src.services.symptom_protocol.common_safety import clusters as common_clusters
from src.services.symptom_protocol.common_safety import fields as common_fields
from src.services.symptom_protocol.models import FieldSpec, QuestionCluster

HEADACHE_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("thunderclap_onset", "Đau đầu đột ngột dữ dội", "M0", "Đạt mức dữ dội nhất trong vài giây hoặc vài phút"),
    FieldSpec(
        "headache_severity", "Mức độ đau đầu (0-10)", "M0",
        "Thang 0-10 theo cảm nhận người bệnh", tri_state=False,
    ),
    FieldSpec("headache_different_from_usual", "Đau đầu khác thường", "M0", "Khác rõ kiểu đau đầu thường gặp trước đây"),
    FieldSpec("headache_progressive", "Đau đầu tăng dần", "M0", "Mức độ hoặc tần suất tăng dần"),
    FieldSpec("headache_positional", "Đau đầu thay đổi theo tư thế", "M1", "Nặng hơn rõ khi đứng, nằm, ho hoặc rặn"),
    FieldSpec("visual_disturbance", "Rối loạn thị giác", "M0", "Mờ mắt, nhìn đôi hoặc mất thị lực mới xuất hiện"),
    FieldSpec("head_trauma_recent", "Chấn thương đầu gần đây", "M0", "Va đập hoặc chấn thương đầu gần đây"),
)

HEADACHE_ALL_FIELDS: tuple[FieldSpec, ...] = (
    common_fields.DEMOGRAPHIC_FIELDS
    + common_fields.SAFETY_NETTING_FIELDS
    + HEADACHE_FIELDS
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

FIELDS_BY_KEY: dict[str, FieldSpec] = {field.key: field for field in HEADACHE_ALL_FIELDS}

STAGE_ORDER: tuple[str, ...] = ("E", "0", "1", "2", "3", "4")
GATE_STAGES: tuple[str, ...] = ("E", "2", "3")
CRITICAL_SCAN_STAGE = "E"
EMERGENCY_SCAN_STAGE = "2"
EARLY_VISIT_SCAN_STAGE = "3"

QUESTION_CLUSTERS: tuple[QuestionCluster, ...] = (
    *common_clusters.critical_scan_clusters("E"),
    QuestionCluster(
        "HA-01", "E", ("thunderclap_onset",),
        script_hint="Cơn đau đầu có đến đột ngột và đạt mức dữ dội nhất chỉ trong vài giây hoặc vài phút không",
    ),
    *common_clusters.demographic_clusters("0"),
    QuestionCluster(
        "HA-02", "1",
        ("focal_neuro_deficit", "new_confusion", "seizure_occurred", "neck_stiffness", "fever_reported", "fever_status", "temp_c"),
        script_hint="Có yếu tay chân, méo miệng, nói khó, lú lẫn, co giật, cứng gáy hoặc sốt không",
    ),
    QuestionCluster(
        "HA-03", "1", ("headache_different_from_usual", "headache_progressive", "headache_severity", "age_value"),
        script_hint="Mức đau từ 0 đến 10 là bao nhiêu, có khác thường hoặc tăng dần so với trước không",
    ),
    QuestionCluster(
        "HA-04", "1", ("headache_positional", "visual_disturbance"),
        script_hint="Cơn đau có đổi rõ theo tư thế, khi ho/rặn, hoặc kèm mờ mắt, nhìn đôi, mất thị lực không",
    ),
    *common_clusters.emergency_scan_clusters("2"),
    *common_clusters.early_visit_scan_clusters("3"),
    QuestionCluster(
        "HA-05", "4", ("is_pregnant", "immunocompromised", "chronic_conditions", "head_trauma_recent"),
        script_hint="Có đang mang thai, suy giảm miễn dịch, bệnh nền đáng kể hoặc mới chấn thương đầu không",
    ),
    *common_clusters.risk_context_clusters("4"),
    *common_clusters.medication_clusters("4"),
    common_clusters.safety_netting_cluster("4"),
    common_clusters.closing_cluster("4", "HA-99"),
)

CLUSTERS_BY_ID: dict[str, QuestionCluster] = {cluster.id: cluster for cluster in QUESTION_CLUSTERS}
