"""`build_summary_text` là chỗ duy nhất dịch phiếu bàn giao sang text cho agent quyết định.

Test quan trọng nhất ở đây là `test_drops_missing_fields`: để lọt một trường chưa hỏi vào text sẽ làm
bước trích xuất graph biến "chưa hỏi" thành phủ định tường minh, tức bịa ra bằng chứng lâm sàng.
"""

from __future__ import annotations

from src.graph_triage.summary_text import build_summary_text
from src.models.schemas import HandoffSummary, RedFlagFinding, SummaryField, TriageCase


def _case(fields: list[SummaryField], **summary_kwargs) -> TriageCase:
    return TriageCase(
        summary=HandoffSummary(chief_complaint="Sốt 39.5°C", **summary_kwargs),
        summary_fields=fields,
        summary_ready=True,
    )


def test_uses_vietnamese_labels_from_summary_fields():
    text = build_summary_text(
        _case([
            SummaryField(label="Thời điểm bắt đầu sốt", value="2 ngày trước"),
            SummaryField(label="Nhiệt độ đo được", value="39.5"),
        ])
    )
    assert text.splitlines()[0] == "Tóm tắt tình trạng bệnh - Sốt 39.5°C:"
    assert "- Thời điểm bắt đầu sốt: 2 ngày trước" in text
    assert "- Nhiệt độ đo được: 39.5" in text


def test_drops_missing_fields():
    """Trường chưa hỏi KHÔNG được xuất hiện dưới bất kỳ dạng nào."""
    text = build_summary_text(
        _case([
            SummaryField(label="Nhiệt độ đo được", value="39.5"),
            SummaryField(label="Lượng nước tiểu", value=None, is_missing=True),
            SummaryField(label="Cứng cổ", value=None, is_missing=True),
        ])
    )
    assert "Lượng nước tiểu" not in text
    assert "Cứng cổ" not in text
    assert "chưa cung cấp" not in text.lower()
    assert "None" not in text
    assert text.count("\n") == 1  # đúng 1 tiêu đề + 1 dòng dữ liệu


def test_includes_red_flags():
    text = build_summary_text(
        _case(
            [SummaryField(label="Nhiệt độ đo được", value="39.5")],
            red_flags=[RedFlagFinding(code="RF-13", label="Cứng cổ kèm sốt cao")],
        )
    )
    assert "- Dấu hiệu nguy hiểm ghi nhận: Cứng cổ kèm sốt cao" in text


def test_empty_when_no_field_is_filled():
    """Chỉ có tiêu đề thì không có evidence nào để trích xuất - đừng gọi API làm gì."""
    assert build_summary_text(_case([SummaryField(label="Nhiệt độ đo được", is_missing=True)])) == ""
    assert build_summary_text(TriageCase()) == ""


def test_collapses_whitespace_so_provenance_spans_stay_matchable():
    """`validate_provenance` so span sau khi chuẩn hoá khoảng trắng; text nguồn phải sạch từ đầu."""
    text = build_summary_text(
        _case([SummaryField(label="Mô tả", value="đau  đầu\n dữ dội")])
    )
    assert "- Mô tả: đau đầu dữ dội" in text
