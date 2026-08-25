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

3. CHỈ GỬI FIELD `true` (quyết định của chủ dự án, 2026-08-25). Field `false` bị bỏ; field `true`
   render bằng RIÊNG NHÃN, không có đuôi `: true`.

   Vì sao bỏ `: true`/`: false` chứ không dịch sang "có"/"không": chuỗi cũ là `- <nhãn>: false`, và
   với LogReg (TF-IDF tiếng Việt) lẫn PhoBERT thì `false` là token vô nghĩa trong khi nhãn vẫn chứa
   nguyên chữ "có sốt" - model đọc thành CÓ sốt, đúng ngược điều người bệnh nói. Chữ `true` còn rò
   xa hơn: `source_explain` ngày 2026-08-24 sinh ra câu gửi người bệnh 'Người bệnh có biểu hiện
   "true".'

   CÁI MẤT, phải biết trước khi ai đó dựa vào chuỗi này: tầng C6 không còn phân biệt "đã hỏi, người
   bệnh khẳng định KHÔNG có" với "chưa hỏi tới". Chấp nhận được vì hai lý do, cả hai đã kiểm:
   - `build_summary_text` có ĐÚNG MỘT người gọi (`service.decide_for_case`) và rule engine KHÔNG
     đọc nó - mức ưu tiên có hiệu lực vẫn do rule engine chấm trên snapshot đầy đủ;
   - cả ba nhánh C6 chỉ bỏ phiếu THEO CHIỀU NÂNG. Bớt thông tin làm chúng thận trọng hơn, không làm
     chúng bỏ sót cấp cứu.
   Snapshot đầy đủ ba trạng thái vẫn còn nguyên ở `_symptom_field_values` (JSON cho model xác suất)
   và ở `summary_render.field_summary()` (văn xuôi + guard chống bịa phủ định).

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
_TRUE, _FALSE = "true", "false"


def _clean(value: object) -> str:
    return " ".join(str(value).split())


def _tri_state(value: object) -> str | None:
    """`"true"`/`"false"` nếu đây là field tri-state, `None` nếu là field số/enum/tự do.

    Nhận dạng theo GIÁ TRỊ chứ không theo `FieldSpec.tri_state`, vì `TriageCase` không mang
    `protocol` theo và không field enum nào của protocol có `true`/`false` trong `allowed_values`
    (`fever_status` là objective/subjective/none, `temp_site` là axillary/oral/..., `temp_c` là số).
    """
    text = str(value).strip().lower()
    return text if text in (_TRUE, _FALSE) else None


def build_summary_text(triage_case: TriageCase) -> str:
    """Trả về phiếu tóm tắt dạng text. Chuỗi rỗng nghĩa là chưa có gì đáng gửi đi."""
    summary = triage_case.summary
    lines: list[str] = []

    chief_complaint = _clean(summary.chief_complaint) if summary and summary.chief_complaint else ""
    lines.append(f"{_HEADER} - {chief_complaint}:" if chief_complaint else f"{_HEADER}:")

    for row in triage_case.summary_fields:
        if row.is_missing or row.value in (None, ""):
            continue
        state = _tri_state(row.value)
        if state == _FALSE:
            continue
        # Field tri-state `true` render bằng RIÊNG NHÃN. Trước đây là `- <nhãn>: true`, và chữ
        # `true` đó không chỉ vô nghĩa với model tiếng Việt - nó còn rò tới tận người bệnh: bản
        # `source_explain` ngày 2026-08-24 sinh ra câu 'Người bệnh có biểu hiện "true".'
        lines.append(
            f"- {_clean(row.label)}"
            if state == _TRUE
            else f"- {_clean(row.label)}: {_clean(row.value)}"
        )

    if summary and summary.red_flags:
        for finding in summary.red_flags:
            lines.append(f"- Dấu hiệu nguy hiểm ghi nhận: {_clean(finding.label)}")

    # Chỉ có dòng tiêu đề nghĩa là mọi trường đều còn thiếu - gửi đi thì bước trích xuất graph không
    # có evidence nào để bám, và hai model text chỉ thấy đúng tên than phiền.
    return "\n".join(lines) if len(lines) > 1 else ""
