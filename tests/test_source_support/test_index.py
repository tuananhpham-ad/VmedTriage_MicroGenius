"""Index cục bộ: bất biến chunk, tra cosine, bồi đắp không nhân đôi. Không tốn API, không cần mạng.

BÀI QUAN TRỌNG NHẤT Ở ĐÂY là `test_chunks_are_always_substrings_of_page`. Cả thiết kế part 3 dựa
trên một mệnh đề: *quote là một lát cắt của trang mình đang giữ*, nên nó nguyên văn THEO CẤU TRÚC chứ
không nhờ model tử tế. Nếu chunking từng sửa dù một ký tự thì mệnh đề đó sai, và guard 3/guard 5 -
vốn chỉ là so chuỗi - sẽ bắt đầu chặn nhầm những trích dẫn hoàn toàn đúng.

Các test nhúng vector dùng embedding GIẢ, tất định: mục tiêu là kiểm phần sổ sách của index (thứ tự
hàng, ghép ma trận, chống nhân đôi), không phải kiểm chất lượng model. Nạp model thật vào đây sẽ kéo
torch vào CI và biến một bài test mili-giây thành hàng chục giây.
"""

from __future__ import annotations

import random
import string

import pytest

from src.source_support.index import DocumentInput, SourceIndex, chunk_text, normalise_page

pytest.importorskip("numpy")


def _fake_vectors(count: int, *, seed: int = 0) -> list[list[float]]:
    rng = random.Random(seed)
    return [[rng.random() for _ in range(4)] for _ in range(count)]


def _random_page(rng: random.Random) -> str:
    words = [
        "".join(rng.choices(string.ascii_letters + "áàảãạđêôư", k=rng.randint(1, 12)))
        for _ in range(rng.randint(1, 400))
    ]
    raw = " ".join(words)
    for _ in range(rng.randint(0, 30)):
        position = rng.randrange(len(raw)) if raw else 0
        raw = raw[:position] + rng.choice([". ", "! ", "? ", "\n\n", "   ", "\r\n"]) + raw[position:]
    return normalise_page(raw)


# --- bất biến trụ cột --------------------------------------------------------------------------


def test_chunks_are_always_substrings_of_page() -> None:
    """200 trang ngẫu nhiên, mọi chunk phải là lát cắt nguyên văn. Đây là nền của guard 3 và guard 5."""
    rng = random.Random(42)
    for _ in range(200):
        page = _random_page(rng)
        for piece in chunk_text(page):
            assert piece in page


def test_chunks_cover_the_page_with_overlap() -> None:
    page = normalise_page("A" * 500 + ". " + "B" * 500 + ". " + "C" * 500)
    pieces = chunk_text(page)
    assert len(pieces) > 1, "trang dài hơn cửa sổ thì phải cắt ra nhiều chunk"
    assert page.startswith(pieces[0][:50])
    assert page.rstrip().endswith(pieces[-1][-50:])


def test_short_page_stays_one_chunk() -> None:
    assert chunk_text("Một câu ngắn.") == ["Một câu ngắn."]


def test_empty_page_yields_nothing() -> None:
    assert chunk_text("   \n\n  ") == []


def test_chunk_size_must_exceed_overlap() -> None:
    """size <= overlap thì vòng cắt không tiến lên được - phải nổ chứ không được treo."""
    with pytest.raises(ValueError):
        chunk_text("x" * 100, size=100, overlap=100)


# --- chuẩn hoá trang ---------------------------------------------------------------------------


def test_normalise_page_collapses_whitespace_only() -> None:
    page = normalise_page("Trẻ  dưới   5 tuổi.\r\n\r\n\r\n\r\nCo giật   kéo dài.")
    assert "  " not in page
    assert "\n\n\n" not in page
    assert "\r" not in page
    # Không đụng dấu câu, không hạ chữ hoa, không bỏ dấu tiếng Việt.
    assert "Trẻ dưới 5 tuổi." in page
    assert "Co giật kéo dài." in page


# --- sổ sách của index -------------------------------------------------------------------------


def test_add_document_indexes_chunks(tmp_path) -> None:
    index = SourceIndex(directory=tmp_path)
    page = "Câu một. " * 200
    pieces = chunk_text(normalise_page(page))
    added = index.add_document(
        document=DocumentInput(url="https://nhs.uk/a", text=page, title="A", publisher="NHS"),
        vectors=_fake_vectors(len(pieces)),
    )
    assert len(added) == len(pieces)
    assert len(index) == len(pieces)
    assert index.vectors.shape[0] == len(pieces)
    assert all(chunk.url == "https://nhs.uk/a" for chunk in added)
    assert len({chunk.chunk_id for chunk in added}) == len(added), "chunk_id phải phân biệt"


def test_add_document_is_idempotent_per_url(tmp_path) -> None:
    """Cùng URL nạp hai lần không nhân đôi - index là cache tự bồi đắp, không phải hàng đợi nạp."""
    index = SourceIndex(directory=tmp_path)
    page = "Câu một. " * 200
    pieces = chunk_text(normalise_page(page))
    document = DocumentInput(url="https://nhs.uk/a", text=page)
    index.add_document(document=document, vectors=_fake_vectors(len(pieces)))
    before = len(index)
    assert index.add_document(document=document, vectors=_fake_vectors(len(pieces))) == []
    assert len(index) == before


def test_add_document_rejects_vector_count_mismatch(tmp_path) -> None:
    index = SourceIndex(directory=tmp_path)
    with pytest.raises(ValueError, match="không khớp số chunk"):
        index.add_document(
            document=DocumentInput(url="https://nhs.uk/a", text="Câu một. " * 200),
            vectors=_fake_vectors(1),
        )


def test_document_id_is_stable_across_runs(tmp_path) -> None:
    """`chunk_id` đi vào trích dẫn đã lưu, nên nó phải suy ra tất định từ URL: một lần nạp lại corpus
    theo thứ tự khác không được làm mọi audit cũ trỏ sai chunk."""
    first = SourceIndex(directory=tmp_path / "a")
    second = SourceIndex(directory=tmp_path / "b")
    page = "Câu một. " * 50
    pieces = chunk_text(normalise_page(page))
    document = DocumentInput(url="https://nhs.uk/same", text=page)
    added_first = first.add_document(document=document, vectors=_fake_vectors(len(pieces)))
    added_second = second.add_document(document=document, vectors=_fake_vectors(len(pieces)))
    assert [chunk.chunk_id for chunk in added_first] == [chunk.chunk_id for chunk in added_second]


# --- tra cứu -----------------------------------------------------------------------------------


def test_search_ranks_by_cosine(tmp_path) -> None:
    index = SourceIndex(directory=tmp_path)
    page = "Alpha. Beta. Gamma. " * 60
    pieces = chunk_text(normalise_page(page))
    vectors = [[1.0, 0.0, 0.0, 0.0] for _ in pieces]
    vectors[1] = [0.0, 1.0, 0.0, 0.0]
    index.add_document(document=DocumentInput(url="https://nhs.uk/a", text=page), vectors=vectors)

    hits = index.search([0.0, 1.0, 0.0, 0.0], top_k=2)
    assert hits[0].chunk.chunk_id == index.chunks[1].chunk_id
    assert hits[0].score > hits[1].score


def test_search_on_empty_index_returns_nothing(tmp_path) -> None:
    assert SourceIndex(directory=tmp_path).search([1.0, 0.0], top_k=3) == []


# --- bền vững ----------------------------------------------------------------------------------


def test_save_then_load_round_trips(tmp_path) -> None:
    index = SourceIndex(directory=tmp_path)
    page = "Câu một. " * 200
    pieces = chunk_text(normalise_page(page))
    index.add_document(
        document=DocumentInput(url="https://nhs.uk/a", text=page, title="A", publisher="NHS"),
        vectors=_fake_vectors(len(pieces)),
    )
    index.save()

    reloaded = SourceIndex.load(tmp_path)
    assert len(reloaded) == len(index)
    assert reloaded.vectors.shape == index.vectors.shape
    assert [c.chunk_id for c in reloaded.chunks] == [c.chunk_id for c in index.chunks]
    assert reloaded.has_document("https://nhs.uk/a")
    # Chunk vẫn tra ra được chính nó sau một vòng ghi/đọc.
    assert reloaded.search(index.vectors[0].tolist(), top_k=1)[0].chunk.text == index.chunks[0].text


def test_load_missing_files_gives_empty_index(tmp_path) -> None:
    """Chưa nạp corpus bao giờ là trạng thái bình thường của lần chạy đầu, không phải lỗi."""
    index = SourceIndex.load(tmp_path)
    assert len(index) == 0
    assert index.vectors is None


def test_load_raises_when_corpus_and_vectors_disagree(tmp_path) -> None:
    """Lệch một dòng là mọi trích dẫn từ đó trở đi gắn SAI nguồn - hỏng im lặng đúng kiểu tệ nhất cho
    một hệ trích dẫn. Phải chết lúc nạp."""
    import numpy as np

    index = SourceIndex(directory=tmp_path)
    page = "Câu một. " * 200
    pieces = chunk_text(normalise_page(page))
    index.add_document(document=DocumentInput(url="https://nhs.uk/a", text=page), vectors=_fake_vectors(len(pieces)))
    index.save()
    np.save(index.embeddings_path, index.vectors[:-1])

    with pytest.raises(ValueError, match="Index hỏng"):
        SourceIndex.load(tmp_path)


def test_chunks_never_start_mid_word() -> None:
    """Chunk mở đầu giữa từ vẫn là lát cắt hợp lệ và vẫn qua mọi guard - nhưng nó là chuỗi được đem đi
    TRÍCH DẪN NGUYÊN VĂN cho điều dưỡng đọc.

    Lỗi thật gặp phải khi chạy ca đầu tiên (2026-08-19): quote hiện ra là "nd liver and kidney function
    tests..." và "g enzyme inhibitors, beta-blockers..." - đuôi của "and" và "converting enzyme".
    Nguyên nhân: chồng lấn tính bằng cách lùi `overlap` ký tự từ điểm cắt trước, và con số đó rơi vào
    giữa từ nhiều hơn là không."""
    rng = random.Random(7)
    for _ in range(200):
        page = _random_page(rng)
        for piece in chunk_text(page):
            position = page.index(piece)
            assert position == 0 or page[position - 1].isspace(), f"chunk mở đầu giữa từ: {piece[:40]!r}"


def test_chunk_start_snapping_keeps_substring_invariant() -> None:
    """Nắn điểm bắt đầu KHÔNG được phá bất biến trụ cột."""
    page = normalise_page("Angiotensin converting enzyme inhibitors, beta-blockers, methyldopa. " * 40)
    pieces = chunk_text(page)
    assert len(pieces) > 1
    assert all(piece in page for piece in pieces)


# --- lọc rác lúc nạp ---------------------------------------------------------------------------


def test_bibliography_chunks_are_filtered_out() -> None:
    """Mục thư mục lọt vào index thì có ngày nó thành trích dẫn hiện trên màn hình điều dưỡng.

    Đây là lỗi ĐO ĐƯỢC trên ca dị ứng da (2026-08-19), không phải giả định: trích dẫn sinh ra là
    "...Cutaneous adverse events caused by immune checkpoint inhibitors. J Am Acad Dermatol.
    2021;85(4):956-966" - không khẳng định điều gì lâm sàng, mà bước chấm vẫn gật supports."""
    from src.source_support.index import looks_like_bibliography

    assert looks_like_bibliography(
        "Johnson DB, LeBoeuf NR. Cutaneous adverse events. J Am Acad Dermatol . 2021;85(4):956-966. "
        "doi:10.1016/j.jaad.2020.09.054"
    )
    assert looks_like_bibliography(
        "M, Rezaei N . Genetic background of febrile seizures. Rev Neurosci . 2014;25(1):129-161. "
        "doi:10.1515/revneuro-2013-0053"
    )


def test_clinical_text_is_not_mistaken_for_bibliography() -> None:
    """Ngưỡng đặt chặt là cố ý: loại nhầm nội dung thật đắt hơn giữ lại một chunk rác, vì bước chấm
    vẫn còn cơ hội gạt chunk rác còn nội dung đã loại thì không quay lại được."""
    from src.source_support.index import looks_like_bibliography

    assert not looks_like_bibliography(
        "Call 999 if the seizure lasts longer than 5 minutes, or your child does not regain "
        "consciousness afterwards."
    )
    assert not looks_like_bibliography(
        "A 2014 review found that febrile seizures occur in 2 to 5% of children aged 6 months to 5 years."
    )


def test_ingest_drops_bibliography_chunks(tmp_path) -> None:
    page = (
        "Febrile seizures occur in young children during fever. " * 20
        + "References. Johnson DB, LeBoeuf NR. J Am Acad Dermatol . 2021;85(4):956-966. "
          "doi:10.1016/j.jaad.2020.09.054. Smith AB. Rev Neurosci . 2014;25(1):129-161. doi:10.1515/rev"
    )
    from src.source_support.index import prepare_chunks

    index = SourceIndex(directory=tmp_path)
    _, pieces = prepare_chunks(page)
    kept = index.add_document(
        document=DocumentInput(url="https://msdmanuals.com/a", text=page),
        vectors=_fake_vectors(len(pieces)),
    )
    assert kept, "nội dung lâm sàng phải còn lại"
    assert not any("J Am Acad Dermatol" in chunk.text for chunk in kept)


# --- chống nạp trùng nội dung -------------------------------------------------------------------


def test_same_content_under_different_urls_is_ingested_once(tmp_path) -> None:
    """`has_document` chỉ so chuỗi URL, nên cùng một trang dưới nhiều dạng địa chỉ sẽ vào index nhiều
    lần. Đo thật 2026-08-19: một lần search về bỏng nạp "5 tài liệu" mà thực chất là 2 trang
    (`/NBK430773/`, `?report=printable`, `?report=reader`, `/NBK430730/`, `/sites/books/NBK430730/`)
    - 204 chunk cho phần nội dung đáng lẽ ~80.

    Tệ hơn tốn chỗ: cùng một đoạn văn xuất hiện ba lần thì nó chiếm ba suất trong top-k của bước tra,
    đẩy các nguồn KHÁC ra ngoài - trùng lặp làm nghèo tập ứng viên đưa sang bước chấm."""
    from src.source_support.index import prepare_chunks

    page = "Bỏng sâu diện rộng cần điều trị cấp cứu ngay. " * 60
    _, pieces = prepare_chunks(page)
    vectors = _fake_vectors(len(pieces))

    index = SourceIndex(directory=tmp_path)
    assert index.add_document(document=DocumentInput(url="https://nhs.uk/a", text=page), vectors=vectors)
    for variant in ("https://nhs.uk/a?report=printable", "https://nhs.uk/a?report=reader", "https://nhs.uk/sites/a"):
        assert index.add_document(document=DocumentInput(url=variant, text=page), vectors=vectors) == []
    assert len(index) == len(pieces)


def test_dedup_survives_save_and_load(tmp_path) -> None:
    """Vân tay phải sống sót vòng ghi/đọc - giữ trong RAM thì mỗi lần khởi động lại là mất, và index
    sẽ lại phình ra sau vài lần chạy."""
    from src.source_support.index import prepare_chunks

    page = "Bỏng sâu diện rộng cần điều trị cấp cứu ngay. " * 60
    _, pieces = prepare_chunks(page)
    vectors = _fake_vectors(len(pieces))

    index = SourceIndex(directory=tmp_path)
    index.add_document(document=DocumentInput(url="https://nhs.uk/a", text=page), vectors=vectors)
    index.save()

    reloaded = SourceIndex.load(tmp_path)
    assert reloaded.add_document(document=DocumentInput(url="https://nhs.uk/a?x=1", text=page), vectors=vectors) == []
    assert len(reloaded) == len(pieces)


def test_different_content_still_gets_in(tmp_path) -> None:
    """Cổng chống trùng không được chặn nội dung KHÁC - loại nhầm nguồn thật đắt hơn nhiều."""
    from src.source_support.index import prepare_chunks

    index = SourceIndex(directory=tmp_path)
    for url, body in [("https://nhs.uk/a", "Nội dung về bỏng. " * 60), ("https://nhs.uk/b", "Nội dung về sốt. " * 60)]:
        _, pieces = prepare_chunks(body)
        assert index.add_document(document=DocumentInput(url=url, text=body), vectors=_fake_vectors(len(pieces)))
    assert len(index.urls) == 2
