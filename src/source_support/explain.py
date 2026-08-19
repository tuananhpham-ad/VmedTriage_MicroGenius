"""Bước 7 - diễn giải tiếng Việt, và **Guard 5**: lớp chặn cuối, bằng code.

MẶT NGUY HIỂM NHẤT CỦA CẢ HỆ THỐNG nằm ở đây: một đoạn văn xuôi tiếng Việt trôi chảy kèm link NHS/WHO
đọc lên rất có thẩm quyền - **kể cả khi nhãn sai**. Người đọc thấy trích dẫn thì tin, mà trích dẫn thì
chỉ chứng minh được mệnh đề tổng quát chứ không chứng minh được ca này.

Vì thế ràng ba lớp, và hai trong ba là CODE chứ không phải prompt:

1. Chỉ claim `supports`/`partial` được phép mang trích dẫn (lọc trước khi gọi model).
2. **Guard 5a** - mọi URL trong đoạn văn phải thuộc tập đã verify, và mọi quote trong citation phải
   khớp NGUYÊN VĂN chunk gốc. Sửa một chữ cũng raise.
3. **Guard 5b** - có claim `contradicts` thì đoạn văn BẮT BUỘC chứa câu cảnh báo cố định.

GUARD 5B LÀ PHẦN THÊM VÀO SO VỚI ĐẶC TẢ GỐC. Đặc tả yêu cầu "nếu có claim contradicts thì phải nói
ra, không được lờ đi" nhưng giao việc đó cho prompt - trên đúng cái output nguy hiểm nhất, và trái
với chuẩn "kiểm bằng code, không bằng prompt" mà chính nó đặt ra cho bốn guard kia. Ở đây câu cảnh báo
là một HẰNG CHUỖI do code chèn, không phải câu do model viết: model quên, model diễn đạt nhẹ đi, hay
model bỏ hẳn đều không thay đổi được điều người đọc nhìn thấy.

CÂU MỞ ĐẦU CẦN NHÃN, VÀ ĐÂY LÀ CHỖ DUY NHẤT NHÃN ĐI VÀO PART 3. Bước 1 và bước 6 không bao giờ thấy
`triage_label` - đó là cơ chế giữ tính blind. Nhãn chỉ xuất hiện ở bước cuối, khi mọi verdict đã chốt
xong và không còn gì để nó tác động tới.
"""

from __future__ import annotations

import json
import logging
import re

from pydantic import BaseModel, ConfigDict, Field

from src.graph_triage.graph_schema import normalise_span
from src.services.infra.provider_router import ROLE_SOURCE_EXPLAIN
from src.source_support.llm import CostMeter, call_json
from src.source_support.quotes import QuoteIntegrityError
from src.source_support.schemas import Citation, ClaimResult, SourceHit

logger = logging.getLogger("vmedtriage.source_support")

CONTRADICTION_WARNING = (
    "Lưu ý: có ít nhất một lập luận trong đánh giá này bị tài liệu tham khảo nói ngược lại. "
    "Ca đã được đánh dấu cần người xem lại."
)
"""Hằng chuỗi của Guard 5b. KHÔNG để model viết câu này - xem docstring module."""

NO_SOURCE_NOTE = (
    "Không tìm được tài liệu tham khảo cho trường hợp này. Việc không có nguồn không có nghĩa đánh "
    "giá sai, cũng không có nghĩa là đúng."
)

_URL_PATTERN = re.compile(r"https?://[^\s\)\]\"'<>]+")

TRIAGE_DISPLAY_VI = {
    "cap_cuu": "CẤP CỨU",
    "kham_som": "KHÁM SỚM",
    "theo_doi_tai_nha": "THEO DÕI TẠI NHÀ",
}


class ExplanationGuardError(RuntimeError):
    """Guard 5 chặn đoạn diễn giải. Không sửa, không cắt gọt - raise để người gọi bỏ hẳn phần trích
    nguồn của ca đó. Một đoạn văn không có trích dẫn tốt hơn hẳn một đoạn văn trích dẫn sai chỗ."""


class ExplanationResponse(BaseModel):
    """Structured output của bước 7."""

    model_config = ConfigDict(extra="forbid")

    explanation_vi: str = Field(min_length=1)
    used_markers: list[str] = Field(default_factory=list)


SYSTEM_PROMPT = """Bạn viết một đoạn giải thích ngắn bằng tiếng Việt cho nhân viên y tế đọc.

Đầu vào gồm: mức phân loại đã chốt, mô tả bệnh nhân, các trích dẫn nguyên văn từ người bệnh, và danh
sách mệnh đề đã được đối chiếu với tài liệu y khoa (mỗi mệnh đề kèm kết quả đối chiếu và marker [n]
nếu có nguồn dùng được).

CẤU TRÚC BẮT BUỘC:
1. Câu mở đầu đúng dạng: "Tình trạng hiện tại của {mô tả bệnh nhân}: {MỨC}"
2. Một đoạn nhắc lại triệu chứng, dùng CHÍNH các trích dẫn tiếng Việt được đưa, đặt trong ngoặc kép.
3. Mục "Vì sao ở mức này:" - gạch đầu dòng, mỗi dòng một mệnh đề CÓ nguồn, kết thúc bằng marker [n].
4. Nếu có mệnh đề không có nguồn mà lập luận vẫn dựa vào, nói THẲNG là không tìm được tài liệu ủng hộ
   suy luận đó. Không lờ đi, không viết mập mờ.
5. Câu cuối nêu rõ phạm vi: nguồn nói về dấu hiệu lâm sàng nói chung, việc áp vào ca này là suy luận
   của hệ thống.

CẤM TUYỆT ĐỐI:
- Gắn marker [n] cho một mệnh đề không được cấp marker trong đầu vào. Marker do đầu vào cấp, không
  phải do bạn đặt ra.
- Viết URL vào đoạn văn. Chỉ dùng marker [n]; phần liệt kê nguồn do hệ thống tự sinh.
- Nêu tên bệnh như một kết luận, nêu hướng điều trị, nêu liều thuốc, nêu chẩn đoán.
- Nói rằng "vì có nguồn nên mức này đúng". Nguồn nói về dấu hiệu, không nói về ca này.
- Thêm bất kỳ dấu hiệu hay chi tiết y khoa nào không có trong đầu vào.

Trả về DUY NHẤT một JSON object: {"explanation_vi": "...", "used_markers": ["[1]", "[2]"]}"""


def build_citations(results: list[ClaimResult]) -> tuple[list[Citation], dict[str, str]]:
    """Cấp marker `[n]` cho các nguồn dùng được. Trả về (citations, claim_en -> marker).

    Chỉ claim `supports`/`partial` được cấp marker - đây là lớp lọc 1, và nó chạy TRƯỚC khi gọi model
    nên model không bao giờ nhìn thấy nguồn của một claim `unsupported` để mà trích nhầm."""
    citations: list[Citation] = []
    marker_by_claim: dict[str, str] = {}
    for result in results:
        if result.verdict not in {"supports", "partial"} or not result.sources:
            continue
        source = result.sources[0]
        marker = f"[{len(citations) + 1}]"
        citations.append(
            Citation(
                marker=marker,
                url=source.url,
                publisher=source.publisher,
                title=source.title,
                quote=source.quote,
            )
        )
        marker_by_claim[result.claim.claim_en] = marker
    return citations, marker_by_claim


def _user_prompt(
    results: list[ClaimResult],
    marker_by_claim: dict[str, str],
    *,
    triage_label: str,
    patient_label: str,
    patient_spans: list[str],
) -> str:
    payload = {
        "muc_phan_loai": TRIAGE_DISPLAY_VI.get(triage_label, triage_label),
        "mo_ta_benh_nhan": patient_label,
        "trich_dan_tu_nguoi_benh": patient_spans,
        "cac_menh_de": [
            {
                "menh_de": result.claim.claim_vi,
                "ket_qua_doi_chieu": result.verdict,
                "marker": marker_by_claim.get(result.claim.claim_en, ""),
                "ly_do": result.sources[0].verdict_reason if result.sources else "",
            }
            for result in results
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def write_explanation(
    results: list[ClaimResult],
    *,
    triage_label: str,
    patient_label: str,
    patient_spans: list[str],
    meter: CostMeter | None = None,
) -> tuple[str, list[Citation]]:
    """Bước 7 + Guard 5. Trả về (đoạn văn, danh sách trích dẫn)."""
    citations, marker_by_claim = build_citations(results)
    response = call_json(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=_user_prompt(
            results, marker_by_claim,
            triage_label=triage_label, patient_label=patient_label, patient_spans=patient_spans,
        ),
        schema=ExplanationResponse,
        role=ROLE_SOURCE_EXPLAIN,
        meter=meter,
    )
    assert isinstance(response, ExplanationResponse)
    text = _apply_contradiction_warning(response.explanation_vi.strip(), results)

    try:
        guard_citations(text, citations, results)
    except (ExplanationGuardError, QuoteIntegrityError) as error:
        # ĐƯỜNG LUI TẤT ĐỊNH, cùng khuôn với `output_guard.py`: guard chặn thì rơi về câu do CODE dựng
        # - khô hơn, nhưng chắc chắn chỉ chứa nguồn đã kiểm.
        #
        # Vì sao không để lỗi ném ra: `service.decide_for_case` nuốt mọi lỗi của part 3 thành `None`,
        # mà `None` nghĩa là `merge_human_review` không thấy cờ nào để bật. Tức là một lần model gõ
        # thừa "[1]" sẽ VỨT LUÔN tín hiệu `contradicts` - đúng thứ nguy hiểm nhất tầng này có nhiệm
        # vụ báo ra. Đoạn văn có thể xấu; cái cờ thì không được phép mất.
        logger.warning("source_support.explanation_rejected reason=%s: %s", type(error).__name__, error)
        text = render_fallback_explanation(
            results, citations, triage_label=triage_label, patient_label=patient_label,
        )
        guard_citations(text, citations, results)
    return text, citations


def render_fallback_explanation(
    results: list[ClaimResult],
    citations: list[Citation],
    *,
    triage_label: str,
    patient_label: str,
) -> str:
    """Đoạn diễn giải dựng HOÀN TOÀN bằng code, không một chữ nào do model viết.

    Dùng khi bản của model bị Guard 5 chặn. Nó nhạt, nhưng nó đúng theo cấu trúc: marker chỉ lấy từ
    `citations` đã cấp, không có URL trần, và câu cảnh báo `contradicts` luôn có mặt."""
    marker_by_claim = {
        result.claim.claim_en: citation.marker
        for result, citation in zip(
            [r for r in results if r.verdict in {"supports", "partial"} and r.sources], citations, strict=False,
        )
    }
    lines = [f"Tình trạng hiện tại của {patient_label}: {TRIAGE_DISPLAY_VI.get(triage_label, triage_label)}", ""]

    supported = [r for r in results if r.verdict in {"supports", "partial"}]
    if supported:
        lines.append("Vì sao ở mức này:")
        for result in supported:
            marker = marker_by_claim.get(result.claim.claim_en, "")
            lines.append(f"- {result.claim.claim_vi}{(' ' + marker) if marker else ''}")
        lines.append("")

    unsupported = [r for r in results if r.verdict == "unsupported"]
    if unsupported:
        lines.append("Không tìm được tài liệu tham khảo cho các lập luận sau:")
        lines.extend(f"- {result.claim.claim_vi}" for result in unsupported)
        lines.append("")

    lines.append(
        "Nguồn tham khảo nói về dấu hiệu lâm sàng nói chung. Việc áp vào ca này là suy luận của hệ "
        "thống, không phải điều tài liệu khẳng định."
    )
    return _apply_contradiction_warning("\n".join(lines).strip(), results)


def _apply_contradiction_warning(text: str, results: list[ClaimResult]) -> str:
    """**Guard 5b.** Có claim `contradicts` thì chèn câu cảnh báo bằng CODE.

    Chèn thay vì kiểm-rồi-raise là cố ý: nội dung cảnh báo không phụ thuộc vào ca nào cả, nên không có
    lý do gì để một lần model quên lại làm mất cả phần trích nguồn của ca đó. Điều phải bảo đảm là
    người đọc NHÌN THẤY câu này, và cách chắc chắn nhất là tự viết nó ra."""
    contradicted = [result for result in results if result.verdict == "contradicts"]
    if not contradicted:
        return text
    if normalise_span(CONTRADICTION_WARNING) in normalise_span(text):
        return text
    logger.info("source_support.contradiction_warning_injected count=%s", len(contradicted))
    return f"{text}\n\n{CONTRADICTION_WARNING}".strip()


def guard_citations(text: str, citations: list[Citation], results: list[ClaimResult]) -> None:
    """**Guard 5a.** Ba phép kiểm, tất cả là so chuỗi, tất cả `raise`."""
    verified_urls = {citation.url for citation in citations}

    # 1. Không URL trần nào trong đoạn văn. Marker [n] là đường DUY NHẤT dẫn tới nguồn, nhờ vậy tập
    #    URL người đọc thấy luôn đúng bằng tập đã qua kiểm - không có đường nào lọt vào giữa câu văn.
    for found in _URL_PATTERN.findall(text):
        if found.rstrip(".,;") not in verified_urls:
            raise ExplanationGuardError(
                f"Guard 5a: đoạn văn chứa URL không thuộc tập đã verify: {found!r}"
            )

    # 2. Mọi marker xuất hiện trong đoạn văn phải đã được cấp. Model tự đặt thêm [3] khi chỉ có hai
    #    nguồn là gắn một trích dẫn không tồn tại vào một câu khẳng định y khoa.
    known = {citation.marker for citation in citations}
    for marker in set(re.findall(r"\[\d+\]", text)):
        if marker not in known:
            raise ExplanationGuardError(
                f"Guard 5a: đoạn văn dùng marker {marker} nhưng chỉ có {sorted(known) or 'không nguồn nào'}."
            )

    # 3. Quote trong citation phải khớp nguyên văn nguồn đã chấm.
    quotes_by_url: dict[str, set[str]] = {}
    for result in results:
        for source in result.sources:
            quotes_by_url.setdefault(source.url, set()).add(normalise_span(source.quote))
    for citation in citations:
        if normalise_span(citation.quote) not in quotes_by_url.get(citation.url, set()):
            raise QuoteIntegrityError(
                f"Guard 5a: quote của {citation.marker} không khớp nguyên văn nguồn đã chấm ({citation.url})."
            )


def unsupported_note(results: list[ClaimResult]) -> str:
    """Câu nói thẳng khi KHÔNG claim nào có nguồn. Dùng khi bước 7 không có gì để viết."""
    if any(result.verdict in {"supports", "partial"} for result in results):
        return ""
    return NO_SOURCE_NOTE


def summarise_sources(results: list[ClaimResult]) -> list[SourceHit]:
    """Gom mọi nguồn đã chấm, để lưu audit."""
    return [source for result in results for source in result.sources]
