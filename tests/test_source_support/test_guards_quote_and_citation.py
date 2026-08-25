"""Guard 3 (quote ↔ chunk) và Guard 5 (đoạn văn ↔ tập nguồn đã verify). Không tốn API, không có model.

Cả hai lớp này là SO CHUỖI, và đó là điều đáng giá nhất ở chúng: quote sinh ra bằng cách cắt chuỗi từ
trang mình đang giữ, nên không có chỗ nào để model bịa trích dẫn - phép kiểm còn lại chỉ là "chuỗi này
có đúng chuỗi kia không", thứ không thể sai theo kiểu model nói dối.

Vì thế mọi bài ở đây kiểm cùng một dạng hỏng: có gì đó SỬA chuỗi trên đường từ index tới đoạn văn.
Ngày một bài trong này nổ thật là ngày có code chen vào giữa - đúng loại hồi quy sẽ âm thầm biến mọi
trích dẫn thành thứ người đọc không tìm thấy trên trang nguồn.
"""

from __future__ import annotations

import pytest

from src.source_support.explain import (
    CONTRADICTION_WARNING,
    ExplanationGuardError,
    _apply_contradiction_warning,
    build_citations,
    guard_citations,
)
from src.source_support.index import Chunk, DocumentInput, SearchHit, SourceIndex
from src.source_support.quotes import (
    QuoteIntegrityError,
    assert_quote_matches_index,
    assert_quote_within_page,
    select_quote,
)
from src.source_support.schemas import Claim, ClaimResult, Retrieval, SourceHit

QUOTE = "Call 999 if the seizure lasts longer than 5 minutes, or your child does not regain consciousness afterwards."
URL = "https://www.nhs.uk/conditions/febrile-seizures/"


def _chunk(chunk_id: str = "doc-abc-chunk-1", text: str = QUOTE) -> Chunk:
    return Chunk(
        chunk_id=chunk_id, document_id="doc-abc", url=URL,
        title="Febrile seizures", publisher="nhs.uk", text=text,
    )


def _result(verdict: str, *, quote: str = QUOTE, url: str = URL) -> ClaimResult:
    return ClaimResult(
        claim=Claim(claim_en="A febrile seizure needs emergency assessment.", claim_vi="Co giật do sốt cần đánh giá cấp cứu.",
                    claim_kind="red_flag", grounded_in="cần được đánh giá cấp cứu"),
        verdict=verdict,
        retrieval=Retrieval(from_index=True, searched_web=False, best_score=0.61),
        sources=[SourceHit(url=url, title="Febrile seizures", publisher="nhs.uk",
                           chunk_id="doc-abc-chunk-1", quote=quote, verdict=verdict)],
    )


# --- bước 5: chọn quote không dùng model -------------------------------------------------------


def test_select_quote_takes_highest_score() -> None:
    candidates = [
        SearchHit(chunk=_chunk("c1"), score=0.61),
        SearchHit(chunk=_chunk("c2"), score=0.44),
    ]
    assert select_quote(candidates).chunk.chunk_id == "c1"


def test_select_quote_on_no_candidates() -> None:
    assert select_quote([]) is None


# --- Guard 3 -----------------------------------------------------------------------------------


def test_guard3_accepts_verbatim_quote(tmp_path) -> None:
    index = SourceIndex(directory=tmp_path)
    index.chunks.append(_chunk())
    assert assert_quote_matches_index(QUOTE, "doc-abc-chunk-1", index).url == URL


def test_guard3_tolerates_whitespace_reflow(tmp_path) -> None:
    """Xuống dòng và khoảng trắng thừa là thứ mọi tầng hiển thị đều nghịch; chặn vì lý do đó là chặn
    nhầm. Mọi khác biệt còn lại đều là thật."""
    index = SourceIndex(directory=tmp_path)
    index.chunks.append(_chunk())
    assert_quote_matches_index("Call 999 if the seizure lasts longer than 5 minutes,\n   or your child\ndoes not regain consciousness afterwards.", "doc-abc-chunk-1", index)


def test_guard3_raises_on_single_word_change(tmp_path) -> None:
    """Sửa MỘT chữ cũng raise. "5 minutes" thành "15 minutes" là đổi hẳn ngưỡng lâm sàng."""
    index = SourceIndex(directory=tmp_path)
    index.chunks.append(_chunk())
    tampered = QUOTE.replace("5 minutes", "15 minutes")
    with pytest.raises(QuoteIntegrityError, match="Guard 3"):
        assert_quote_matches_index(tampered, "doc-abc-chunk-1", index)


def test_guard3_raises_on_unknown_chunk_id(tmp_path) -> None:
    with pytest.raises(QuoteIntegrityError, match="không có trong index"):
        assert_quote_matches_index(QUOTE, "doc-abc-chunk-99", SourceIndex(directory=tmp_path))


def test_guard3_within_page_at_ingest_time() -> None:
    page = f"Some heading.\n{QUOTE}\nMore text."
    assert_quote_within_page(QUOTE, page, URL)
    with pytest.raises(QuoteIntegrityError, match="Guard 3"):
        assert_quote_within_page("Câu này không có trên trang.", page, URL)


def test_ingest_rejects_chunks_that_are_not_slices(tmp_path, monkeypatch) -> None:
    """Guard 3 tại chỗ nó thật sự có nghĩa: nếu chunking từng SỬA chuỗi thì nạp phải nổ ngay."""
    from src.source_support import index as index_module

    monkeypatch.setattr(index_module, "chunk_text", lambda page, **kwargs: ["đoạn không có trên trang"])
    with pytest.raises(ValueError, match="không phải lát cắt nguyên văn"):
        SourceIndex(directory=tmp_path).add_document(
            document=DocumentInput(url=URL, text="Nội dung thật của trang."), vectors=[[1.0]],
        )


# --- Guard 5a: marker và URL -------------------------------------------------------------------


def test_build_citations_only_numbers_supportive_verdicts() -> None:
    """`unsupported`/`contradicts` KHÔNG được cấp marker - lọc trước khi gọi model, nên model không
    bao giờ nhìn thấy nguồn của chúng để mà trích nhầm."""
    citations, by_claim = build_citations([_result("supports"), _result("unsupported"), _result("contradicts")])
    assert [c.marker for c in citations] == ["[1]"]
    assert len(by_claim) == 1


def test_guard5_accepts_a_clean_paragraph() -> None:
    results = [_result("supports")]
    citations, _ = build_citations(results)
    guard_citations("Vì sao ở mức này:\n- Co giật do sốt cần đánh giá cấp cứu [1]", citations, results)


def test_guard5_raises_on_unverified_url_in_text() -> None:
    """Marker là đường DUY NHẤT dẫn tới nguồn; URL trần trong câu văn là đường đi vòng qua kiểm duyệt."""
    results = [_result("supports")]
    citations, _ = build_citations(results)
    with pytest.raises(ExplanationGuardError, match="URL không thuộc tập đã verify"):
        guard_citations("Theo https://evil.com/bai-viet thì nên nhập viện [1]", citations, results)


def test_guard5_raises_on_invented_marker() -> None:
    """Model tự đặt thêm [2] khi chỉ có một nguồn là gắn trích dẫn không tồn tại vào một câu y khoa."""
    results = [_result("supports")]
    citations, _ = build_citations(results)
    with pytest.raises(ExplanationGuardError, match=r"marker \[2\]"):
        guard_citations("- Mệnh đề một [1]\n- Mệnh đề hai [2]", citations, results)


def test_guard5_raises_when_citation_quote_was_altered() -> None:
    results = [_result("supports")]
    citations, _ = build_citations(results)
    citations[0].quote = QUOTE.replace("999", "115")
    with pytest.raises(QuoteIntegrityError, match="không khớp nguyên văn"):
        guard_citations("- Mệnh đề [1]", citations, results)


def test_guard5_allows_verified_url_written_out() -> None:
    """URL đã qua kiểm thì không bị chặn - cổng chặn URL LẠ, không chặn việc nhắc nguồn thật."""
    results = [_result("supports")]
    citations, _ = build_citations(results)
    guard_citations(f"Xem {URL} [1]", citations, results)


# --- Guard 5b: bắt buộc nói ra khi bị nguồn nói ngược ------------------------------------------


def test_contradiction_warning_is_injected_by_code() -> None:
    """Đặc tả gốc phó thác việc này cho prompt. Ở đây câu cảnh báo do CODE chèn, nên model quên, model
    viết nhẹ đi hay model bỏ hẳn đều không đổi được điều người đọc nhìn thấy."""
    text = _apply_contradiction_warning("Đoạn văn model viết, không hề nhắc gì.", [_result("contradicts")])
    assert CONTRADICTION_WARNING in text


def test_contradiction_warning_absent_when_nothing_contradicts() -> None:
    text = _apply_contradiction_warning("Đoạn văn bình thường.", [_result("supports")])
    assert CONTRADICTION_WARNING not in text


def test_contradiction_warning_not_duplicated() -> None:
    already = f"Đoạn văn.\n\n{CONTRADICTION_WARNING}"
    assert _apply_contradiction_warning(already, [_result("contradicts")]).count(CONTRADICTION_WARNING) == 1


# --- cắt quote về đoạn đọc được ----------------------------------------------------------------


def test_trim_prefers_whole_sentences() -> None:
    """Chunk cắt theo cửa sổ ký tự nên phần lớn mở đầu giữa câu - đo trên corpus thật là 75%."""
    from src.source_support.quotes import trim_to_sentences

    raw = ("nd liver and kidney function tests: To rule out metabolic disorders. "
           "Call 999 if the seizure lasts longer than 5 minutes, or your child does not regain "
           "consciousness afterwards. Take your child to")
    trimmed = trim_to_sentences(raw)
    assert trimmed.startswith("Call 999")
    assert trimmed.endswith("afterwards.")
    assert trimmed in raw, "quote vẫn phải là lát cắt nguyên văn của chunk"


def test_trim_drops_a_dangling_clause_when_there_is_no_sentence() -> None:
    """Danh sách gạch đầu dòng (NHS dùng rất nhiều) không có dấu chấm nào - 20% chunk rơi vào nhóm
    này. Chúng là nội dung TỐT nên không được lọc bỏ, chỉ cắt phần mở đầu cụt."""
    from src.source_support.quotes import trim_to_sentences

    raw = ("and kidney function tests: To rule out metabolic disorders especially if the history "
           "includes recent vomiting or impaired fluid intake")
    trimmed = trim_to_sentences(raw)
    assert not trimmed.startswith("and kidney")
    assert trimmed in raw


def test_trim_never_returns_something_shorter_than_useful() -> None:
    """Cắt quá tay làm mất ngữ cảnh; dưới ngưỡng thì thà giữ nguyên chunk."""
    from src.source_support.quotes import MIN_QUOTE_CHARS, trim_to_sentences

    raw = "Some lead-in text. Short."
    assert len(trim_to_sentences(raw)) >= min(len(raw), MIN_QUOTE_CHARS) or trim_to_sentences(raw) == raw


def test_guard3_accepts_a_trimmed_quote(tmp_path) -> None:
    """Guard 3 nới từ 'bằng nhau' thành 'là lát cắt của chunk' - phép nới KHÔNG làm yếu guard: quote ⊂
    chunk ⊂ trang vẫn là chuỗi so chuỗi thuần."""
    from src.source_support.quotes import trim_to_sentences

    index = SourceIndex(directory=tmp_path)
    index.chunks.append(_chunk(text=f"nd liver function tests. {QUOTE} Take your child to"))
    assert_quote_matches_index(trim_to_sentences(index.chunks[0].text), "doc-abc-chunk-1", index)


def test_guard3_still_rejects_text_not_in_the_chunk(tmp_path) -> None:
    index = SourceIndex(directory=tmp_path)
    index.chunks.append(_chunk())
    with pytest.raises(QuoteIntegrityError, match="Guard 3"):
        assert_quote_matches_index("Câu này không có trong chunk.", "doc-abc-chunk-1", index)
