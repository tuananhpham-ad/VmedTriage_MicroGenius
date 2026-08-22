"""Điều phối bảy bước của part 3. Điểm vào duy nhất: `run()`.

BA RÀNG BUỘC CỦA TẦNG NÀY, không được phá:

1. **KHÔNG BAO GIỜ đổi `triage_label`.** `run()` không nhận quyền ghi vào quyết định; nó trả về một
   khối gắn CẠNH. Đường duy nhất nó tác động tới ca là `summary.requires_human_review`, và người gọi
   OR cờ đó vào cờ của part 2 - chỉ BẬT THÊM, không bao giờ hạ.

2. **Nhãn chỉ vào ở bước 7.** `extract_claims` và `grade_all` không nhận `triage_label`. Đó không
   phải quy ước lỏng lẻo mà là hình dạng chữ ký hàm: muốn phá thì phải sửa chữ ký, và lúc đó có chỗ
   để dừng lại mà hỏi tại sao.

3. **Best-effort ở tầng TRÊN, không phải ở đây.** Module này để lỗi ném ra. `service.decide_for_case`
   mới là chỗ nuốt và ghi log, vì nó nằm trên đường phản hồi của bệnh nhân. Nuốt lỗi ở cả hai tầng là
   cách một guard hỏng suốt nhiều tuần mà không ai biết.

THỨ TỰ BẮT BUỘC, mỗi bước là điều kiện của bước sau:

    tách claim -> Guard 0a/0b -> tra index (+search) -> chọn quote -> chấm blind (+Guard 0c)
    -> diễn giải -> Guard 5a/5b
"""

from __future__ import annotations

import logging
import re
from typing import Any

from src.config import get_settings
from src.observability.braintrust_tracing import traced_span
from src.source_support.claims import extract_claims
from src.source_support.explain import NO_SOURCE_NOTE, write_explanation
from src.source_support.index import SourceIndex
from src.source_support.llm import CostMeter
from src.source_support.retrieval import retrieve
from src.source_support.schemas import (
    ClaimResult,
    CostReport,
    Retrieval,
    SourceSupport,
    SupportSummary,
)
from src.source_support.verdict import grade_all, to_source_hits

logger = logging.getLogger("vmedtriage.source_support")

DEFAULT_PATIENT_LABEL = "người bệnh"


def run(decision: dict[str, Any], *, triage_label: str, index: SourceIndex | None = None) -> SourceSupport:
    """Chạy đủ bảy bước cho một quyết định. Raise khi guard chặn hoặc model hỏng - xem ràng buộc 3.

    `decision` là `result["llm_decision"]` lấy BÊN TRONG `service.decide_for_case`, trước chỗ nó thu
    hẹp còn 5 khoá: `evidence` và `risk_modifiers` bị bỏ ở ranh giới đó, mà bước 1 lẫn Guard 0b đều
    cần chúng."""
    settings = get_settings()
    meter = CostMeter()

    # Unit D (docs/eval/01_evaluation_units.md mục 5) - trích claim đi qua provider_router
    # (role=ROLE_CLAIM_SPLITTER), còn embedding (text-embedding-3-small) và web-search fallback
    # (Gemini grounding / Tavily) gọi THẲNG provider của chúng, KHÔNG qua provider_router - ghi rõ
    # trong metadata để không lẫn với các bước có via_provider_router=True.
    with traced_span(
        "claim_extraction_retrieval",
        input={"triage_label": triage_label},
        metadata={
            "unit": "D: claim extraction & retrieval",
            "claim_extraction": {"via_provider_router": True, "role": "ROLE_CLAIM_SPLITTER"},
            "embedding_direct_openai": {"via_provider_router": False, "model": "text-embedding-3-small"},
            "web_search_fallback": {
                "via_provider_router": False,
                "provider": settings.source_support_search_provider,
            },
            "can_change_label": False,
        },
    ) as claim_retrieval_span:
        claims = extract_claims(decision, meter=meter)
        if not claims:
            claim_retrieval_span.log(output={"claims_extracted": 0})
            return _empty(meter, note=NO_SOURCE_NOTE, reason="khong_tach_duoc_claim")

        index = index if index is not None else SourceIndex.load()
        before = len(index)
        evidences = [retrieve(claim, index, meter=meter) for claim in claims]
        if len(index) > before:
            index.save()
        claim_retrieval_span.log(
            output={
                "claims_extracted": len(claims),
                "web_searches_performed": meter.web_searches,
                "index_grew_by": len(index) - before,
            }
        )

    # Unit E (docs/eval/01_evaluation_units.md mục 6) - verdict.grade() + explain.write_explanation(),
    # cả hai đi qua provider_router (role=ROLE_SOURCE_VERDICT / ROLE_SOURCE_EXPLAIN).
    with traced_span(
        "verdict_explanation",
        input={"claims_to_grade": len(claims)},
        metadata={
            "unit": "E: verdict grading & explanation",
            "via_provider_router": True,
            "roles": ["ROLE_SOURCE_VERDICT", "ROLE_SOURCE_EXPLAIN"],
            "can_change_label": False,
        },
    ) as verdict_span:
        results: list[ClaimResult] = []
        dropped = 0
        for evidence, response in grade_all(evidences, meter=meter):
            # Guard 0c: claim đã bị viết lệch khỏi lập luận gốc thì bỏ hẳn, không đưa sang bước diễn
            # giải. Bỏ chứ không hạ verdict: một claim không phản ánh đúng lập luận thì kết quả đối
            # chiếu của nó - dù là `supports` hay `unsupported` - đều đang nói về một mệnh đề khác
            # với mệnh đề hệ thống thật sự dựa vào, nên nó không có nghĩa gì để hiển thị.
            if not response.claim_matches_reasoning:
                dropped += 1
                logger.warning(
                    "source_support.claim_dropped reason=guard_0c claim=%r grounded_in=%r",
                    evidence.claim.claim_en[:80], evidence.claim.grounded_in[:80],
                )
                continue
            results.append(
                ClaimResult(
                    claim=evidence.claim,
                    verdict=response.verdict,
                    retrieval=evidence.retrieval,
                    sources=to_source_hits(evidence, response),
                )
            )

        if not results:
            # MỌI claim đều bị Guard 0c loại. Đây là kết thúc HỢP LỆ, không phải lỗi - nhưng nó phải
            # để lại dấu vết: nếu chỉ có mấy dòng `claim_dropped` rồi im bặt thì người đọc log không
            # phân biệt được "đã xong và không có gì để trích" với "treo giữa chừng" hay "văng ngoại lệ".
            verdict_span.log(output={"dropped_by_guard_0c": dropped, "results": 0})
            return _empty(meter, note=NO_SOURCE_NOTE, examined=len(claims), dropped=dropped,
                          reason="moi_claim_bi_guard_0c_loai")

        explanation, citations = write_explanation(
            results,
            triage_label=triage_label,
            patient_label=_patient_label(decision),
            patient_spans=_patient_spans(decision),
            meter=meter,
        )
        verdict_span.log(
            output={
                "dropped_by_guard_0c": dropped,
                "citations": len(citations),
                "explanation_chars": len(explanation),
            }
        )

    contradicted = [result.claim.claim_vi for result in results if result.verdict == "contradicts"]
    summary = SupportSummary(
        claims_examined=len(claims),
        claims_with_support=sum(1 for r in results if r.verdict in {"supports", "partial"}),
        verified_citations=len(citations),
        contradicted_claims=contradicted,
        requires_human_review=bool(contradicted),
        web_searches_performed=meter.web_searches,
    )
    logger.info(
        "source_support.done claims=%s supported=%s citations=%s contradicted=%s dropped=%s "
        "searches=%s calls=%s providers=%s threshold=%.2f",
        summary.claims_examined, summary.claims_with_support, summary.verified_citations,
        len(contradicted), dropped, summary.web_searches_performed, meter.llm_calls,
        meter.provider_calls, settings.source_support_threshold,
    )
    return SourceSupport(
        explanation_vi=explanation,
        explanation_citations=citations,
        claims=results,
        summary=summary,
        cost=_cost(meter),
    )


def merge_human_review(decision_flag: bool, support: SourceSupport | None) -> bool:
    """Gộp cờ người xem. CHỈ BẬT THÊM - part 3 không bao giờ được hạ cờ mà part 2 đã dựng lên.

    Viết thành hàm riêng để chỗ nối ở `service.py` không phải tự nhớ chiều của phép OR; đảo chiều ở
    đó là cách một ca cần người xem lặng lẽ trôi qua."""
    if support is None:
        return decision_flag
    return decision_flag or support.summary.requires_human_review


_AGE_PHRASE = re.compile(
    r"(?:bé|cháu|em bé|trẻ|bệnh nhân|người bệnh)?\s*\d{1,3}\s*(?:tháng|tuần|ngày|tuổi)(?:\s*tuổi)?",
    re.IGNORECASE,
)

_FIELD_PREFIX = re.compile(r"^[^:\n]{1,40}:\s*")
"""Tiền tố "<nhãn>: " của một dòng trong phiếu tóm tắt. Chặn ở 40 ký tự để không nuốt nhầm một câu
văn có dấu hai chấm giữa chừng."""


def _patient_label(decision: dict[str, Any]) -> str:
    """Mô tả bệnh nhân cho câu mở đầu, lấy từ trích dẫn NGUYÊN VĂN chứ không tự sinh.

    BA NGUỒN, XẾP THEO ĐỘ TIN CẬY. `risk_modifiers` là chỗ tuổi đáng lẽ nằm - nhưng đo trên luồng
    thật (2026-08-19) thì part 2 KHÔNG phải lúc nào cũng sinh risk_modifier, kể cả với bệnh nhi 14
    tháng. Khi đó câu mở đầu tụt xuống "Tình trạng hiện tại của người bệnh", mất hẳn thông tin tuổi -
    thứ quan trọng nhất để điều dưỡng định hướng.

    Nguồn thứ hai là cụm tuổi trong `decision_summary`. Nó vẫn là trích NGUYÊN VĂN (một lát cắt của
    câu lập luận), không phải mô tả do model bịa ra - đó là ranh giới không được vượt: tự sinh mô tả
    bệnh nhân là bịa dữ kiện lâm sàng."""
    for modifier in decision.get("risk_modifiers") or []:
        span = str(modifier.get("source_span") or "").strip()
        if span:
            return span

    match = _AGE_PHRASE.search(str(decision.get("decision_summary") or ""))
    if match:
        return match.group(0).strip()

    return DEFAULT_PATIENT_LABEL


def _clean_span(span: str) -> str:
    """Bỏ tiền tố nhãn trường của phiếu tóm tắt: "Sốt: đang sốt cao" -> "đang sốt cao".

    Phiếu dựng dạng "- <nhãn>: <giá trị>", nên `source_span` trích verbatim từ nó mang theo cả tiền
    tố. Đoạn diễn giải đặt nguyên chuỗi đó trong ngoặc kép thì đọc ra "Người bệnh có biểu hiện
    *Sốt: đang sốt cao từ chiều qua*" - đúng nội dung nhưng gượng như đọc biểu mẫu.

    AN TOÀN VÌ ĐÂY KHÔNG PHẢI TRÍCH DẪN NGUỒN. Các span này chỉ là đầu vào hiển thị cho bước 7;
    guard 5 kiểm quote của CITATION (cắt từ chunk y văn), không kiểm chuỗi này. Bất biến "trích dẫn
    nguyên văn" không bị đụng tới."""
    return _FIELD_PREFIX.sub("", span).strip()


def _patient_spans(decision: dict[str, Any], limit: int = 6) -> list[str]:
    """Các trích dẫn tiếng Việt để bước 7 đặt trong ngoặc kép.

    Chỉ lấy dấu hiệu CÓ MẶT: nhắc lại "không khó thở" trong phần mô tả triệu chứng đọc như một lời
    trấn an, mà đó chính là kiểu suy luận thiếu căn cứ cả tầng này đang tìm cách chặn."""
    spans = [
        _clean_span(str(item.get("source_span") or ""))
        for item in decision.get("evidence") or []
        if item.get("status") == "present"
    ]
    return [span for span in dict.fromkeys(spans) if span][:limit]


def _cost(meter: CostMeter) -> CostReport:
    return CostReport(
        llm_calls=meter.llm_calls,
        input_tokens=meter.input_tokens,
        output_tokens=meter.output_tokens,
        embed_tokens=meter.embed_tokens,
        web_searches=meter.web_searches,
        provider_calls=dict(meter.provider_calls),
    )


def _empty(
    meter: CostMeter, *, note: str, examined: int = 0, dropped: int = 0, reason: str = "",
) -> SourceSupport:
    """Ca không có gì để trích. Vẫn trả về khối đầy đủ kèm câu nói THẲNG là không có nguồn - im lặng
    sẽ bị đọc thành "hệ thống chưa chạy" thay vì "đã tra và không thấy".

    Ghi CÙNG một dòng `source_support.done` như đường thuận, để mọi ca đều kết thúc bằng đúng một
    dòng tổng kết - dù nó có trích được gì hay không."""
    logger.info(
        "source_support.done claims=%s supported=0 citations=0 contradicted=0 dropped=%s "
        "searches=%s calls=%s providers=%s ket_thuc=%s",
        examined, dropped, meter.web_searches, meter.llm_calls, meter.provider_calls, reason or "khong_co_gi",
    )
    return SourceSupport(
        explanation_vi=note,
        summary=SupportSummary(claims_examined=examined, web_searches_performed=meter.web_searches),
        cost=_cost(meter),
    )


__all__ = ["Retrieval", "merge_human_review", "run"]
