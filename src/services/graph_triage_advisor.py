"""GNN Advisory Signal - #TODO, KHÔNG được wire vào TriagePipeline bởi ai khác ngoài chủ sở hữu module.

Bối cảnh (xem _guidance/vmedtriage_solution_design_review.md mục 9.4 để biết đầy đủ lý do thiết kế):

- Ý tưởng gốc: dual embedding (text summary + conversation/checklist graph) -> GNN -> distribution
  3 mức ưu tiên (Cấp cứu / Khám sớm / Tự theo dõi), lấy argmax gửi thẳng cho điều dưỡng.
- Bị bẻ lại vì vi phạm nguyên tắc cốt lõi trong _guidance/vmedtriage_solution_design_review.md mục 2:
  "Quyết định triage nên được sinh bởi engine có kiểm soát" - GNN là black-box, không tra bảng phân
  độ, không grounded, không giải thích được theo protocol/guideline -> vi phạm "chống bịa" (mục 3.4).
- Dataset hiện có (5 CSV trong data/triage_*.csv, ~609 dòng) là NHÃN TỰ SINH (silver-label), không
  phải bác sĩ gán, lệch nhãn nặng theo từng nhóm triệu chứng (đã phân tích: cùng slug
  'shortness_of_breath' xuất hiện ở cả 3 mức nhãn) -> KHÔNG đủ tin cậy để train một classifier tự
  quyết định mức triage cho một hệ thống y tế.

Vai trò được CHO PHÉP của module này khi triển khai (việc của người phụ trách phần GNN, tách riêng
khỏi TriagePipeline chính):

1. CHỈ được trả về evidence phụ mang tính tham khảo - ví dụ "N case tương tự đã approved trước đây,
   phân bố mức ưu tiên của các case đó" - KHÔNG được trả thẳng một priority để hệ thống tự dùng.
2. Explainability là điều kiện bắt buộc trước khi bật hiển thị cho điều dưỡng: mỗi gợi ý phải kèm
   được (a) danh sách case tương tự cụ thể (không phải % vô danh), (b) field/node nào trong graph
   đóng góp nhiều nhất vào độ tương đồng. Nếu chưa làm được (b) thì KHÔNG hiển thị cho nurse, chỉ
   chạy shadow-mode (log để đánh giá offline).
3. `ProtocolTriageEngine` (src/services/triage_engine.py) và `RedFlagSafetyLayer`
   (src/services/red_flag.py) vẫn PHẢI là nguồn quyết định priority duy nhất. Output của module này
   không bao giờ được gán vào `TriageProposal.priority` hay override `RedFlagFinding`.
4. Bắt buộc feature-flag tắt theo mặc định (xem `Settings.enable_graph_triage_advisor` - #TODO thêm
   vào src/config.py khi bắt đầu implement) và chạy shadow-mode trước khi bật hiển thị thật.

#TODO (người phụ trách phần GNN implement, KHÔNG phải phạm vi của luồng triage chính):
    - [ ] Thiết kế node/edge schema cho conversation graph theo từng checklist bệnh
          (src/config.py:REQUIRED_FIELDS_BY_SYMPTOM_GROUP là điểm bắt đầu tự nhiên).
    - [ ] Dual embedding: v1 = text-embed(summary) dùng lại bkai-foundation-models/vietnamese-bi-encoder
          đã cấu hình sẵn trong src/pipeline/weaviate_cloud.py; v2 = graph-embed (GNN encoder, cần chọn
          kiến trúc - chưa quyết định trong repo này).
    - [ ] Ingest + dedupe 609 dòng trong data/triage_*.csv (đã phát hiện 40 câu trùng lặp và vài lỗi
          slug chính tả "dau-dau") thành corpus case tương tự trong Weaviate (không dùng làm nhãn
          huấn luyện classifier tự quyết - chỉ dùng cho similarity search).
    - [ ] Cơ chế feedback/calibration offline đọc audit_log (approval_store.AuditLogEntry, action=
          "approve"/"override"/"reject") để đánh giá độ hữu ích của gợi ý theo thời gian; loại trừ
          action="reject" với reason bắt đầu bằng RejectReasonCode.ALREADY_HANDLED_OFFLINE/OTHER khỏi
          mọi phép đo độ chính xác (không phải tín hiệu AI đúng/sai).
    - [ ] Explainability UI cho nurse (mục 2 ở trên) trước khi tắt shadow-mode.

Class dưới đây chỉ là điểm neo (anchor) cho interface tương lai - KHÔNG có logic thật, KHÔNG được
gọi ở bất kỳ đâu trong TriagePipeline/case_flow/case_approval hiện tại.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.models.schemas import TriageCase


@dataclass(slots=True)
class SimilarCaseEvidence:
    """Một case tương tự đã được điều dưỡng duyệt trước đây - dùng làm evidence tham khảo, KHÔNG
    phải kết luận. `case_id` phải trỏ tới case đã ẩn danh nếu dùng để hiển thị cho nurse khác."""

    case_id: str
    similarity_score: float
    approved_priority: str
    contributing_fields: list[str]


class GraphTriageAdvisor:
    """#TODO - chưa implement. Không gọi class này ở bất kỳ pipeline nào cho tới khi có explainability
    (xem docstring module) và feature flag bật tường minh."""

    def advise(self, triage_case: TriageCase) -> list[SimilarCaseEvidence]:
        raise NotImplementedError(
            "GraphTriageAdvisor chưa được implement - xem #TODO trong "
            "src/services/graph_triage_advisor.py. Không dùng module này trong luồng quyết định "
            "triage chính (ProtocolTriageEngine/RedFlagSafetyLayer vẫn là nguồn quyết định duy nhất)."
        )
