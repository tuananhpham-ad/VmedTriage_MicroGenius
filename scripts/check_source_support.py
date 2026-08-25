"""Chạy hai ca chuẩn qua part 3 và in kết quả để người đọc tự phán. TỐN lời gọi API.

    python -m scripts.check_source_support                 # cả hai ca
    python -m scripts.check_source_support --case allergy  # chỉ ca dị ứng da
    python -m scripts.check_source_support --provider-order gemini,openai

HAI CA NÀY KHÔNG TƯƠNG ĐƯƠNG NHAU.

`fever` là ca thuận: kiểm hệ thống có chạy thông không, và corpus đã nạp có đủ để `web_searches` bằng
0 ngay lần đầu không.

`allergy` là **ĐIỂM DỪNG BẮT BUỘC**. Lập luận gốc dựa trên việc VẮNG MẶT dấu hiệu, và nguồn NHS chỉ
liệt kê hai dấu hiệu đó như cảnh báo *nếu xuất hiện* - tức nó là MỆNH ĐỀ ĐẢO, không chứng minh được
chiều ngược lại. Verdict đúng là `unsupported` hoặc `partial`.

Nếu ca này ra `supports`, hoặc đoạn diễn giải viết "vì không khó thở nên chưa đến mức cấp cứu" kèm
link NHS, thì **DỪNG LẠI**: siết prompt bước 6 rồi chạy lại. Đây là chỗ thiết kế post-hoc dễ hỏng
nhất, và hỏng ở đây thì mọi trích dẫn phía sau đều là trang trí cho một suy luận sai.

Script này KHÔNG tự kết luận đỗ/trượt thay bạn - nó in ra đủ dữ kiện rồi nêu tiêu chí. Một bài kiểm
mà máy tự chấm "đạt" là một bài kiểm không ai đọc.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any

from src.config import get_settings
from src.source_support import pipeline
from src.source_support.index import SourceIndex
from src.source_support.schemas import SourceSupport

FEVER_CASE: dict[str, Any] = {
    "triage_label": "cap_cuu",
    "decision_summary": (
        "Báo cáo mô tả cháu đang sốt cao thì lên cơn co giật, người cứng lại, mắt trợn ngược khoảng "
        "hai phút; sau cơn lịm đi và gọi không phản ứng. Co giật khi đang sốt ở trẻ nhỏ kèm không đáp "
        "ứng kéo dài sau cơn cần được đánh giá cấp cứu."
    ),
    "uncertainty_summary": "Chưa rõ tiền sử co giật trước đây.",
    "requires_human_review": False,
    "risk_modifiers": [{"factor": "extreme_age", "source_span": "cháu bé 14 tháng tuổi"}],
    "evidence": [
        {"concept": "fever", "status": "present", "source_span": "đang sốt cao"},
        {"concept": "seizure", "status": "present", "source_span": "lên cơn co giật"},
        {"concept": "lethargy", "status": "present", "source_span": "lịm đi"},
    ],
}

ALLERGY_CASE: dict[str, Any] = {
    "triage_label": "kham_som",
    "decision_summary": (
        "Bệnh nhân nổi mẩn đỏ ngứa khắp người sau khi uống kháng sinh 2 ngày. Không thấy khó thở, mặt "
        "không sưng, nên chưa có dấu hiệu phản vệ cần cấp cứu ngay; tuy nhiên cần khám sớm để đánh "
        "giá dị ứng thuốc."
    ),
    "uncertainty_summary": "Chưa rõ loại kháng sinh đã dùng.",
    "requires_human_review": False,
    "risk_modifiers": [],
    "evidence": [
        {"concept": "skin_redness", "status": "present", "source_span": "nổi mẩn đỏ khắp người"},
        {"concept": "itching", "status": "present", "source_span": "ngứa"},
        {"concept": "dyspnea", "status": "absent", "source_span": "Không thấy khó thở"},
        {"concept": "swelling", "status": "absent", "source_span": "mặt không sưng"},
    ],
}

CASES = {"fever": FEVER_CASE, "allergy": ALLERGY_CASE}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=sorted(CASES), help="Chỉ chạy một ca.")
    parser.add_argument("--provider-order", help='Ép thứ tự provider cho cả 3 bước, ví dụ "gemini,openai".')
    parser.add_argument("--index-only", action="store_true", help="Không search web, chỉ dùng index.")
    parser.add_argument("--json", action="store_true", help="In nguyên khối JSON thay vì bản đọc được.")
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args()
    settings = get_settings()

    if args.provider_order:
        for attribute in ("role_order_claim_splitter", "role_order_source_verdict", "role_order_source_explain"):
            setattr(settings, attribute, args.provider_order)
    if args.index_only:
        settings.source_support_index_only = True

    index = SourceIndex.load()
    if not index:
        print("Index rỗng. Chạy trước: python -m scripts.build_source_corpus", file=sys.stderr)
        return 1
    print(f"Index: {len(index)} chunk · {len(index.urls)} tài liệu · ngưỡng {settings.source_support_threshold}")
    print(f"Thứ tự provider: {settings.role_order_source_verdict or settings.llm_provider_order}\n")

    for name in [args.case] if args.case else list(CASES):
        support = pipeline.run(CASES[name], triage_label=CASES[name]["triage_label"], index=index)
        if args.json:
            print(json.dumps(support.model_dump(mode="json"), ensure_ascii=False, indent=2))
        else:
            _render(name, support)
    return 0


def _render(name: str, support: SourceSupport) -> None:
    print("=" * 78)
    print(f"CA: {name}")
    print("=" * 78)

    for result in support.claims:
        source = result.sources[0] if result.sources else None
        print(f"\n  [{result.verdict.upper()}] {result.claim.claim_vi}")
        print(f"      loại       : {result.claim.claim_kind}")
        print(f"      neo vào    : {result.claim.grounded_in[:90]!r}")
        print(f"      tra cứu    : index={result.retrieval.from_index} "
              f"search={result.retrieval.searched_web} điểm={result.retrieval.best_score:.3f}")
        if source:
            print(f"      nguồn      : {source.publisher} · {source.url[:70]}")
            print(f"      trích      : {' '.join(source.quote.split())[:150]}")
            print(f"      lý do      : {source.verdict_reason[:150]}")

    print("\n  --- ĐOẠN DIỄN GIẢI ---")
    for line in support.explanation_vi.splitlines():
        print(f"  {line}")

    if support.explanation_citations:
        print("\n  --- TRÍCH DẪN ---")
        for citation in support.explanation_citations:
            print(f"  {citation.marker} {citation.publisher} · {citation.url}")
            print(f"      \"{' '.join(citation.quote.split())[:150]}\"")

    summary, cost = support.summary, support.cost
    print(f"\n  claim={summary.claims_examined} có_nguồn={summary.claims_with_support} "
          f"trích_dẫn={summary.verified_citations} search={summary.web_searches_performed} "
          f"cần_người_xem={summary.requires_human_review}")
    print(f"  call={cost.llm_calls} provider={cost.provider_calls} embed_tok≈{cost.embed_tokens}")

    if name == "allergy":
        _allergy_criteria(support)
    print()


def _allergy_criteria(support: SourceSupport) -> None:
    """In tiêu chí của điểm dừng bắt buộc. Cố ý KHÔNG tự chấm đỗ/trượt - xem docstring module."""
    rule_outs = [r for r in support.claims if r.claim.claim_kind == "rule_out"]
    print("\n  --- ĐIỂM DỪNG BẮT BUỘC: tự đọc rồi phán ---")
    print(f"  claim loại rule_out: {len(rule_outs)}")
    for result in rule_outs:
        print(f"    verdict={result.verdict}  <- phải là unsupported hoặc partial, KHÔNG được supports")
    print("  Đoạn diễn giải PHẢI nói thẳng là không tìm được tài liệu ủng hộ suy luận 'vắng dấu hiệu'.")
    print("  Nếu nó viết \"vì không khó thở nên chưa đến mức cấp cứu\" kèm link NHS -> DỪNG,")
    print("  siết prompt bước 6 (src/source_support/verdict.py) rồi chạy lại.")


if __name__ == "__main__":
    sys.exit(main())
