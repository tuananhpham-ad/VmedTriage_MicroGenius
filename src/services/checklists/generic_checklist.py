"""Field + cụm câu hỏi cho protocol GENERIC - than phiền chưa có protocol chuyên biệt.

Hợp đồng của protocol này HẸP và phải giữ cho hẹp:

> Thu thập thông tin ban đầu, quét tập dấu hiệu nguy hiểm phổ quát ĐÃ ĐƯỢC PHÊ DUYỆT, rồi tạo phiếu
> bàn giao điều dưỡng. KHÔNG chẩn đoán, KHÔNG tự kết luận an toàn, và KHÔNG tuyên bố đã bao phủ đầy
> đủ nguy cơ của than phiền đó.

Vì sao cần: sau khi `/chat` chuyển sang agent fever, người nhắn "tôi đau ngực từ sáng, đi vài bước là
hụt hơi" bị hỏi "bé hay người lớn, bao nhiêu tuổi" và KHÔNG luật đỏ nào quét - pipeline cũ
(`RED_FLAG_RULES` trong `src/config.py`) từng bắt ca đó ngay lượt đầu. Đây là lỗ hổng an toàn có thật,
đã được ghi lại bằng test trước khi vá.

Phần lớn nội dung file này là ĐI MƯỢN `common_safety/` - chỉ 6 field và 2 cụm là thật sự mới, phần mô
tả than phiền. Đó chính là dấu hiệu việc tách `common_safety` đã đúng chỗ.
"""

from __future__ import annotations

from src.services.symptom_protocol.common_safety import clusters as common_clusters
from src.services.symptom_protocol.common_safety import fields as common_fields
from src.services.symptom_protocol.models import FieldSpec, QuestionCluster

# --- Field mô tả than phiền (phần DUY NHẤT không dùng chung được) --------------------------------
COMPLAINT_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("chief_complaint", "Triệu chứng chính", "M0", "Người bệnh tự mô tả điều khó chịu nhất, giữ NGUYÊN VĂN lời họ - không quy về tên bệnh", tri_state=False),
    FieldSpec("complaint_site", "Vị trí/bộ phận khó chịu", "M1", "Ngực, bụng, đầu, lưng, tay chân... theo lời người bệnh", tri_state=False),
    FieldSpec("complaint_onset_at", "Thời điểm bắt đầu", "M0", "YYYY-MM-DD; quy đổi từ 'hôm qua', '3 ngày nay' theo ngày hiện tại", tri_state=False),
    FieldSpec("complaint_duration_days", "Số ngày đã kéo dài", "M1", "Tính TỰ ĐỘNG từ complaint_onset_at - không hỏi trực tiếp", tri_state=False),
    FieldSpec("complaint_severity", "Mức khó chịu (0-10)", "M1", "Thang 0-10 theo cảm nhận người bệnh", tri_state=False),
    FieldSpec("complaint_progression", "Diễn tiến", "M1", "better/same/worse - đang đỡ dần, như cũ, hay nặng lên", tri_state=False, allowed_values=("better", "same", "worse", "unknown",)),
)

GENERIC_FIELDS: tuple[FieldSpec, ...] = (
    common_fields.DEMOGRAPHIC_FIELDS
    + common_fields.SAFETY_NETTING_FIELDS
    + COMPLAINT_FIELDS
    + common_fields.GENERAL_FIELDS
    + common_fields.RESPIRATORY_FIELDS
    + common_fields.CIRCULATION_FIELDS
    + common_fields.NEUROLOGICAL_FIELDS
    + common_fields.SKIN_BLEEDING_FIELDS
    + common_fields.ASSOCIATED_FIELDS
    + common_fields.RISK_CONTEXT_FIELDS
    + common_fields.MEDICATION_FIELDS
)

FIELDS_BY_KEY: dict[str, FieldSpec] = {field.key: field for field in GENERIC_FIELDS}


# --- Stage ---------------------------------------------------------------------------------------
#
# Giữ ĐÚNG hình dạng của fever (nhân khẩu -> mô tả than phiền -> quét đỏ -> quét khám sớm -> nguy cơ)
# để `stage_machine` chạy y nguyên: hai stage quét đỏ/khám sớm phải TÁCH RỜI thì cơ chế "chỉ quét
# early-visit khi emergency-scan đã sạch" (`_cluster_is_skipped`) mới có chỗ bám. Bảng trong
# `agent_conversation_policy.md` §3.4 gộp chúng vào một stage - làm vậy sẽ mất cơ chế đó.
STAGE_ORDER: tuple[str, ...] = ("0", "1", "2", "3", "4")
GATE_STAGES: tuple[str, str] = ("2", "3")

QUESTION_CLUSTERS: tuple[QuestionCluster, ...] = (
    # --- Stage 0 — ai đang cần tư vấn ---
    *common_clusters.demographic_clusters("0"),
    # --- Stage 1 — than phiền là gì ---
    QuestionCluster("G1-01", "1", ("chief_complaint", "complaint_site", "complaint_onset_at"), script_hint="Điều khó chịu nhất hiện giờ là gì, ở vùng nào, bắt đầu từ khi nào"),
    QuestionCluster("G1-02", "1", ("complaint_severity", "complaint_progression"), script_hint="Trên thang 0-10 khó chịu mức nào, mấy hôm nay đang đỡ dần, như cũ hay nặng lên"),
    # --- Stage 2 — quét dấu hiệu đỏ phổ quát ---
    *common_clusters.emergency_scan_clusters("2"),
    # --- Stage 3 — quét dấu hiệu cần khám sớm ---
    *common_clusters.early_visit_scan_clusters("3"),
    # `diarrhea` là tier M1 (mất nước, nguồn nhiễm) nhưng TRƯỚC 2026-08-19 không cụm nào của generic
    # hỏi tới nó - không đường nào thu thập được, nên `mandatory_unasked` khác 0 ở MỌI phiên generic
    # (đo được: 9/10 phiên trong log ngày 17/08 đều thiếu đúng field này).
    #
    # Cụm RIÊNG của generic chứ không thêm vào `common_clusters`: fever đã hỏi tiêu chảy ở Q5-04 với
    # ngữ cảnh khác (nguồn nhiễm của một ca đang sốt), và nhét vào cụm dùng chung sẽ làm fever hỏi
    # trùng hai lần ở hai stage.
    QuestionCluster("G3-01", "3", ("diarrhea",), script_hint="Mấy hôm nay có đi ngoài phân lỏng nhiều lần không"),
    # --- Stage 4 — bối cảnh nguy cơ + thuốc + an toàn tại nhà ---
    *common_clusters.risk_context_clusters("4"),
    *common_clusters.medication_clusters("4"),
    common_clusters.safety_netting_cluster("4"),
)

CLUSTERS_BY_ID: dict[str, QuestionCluster] = {cluster.id: cluster for cluster in QUESTION_CLUSTERS}
