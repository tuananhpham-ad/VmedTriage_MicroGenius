"""Index y văn cục bộ: hai file song song + cosine bằng numpy. KHÔNG gọi mạng, KHÔNG cần vector DB.

VÌ SAO KHÔNG DÙNG WEAVIATE dù dự án đã có: collection `knowledge` phục vụ luồng hỏi-đáp và sống trên
Weaviate Cloud, tức mỗi lần tra là một vòng mạng và một phụ thuộc dịch vụ ngoài. Part 3 tra 3 lần mỗi
ca trên một corpus cỡ vài nghìn chunk - ở quy mô đó `numpy.dot` trên ma trận nằm sẵn trong RAM nhanh
hơn nhiều lần và không hỏng khi mạng hỏng. Đây là quyết định có chủ đích, không phải bỏ sót: nếu
corpus vượt vài chục nghìn chunk thì cân lại.

HAI FILE SONG SONG, CÙNG THỨ TỰ DÒNG:

    corpus.jsonl     dòng i = metadata + text của chunk i
    embeddings.npy   hàng i = vector đã chuẩn hoá L2 của chunk i

Bất biến `len(corpus) == embeddings.shape[0]` được kiểm lúc nạp và raise nếu lệch. Lệch một dòng là
mọi trích dẫn từ đó trở đi gắn sai nguồn - hỏng im lặng đúng kiểu tệ nhất cho một hệ trích dẫn, nên
thà chết lúc khởi động.

CHUNK LÀ LÁT CẮT NGUYÊN VĂN CỦA TRANG. `chunk_text` chỉ CẮT chuỗi, không sửa một ký tự nào. Nhờ vậy
"quote nằm trong trang" đúng THEO CẤU TRÚC chứ không nhờ model tử tế - đó là trụ của cả thiết kế
part 3, và là lý do guard 3/guard 5 chỉ còn là so chuỗi. Việc chuẩn hoá khoảng trắng làm ĐÚNG MỘT LẦN
ở `normalise_page` lúc nạp; từ đó trở đi trang đã chuẩn hoá là văn bản gốc duy nhất.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.paths import SOURCE_INDEX_DIR

logger = logging.getLogger("vmedtriage.source_support")

CORPUS_FILE = "corpus.jsonl"
EMBEDDINGS_FILE = "embeddings.npy"

CHUNK_CHARS = 800
"""Cửa sổ chunk. Đủ dài để một câu trích có ngữ cảnh, đủ ngắn để cosine còn sắc - đoạn càng dài thì
vector càng trung bình hoá và càng khó phân biệt."""

CHUNK_OVERLAP = 150
"""Chồng lấn, để một câu nằm vắt qua ranh giới không bị cắt đôi ở cả hai chunk."""

_SENTENCE_END = re.compile(r"[.!?]\s")
_WHITESPACE = re.compile(r"[ \t]+")
_BLANK_LINES = re.compile(r"\n{3,}")


def normalise_page(text: str) -> str:
    """Chuẩn hoá trang ĐÚNG MỘT LẦN lúc nạp. Sau bước này, chuỗi trả về LÀ văn bản gốc.

    Chỉ gộp khoảng trắng ngang và dòng trống thừa - không đụng dấu câu, không hạ chữ hoa, không bỏ
    dấu tiếng Việt. Mọi phép so verbatim phía sau (guard 3, guard 5) đều so với chính chuỗi này, nên
    càng ít biến đổi thì trích dẫn càng gần bản người đọc thấy trên trang."""
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = _WHITESPACE.sub(" ", cleaned)
    cleaned = "\n".join(line.strip() for line in cleaned.split("\n"))
    return _BLANK_LINES.sub("\n\n", cleaned).strip()


def _snap_to_sentence(page: str, start: int, end: int) -> int:
    """Đẩy điểm cắt về ranh giới câu GẦN NHẤT phía trước, nếu có trong nửa sau của cửa sổ.

    Giới hạn "nửa sau" là cố ý: không tìm thấy dấu câu nào thì cắt cứng theo độ dài còn hơn là tạo ra
    một chunk dài gấp đôi hoặc ngắn một nửa. Trang y văn có bảng và danh sách gạch đầu dòng, ở đó dấu
    chấm thưa hẳn."""
    if end >= len(page):
        return len(page)
    window_floor = start + (end - start) // 2
    matches = list(_SENTENCE_END.finditer(page, window_floor, end))
    return matches[-1].end() if matches else end


def _snap_start_to_word(page: str, start: int) -> int:
    """Đẩy điểm BẮT ĐẦU tới ranh giới từ gần nhất phía sau.

    Vì sao cần: chồng lấn được tính bằng cách lùi lại `overlap` ký tự từ điểm cắt trước, và con số đó
    rơi vào giữa từ nhiều hơn là không. Không nắn thì chunk mở đầu bằng "nd liver and kidney..." hay
    "g enzyme inhibitors..." - và đó chính là chuỗi được đem đi trích dẫn nguyên văn cho điều dưỡng
    đọc. Vẫn là lát cắt hợp lệ của trang, vẫn qua mọi guard, nhưng đọc lên như bị hỏng.

    Nắn TIẾN chứ không lùi: lùi lại sẽ lấn sang từ đã thuộc chunk trước và làm phần chồng lấn dài hơn
    dự tính."""
    if start <= 0 or start >= len(page):
        return start
    if page[start - 1].isspace():
        return start
    cursor = start
    while cursor < len(page) and not page[cursor].isspace():
        cursor += 1
    while cursor < len(page) and page[cursor].isspace():
        cursor += 1
    return cursor


def chunk_text(page: str, *, size: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Cắt trang thành các lát CHỒNG LẤN. Mọi phần tử trả về là substring nguyên văn của `page`.

    Bất biến này được test khẳng định trên dữ liệu ngẫu nhiên (`test_chunks_are_substrings`); nó là
    thứ làm guard 3 không bao giờ có thể sai vì lý do chunking."""
    if size <= overlap:
        raise ValueError("size phải lớn hơn overlap, nếu không vòng cắt không tiến lên được.")
    page = page.strip()
    if not page:
        return []
    if len(page) <= size:
        return [page]

    chunks: list[str] = []
    start = 0
    while start < len(page):
        end = _snap_to_sentence(page, start, min(start + size, len(page)))
        piece = page[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(page):
            break
        start = _snap_start_to_word(page, max(end - overlap, start + 1))
    return chunks


_JOURNAL_CITATION = re.compile(r"\b\d{4};\s?\d+")
"""Dạng "2014;25(1):129-161" - gần như chỉ xuất hiện trong danh mục tài liệu tham khảo."""

_DOI_OR_PMID = re.compile(r"\b(doi:|doi\.org|PMID)", re.I)


def looks_like_bibliography(text: str) -> bool:
    """Chunk này là danh mục tài liệu tham khảo chứ không phải nội dung lâm sàng?

    VÌ SAO CẦN. Trang MSD đính danh mục tham khảo dài ở cuối mỗi bài. Chúng vào index như mọi chunk
    khác, và vì dày đặc thuật ngữ y khoa nên cosine với một claim lâm sàng vẫn cao. Kết quả đo thật
    trên ca dị ứng da (2026-08-19): trích dẫn hiện ra cho điều dưỡng là
    *"...Cutaneous adverse events caused by immune checkpoint inhibitors. J Am Acad Dermatol. 2021;85(4):956-966"*
    - một mục thư mục, không khẳng định điều gì về lâm sàng cả, mà bước chấm vẫn gật `supports`.

    Ngưỡng đặt ở HAI dấu hiệu trở lên, cố ý chặt: một bài lâm sàng hoàn toàn có thể nhắc một mốc năm
    hoặc một DOI giữa đoạn, và loại nhầm nội dung thật đắt hơn nhiều so với giữ lại một chunk rác -
    bước 6 vẫn còn cơ hội gạt chunk rác, còn nội dung đã bị loại thì không quay lại được."""
    signals = len(_JOURNAL_CITATION.findall(text)) + len(_DOI_OR_PMID.findall(text))
    return signals >= 2


def content_fingerprint(text: str) -> str:
    """Vân tay nội dung của một trang, dùng để chống nạp trùng.

    VÌ SAO KHÔNG CHỈ SO URL. `has_document` so chuỗi URL, nên cùng một trang dưới nhiều dạng địa chỉ
    sẽ vào index nhiều lần. Đo thật 2026-08-19, một lần search về bỏng nạp "5 tài liệu" mà thực chất
    là 2 trang:

        .../books/NBK430773/
        .../books/NBK430773/?report=printable
        .../books/NBK430773/?report=reader
        .../books/NBK430730/
        .../sites/books/NBK430730/

    204 chunk cho phần nội dung đáng lẽ chỉ ~80. Tệ hơn tốn chỗ: cùng một đoạn văn xuất hiện ba lần
    thì nó chiếm ba suất trong top-k của bước tra, đẩy các nguồn KHÁC ra ngoài - tức trùng lặp làm
    nghèo đi tập ứng viên đưa sang bước chấm.

    Vân tay tính trên TEXT ĐÃ CHUẨN HOÁ chứ không trên URL, nên nó bắt được mọi biến thể địa chỉ mà
    không cần đoán tham số nào là nhiễu."""
    import hashlib

    return hashlib.sha256(normalise_page(text).encode("utf-8")).hexdigest()


def prepare_chunks(text: str) -> tuple[str, list[str]]:
    """Chuẩn hoá trang rồi cắt thành các chunk ĐÃ LỌC. Trả về (trang, chunk).

    ĐIỂM VÀO DUY NHẤT để biết một trang cho ra những chunk nào. Người gọi nhúng vector Ở NGOÀI (nhúng
    theo lô rẻ hơn nhiều), nên nếu `add_document` tự lọc thêm một lần nữa bên trong thì số vector và
    số chunk lệch nhau - đúng lỗi đã gặp. Cả hai phía cùng gọi hàm này thì hai danh sách luôn khớp
    theo cấu trúc, không phải nhờ người viết nhớ."""
    page = normalise_page(text)
    return page, [piece for piece in chunk_text(page) if not looks_like_bibliography(piece)]


@dataclass(frozen=True, slots=True)
class Chunk:
    """Một dòng của `corpus.jsonl`. `text` là lát cắt nguyên văn của trang đã chuẩn hoá."""

    chunk_id: str
    document_id: str
    url: str
    title: str
    publisher: str
    text: str
    retrieved_at: str = ""
    content_hash: str = ""
    """Vân tay của TRANG mà chunk này cắt ra. Lưu xuống đĩa để phép chống trùng còn hiệu lực sau khi
    nạp lại index - nếu chỉ giữ trong RAM thì mỗi lần khởi động lại là mất."""

    def as_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id, "document_id": self.document_id, "url": self.url,
            "title": self.title, "publisher": self.publisher, "text": self.text,
            "retrieved_at": self.retrieved_at, "content_hash": self.content_hash,
        }


@dataclass(frozen=True, slots=True)
class SearchHit:
    chunk: Chunk
    score: float


@dataclass
class SourceIndex:
    """Corpus + ma trận vector, nạp một lần rồi tra trong RAM."""

    directory: Path = field(default_factory=lambda: SOURCE_INDEX_DIR)
    chunks: list[Chunk] = field(default_factory=list)
    vectors: Any = None
    """`numpy.ndarray` (N, D) float32 đã chuẩn hoá L2, hoặc `None` khi index rỗng."""

    _fingerprints: set[str] = field(default_factory=set, repr=False)
    """Vân tay nội dung các trang ĐÃ nạp, để chống trùng - xem `content_fingerprint`."""

    _pages: dict[str, str] = field(default_factory=dict, repr=False)
    """url -> trang đã chuẩn hoá, CHỈ trong phiên hiện tại và KHÔNG được ghi xuống đĩa.

    Guard 3 ("quote nằm trong trang") chỉ có ý nghĩa ở đúng thời điểm nạp, khi còn cầm nguyên trang
    trong tay; sau đó quote LÀ một chunk nên phép kiểm ở lúc chạy là guard 5 (quote khớp verbatim
    chunk). Lưu cả trang xuống đĩa chỉ để lặp lại một phép kiểm đã làm rồi là nhân đôi dung lượng
    corpus mà không mua thêm bảo đảm nào."""

    @property
    def corpus_path(self) -> Path:
        return self.directory / CORPUS_FILE

    @property
    def embeddings_path(self) -> Path:
        return self.directory / EMBEDDINGS_FILE

    def __len__(self) -> int:
        return len(self.chunks)

    @property
    def urls(self) -> set[str]:
        return {chunk.url for chunk in self.chunks}

    def page_of(self, url: str) -> str:
        """Trang đã chuẩn hoá của một URL nếu nó được nạp TRONG phiên này, ngược lại chuỗi rỗng."""
        return self._pages.get(url, "")

    # ---------- nạp / ghi ----------

    @classmethod
    def load(cls, directory: Path | None = None) -> SourceIndex:
        """Nạp index từ đĩa. Thiếu file = index rỗng (hợp lệ), lệch số dòng = raise.

        Phân biệt hai trường hợp đó là quan trọng: chưa nạp corpus bao giờ là trạng thái bình thường
        của lần chạy đầu, còn corpus lệch embedding là hỏng dữ liệu và mọi trích dẫn sau đó gắn sai
        nguồn."""
        import numpy as np

        directory = directory or SOURCE_INDEX_DIR
        index = cls(directory=directory)
        corpus_path = directory / CORPUS_FILE
        embeddings_path = directory / EMBEDDINGS_FILE
        if not corpus_path.is_file() or not embeddings_path.is_file():
            return index

        for line in corpus_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                index.chunks.append(Chunk(**json.loads(line)))
        index._fingerprints = {chunk.content_hash for chunk in index.chunks if chunk.content_hash}
        vectors = np.load(embeddings_path)
        if vectors.shape[0] != len(index.chunks):
            raise ValueError(
                f"Index hỏng: {corpus_path.name} có {len(index.chunks)} dòng nhưng "
                f"{embeddings_path.name} có {vectors.shape[0]} vector. Nạp lại corpus bằng "
                f"scripts/build_source_corpus.py --rebuild."
            )
        index.vectors = vectors
        return index

    def save(self) -> None:
        """Ghi cả hai file. Ghi ra file tạm rồi đổi tên để không bao giờ để lại cặp file lệch nhau.

        Nếu ghi thẳng đè, một lần ngắt giữa chừng (Ctrl-C, hết pin) sẽ để lại corpus mới cạnh
        embedding cũ - đúng trạng thái mà `load` phải raise, và người sau phải nạp lại toàn bộ."""
        import numpy as np

        self.directory.mkdir(parents=True, exist_ok=True)
        corpus_tmp = self.corpus_path.with_suffix(".jsonl.tmp")
        embeddings_tmp = self.embeddings_path.with_suffix(".npy.tmp")

        payload = "\n".join(json.dumps(chunk.as_dict(), ensure_ascii=False) for chunk in self.chunks)
        corpus_tmp.write_text(payload + ("\n" if payload else ""), encoding="utf-8")
        vectors = self.vectors if self.vectors is not None else np.zeros((0, 1), dtype="float32")
        # Ghi qua FILE HANDLE, không đưa đường dẫn: `np.save` tự nối đuôi ".npy" vào tên nào chưa có
        # đuôi đó, nên "embeddings.npy.tmp" sẽ lặng lẽ thành "embeddings.npy.tmp.npy" và bước đổi tên
        # bên dưới không tìm thấy file. Handle thì nó ghi đúng chỗ được đưa.
        with embeddings_tmp.open("wb") as handle:
            np.save(handle, vectors)

        corpus_tmp.replace(self.corpus_path)
        embeddings_tmp.replace(self.embeddings_path)

    # ---------- tra ----------

    def search(self, vector: list[float], *, top_k: int = 5) -> list[SearchHit]:
        """Cosine giữa `vector` và toàn bộ index, trả `top_k` chunk điểm cao nhất.

        Chỉ một phép nhân ma trận: vector đã được `embedding.embed_many` chuẩn hoá L2 sẵn nên tích vô
        hướng CHÍNH LÀ cosine, không cần chia chuẩn lần nào nữa."""
        import numpy as np

        if self.vectors is None or not self.chunks:
            return []
        scores = self.vectors @ np.asarray(vector, dtype=self.vectors.dtype)
        ranked = np.argsort(scores)[::-1][:top_k]
        return [SearchHit(chunk=self.chunks[int(i)], score=float(scores[int(i)])) for i in ranked]

    # ---------- bồi đắp ----------

    def has_document(self, url: str) -> bool:
        return url in self.urls

    def add_document(
        self,
        *,
        document: DocumentInput,
        vectors: list[list[float]] | None = None,
    ) -> list[Chunk]:
        """Cắt + nạp một trang vào index. Trả về các chunk vừa thêm (rỗng nếu URL đã có).

        Không nhân đôi theo URL: mỗi lần một claim tra trượt rồi đi search, kết quả được ghi lại đây,
        nên cùng một trang rất dễ được đề xuất lại ở ca sau. Bỏ qua im lặng là đúng hành vi mong muốn
        - đây là cache tự bồi đắp, không phải hàng đợi nạp.

        `vectors` cho phép người gọi nhúng theo lô ở ngoài (nhanh hơn nhiều khi nạp corpus hàng loạt);
        bỏ trống thì tự nhúng."""
        import numpy as np

        if self.has_document(document.url):
            return []
        page, pieces = prepare_chunks(document.text)
        if not pieces:
            return []
        fingerprint = content_fingerprint(document.text)
        if fingerprint in self._fingerprints:
            logger.info("source_support.duplicate_content url=%s", document.url)
            return []

        # Guard 3 tại ĐÚNG chỗ nó có nghĩa: lúc còn cầm nguyên trang. Sai ở đây là lỗi chunking, và
        # nó phải nổ ngay chứ không được đi tiếp thành một trích dẫn không truy được về trang nguồn.
        for piece in pieces:
            if piece not in page:
                raise ValueError(f"Chunk không phải lát cắt nguyên văn của trang: {document.url}")

        if vectors is None:
            from src.source_support.embedding import embed_many

            vectors = embed_many(pieces)
        if len(vectors) != len(pieces):
            raise ValueError(f"Số vector ({len(vectors)}) không khớp số chunk ({len(pieces)}).")

        document_id = _document_id(document.url)
        added = [
            Chunk(
                chunk_id=f"{document_id}-chunk-{position}",
                document_id=document_id,
                url=document.url,
                title=document.title,
                publisher=document.publisher,
                text=piece,
                retrieved_at=document.retrieved_at,
                content_hash=fingerprint,
            )
            for position, piece in enumerate(pieces, start=1)
        ]
        self.chunks.extend(added)
        self._pages[document.url] = page
        self._fingerprints.add(fingerprint)

        block = np.asarray(vectors, dtype="float32")
        self.vectors = block if self.vectors is None else np.vstack([self.vectors, block])
        return added


@dataclass(frozen=True, slots=True)
class DocumentInput:
    """Một trang đã fetch và bóc text, sẵn sàng nạp vào index."""

    url: str
    text: str
    title: str = ""
    publisher: str = ""
    retrieved_at: str = ""


def _document_id(url: str) -> str:
    """Định danh tài liệu suy ra TẤT ĐỊNH từ URL - cùng URL luôn cho cùng id, kể cả giữa các lần chạy.

    Dùng hash thay vì số thứ tự tăng dần vì `chunk_id` đi vào trích dẫn đã lưu: số thứ tự sẽ đổi
    nghĩa sau một lần nạp lại corpus theo thứ tự khác, làm mọi audit cũ trỏ sai chunk."""
    import hashlib

    return "doc-" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
