"""Luồng ĐẦY ĐỦ: phiếu tóm tắt -> part 2 (quyết định nhãn) -> part 3 (trích nguồn). TỐN API.

    python -m scripts.check_full_flow

Khác `check_source_support.py` ở chỗ nó KHÔNG tự chế sẵn `llm_decision`. Nó dựng một `TriageCase`
thật, gọi đúng `service.decide_for_case` mà luồng web gọi, và để part 2 tự sinh quyết định. Nhờ vậy
nó kiểm được những thứ mà bài kia không kiểm được:

* `build_summary_text` có ra phiếu dùng được không (dòng `is_missing` bị bỏ đúng chưa);
* DeepSeek trích được Patient Graph với `source_span` khớp verbatim phiếu chưa;
* ba model cục bộ có đồng thuận không, và `model_disagreement` có bật `requires_human_review` không;
* **part 3 móc vào ĐÚNG CHỖ** - trước lúc `service` thu hẹp còn 5 khoá, nơi `evidence` và
  `risk_modifiers` còn tồn tại;
* cờ `requires_human_review` gộp đúng chiều (chỉ BẬT THÊM).

CHI PHÍ MỖI CA: 1 lời gọi DeepSeek (trích graph) + ~3 OpenAI (vòng tool + chốt) + 3-5 Gemini (part 3).
Cố ý chỉ có HAI ca - đây là bài kiểm luồng, không phải bài đo chất lượng.
"""

from __future__ import annotations

import logging
import sys

from src.graph_triage import service
from src.models.schemas import HandoffSummary, SummaryField, TriageCase

FEVER = TriageCase(
    case_id="flow-fever",
    summary=HandoffSummary(chief_complaint="Sốt cao kèm co giật ở trẻ nhỏ"),
    summary_fields=[
        SummaryField(label="Tuổi", value="14 tháng"),
        SummaryField(label="Sốt", value="đang sốt cao từ chiều qua"),
        SummaryField(label="Co giật", value="lên cơn co giật, người cứng lại, mắt trợn ngược khoảng hai phút"),
        SummaryField(label="Sau cơn", value="lịm đi, gọi không phản ứng"),
        SummaryField(label="Nôn", value=None, is_missing=True),
        SummaryField(label="Tiền sử co giật", value="chưa từng bị trước đây"),
    ],
)

ALLERGY = TriageCase(
    case_id="flow-allergy",
    summary=HandoffSummary(chief_complaint="Nổi mẩn ngứa sau khi uống kháng sinh"),
    summary_fields=[
        SummaryField(label="Tuổi", value="32 tuổi"),
        SummaryField(label="Phát ban", value="nổi mẩn đỏ khắp người, ngứa nhiều"),
        SummaryField(label="Thời điểm khởi phát", value="sau khi uống kháng sinh 2 ngày"),
        SummaryField(label="Khó thở", value="không thấy khó thở"),
        SummaryField(label="Sưng mặt", value="mặt không sưng"),
        SummaryField(label="Loại kháng sinh", value=None, is_missing=True),
    ],
)

BURNS = TriageCase(
    case_id="flow-burns",
    summary=HandoffSummary(chief_complaint="Bỏng nước sôi diện rộng"),
    summary_fields=[
        SummaryField(label="Tuổi", value="28 tuổi"),
        SummaryField(label="Cơ chế", value="đổ nồi nước sôi vào người khi đang nấu ăn"),
        SummaryField(label="Vị trí bỏng", value="bỏng vùng ngực và cả hai cánh tay"),
        SummaryField(label="Diện tích", value="mảng da đỏ rộng, có phồng rộp nhiều chỗ"),
        SummaryField(label="Đau", value="đau rát dữ dội"),
        SummaryField(label="Khó thở", value=None, is_missing=True),
    ],
)
"""Ca NGOÀI 5 nhóm triệu chứng MVP - cố ý. Corpus 39 tài liệu không phủ bỏng, nên đây là ca đầu tiên
kích hoạt được nhánh index-miss: search -> fetch -> nạp index -> tra lại."""

CASES = {"fever": FEVER, "allergy": ALLERGY, "burns": BURNS}


def parse_args():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=sorted(CASES), help="Chỉ chạy một ca.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    for triage_case in ([CASES[args.case]] if args.case else list(CASES.values())):
        print("=" * 78)
        print(f"CA: {triage_case.case_id}")
        print("=" * 78)

        from src.graph_triage.summary_text import build_summary_text

        summary_text = build_summary_text(triage_case)
        print("\n--- PHIẾU TÓM TẮT (đầu vào của part 2) ---")
        for line in summary_text.splitlines():
            print(f"  {line}")

        result = service.decide_for_case(triage_case)
        if result is None:
            print("\n  KHÔNG CÓ KẾT QUẢ - tính năng tắt hoặc agent dựng không được. Xem log ở trên.")
            continue

        print("\n--- PART 2: QUYẾT ĐỊNH ---")
        print(f"  nhãn              : {result['triage_label']}")
        print(f"  cần người xem     : {result['requires_human_review']}  (đã GỘP cờ của part 3)")
        print(f"  model             : {result['model']}")
        print("  tóm tắt quyết định:")
        for line in _wrap(result["decision_summary"]):
            print(f"    {line}")

        support = result.get("source_support")
        if not support:
            print("\n--- PART 3: KHÔNG CÓ ---  (tắt, hoặc guard chặn - xem log)")
            continue

        print("\n--- PART 3: TRÍCH NGUỒN ---")
        for line in support["explanation_vi"].splitlines():
            print(f"  {line}")
        for citation in support["explanation_citations"]:
            print(f"\n  {citation['marker']} {citation['publisher']} · {citation['url']}")
            print(f'      "{" ".join(citation["quote"].split())[:170]}"')

        # `cost` và `claims[]` KHÔNG có ở đây: `service.decide_for_case` cố ý chỉ trả phần hiển
        # thị (mục A5). Số liệu vận hành nằm ở dòng log `source_support.done`.
        summary = support["summary"]
        print(f"\n  claim={summary['claims_examined']} có_nguồn={summary['claims_with_support']} "
              f"trích_dẫn={summary['verified_citations']} search={summary['web_searches_performed']} "
              f"cần_người_xem={summary['requires_human_review']}")
        print(f"  can_change_label={support['method']['can_change_label']}")
        print()

    return 0


def _wrap(text: str, width: int = 92) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines


if __name__ == "__main__":
    sys.exit(main())
