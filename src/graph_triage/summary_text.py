"""Phiếu tóm tắt của một `TriageCase` -> đoạn text tiếng Việt để đưa sang agent quyết định.

VÌ SAO CẦN LỚP NÀY: `LogRegPredictor`/`BertPredictor` nhận một chuỗi text, còn P-141 giữ phiếu bàn
giao ở dạng có cấu trúc (`HandoffSummary` + `TriageCase.summary_fields`). Đây là chỗ duy nhất dịch
giữa hai dạng đó.

HAI ĐIỀU KHÔNG ĐƯỢC PHÁ:

1. Dựng theo `summary_fields`, KHÔNG phải `structured_data.fields`. `summary_fields` đã mang nhãn
   tiếng Việt do protocol cấp (`symptom_case_bridge._summary_fields`); `structured_data.fields` có
   khoá là field key thô (`fever_onset_at`, `urine_output`) - đưa vào text thì cả hai model text lẫn
   bước trích xuất graph đều đọc phải chuỗi không có nghĩa tiếng Việt.

2. BỎ HẲN dòng `is_missing=True`. Trường chưa hỏi tới mà vẫn xuất hiện trong text là mời bước trích
   xuất graph biến "chưa hỏi" thành phủ định tường minh (`status="absent"`), trong khi hợp đồng
   `patient_graph_v1` quy định UNKNOWN phải là BỎ node đi. Lọc ở đây, deterministic, trước khi có bất
   kỳ lời gọi LLM nào.

Hàm này là hàm THUẦN: không gọi LLM, không đọc store, không đọc thời gian.

ĐÃ ĐO - LỆCH PHÂN PHỐI SO VỚI LÚC TRAIN (2026-08-15, 200 ca từ golden.csv, seed 42):

LogReg và PhoBERT được train trên cột `patient` của golden.csv - lời kể tự sự của người bệnh, trung
bình 377 ký tự. Phiếu tóm tắt là template gạch đầu dòng. Giữ NGUYÊN nội dung lâm sàng và chỉ đổi vỏ
sang template, LogReg đã cho:

    accuracy            0.950 -> 0.790
    recall 'cap_cuu'    0.946 -> 0.784   (12/70 ca cấp cứu bị tụt hạng)
    đổi nhãn            36/200 = 18%

Đây là CẬN DƯỚI của mức lệch: phiếu tóm tắt thật còn mất chi tiết và đổi từ ngữ so với lời kể gốc.
Lời kể gốc (`session.conversation`, các lượt `role="user"`) khớp phân phối train hơn hẳn và cũng cho
`source_span` provenance thật thay vì span cắt từ template.

Dùng phiếu tóm tắt là quyết định có chủ đích của chủ dự án, không phải sơ suất. Ghi lại đây để người
sau không phải đo lại; nếu muốn đổi sang lời kể gốc thì chỉ cần đổi nguồn text trong
`service.decide_for_case`. Lưới an toàn vẫn còn nguyên: hai model bất đồng thì `llm_decision` bắt
buộc `requires_human_review=True`, và mức ưu tiên có hiệu lực vẫn do rule engine quyết.
"""

from __future__ import annotations

from src.models.schemas import TriageCase

_HEADER = "Tóm tắt tình trạng bệnh"


def _clean(value: object) -> str:
    return " ".join(str(value).split())


def build_summary_text(triage_case: TriageCase) -> str:
    """Trả về phiếu tóm tắt dạng text. Chuỗi rỗng nghĩa là chưa có gì đáng gửi đi."""
    summary = triage_case.summary
    lines: list[str] = []

    chief_complaint = _clean(summary.chief_complaint) if summary and summary.chief_complaint else ""
    lines.append(f"{_HEADER} - {chief_complaint}:" if chief_complaint else f"{_HEADER}:")

    for row in triage_case.summary_fields:
        if row.is_missing or row.value in (None, ""):
            continue
        lines.append(f"- {_clean(row.label)}: {_clean(row.value)}")

    if summary and summary.red_flags:
        for finding in summary.red_flags:
            lines.append(f"- Dấu hiệu nguy hiểm ghi nhận: {_clean(finding.label)}")

    # Chỉ có dòng tiêu đề nghĩa là mọi trường đều còn thiếu - gửi đi thì bước trích xuất graph không
    # có evidence nào để bám, và hai model text chỉ thấy đúng tên than phiền.
    return "\n".join(lines) if len(lines) > 1 else ""
