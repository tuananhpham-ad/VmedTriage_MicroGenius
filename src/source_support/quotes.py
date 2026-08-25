"""Bước 5 - chọn quote. **KHÔNG có model nào ở đây.** Và **Guard 3**.

ĐÂY LÀ QUYẾT ĐỊNH THIẾT KẾ QUAN TRỌNG NHẤT CỦA CẢ PART 3. Sau khi fetch, hệ thống đã cầm text trong
tay; chunk có cosine cao nhất *chính là* quote. Không cần model đọc để chọn, và vì thế:

* quote nguyên văn **theo cấu trúc**, không nhờ model tử tế - nó là một lát cắt của chuỗi mình đang
  giữ, nên không còn chỗ nào để bịa trích dẫn;
* hai lớp guard phía sau (3 và 5) tụt xuống thành **so chuỗi** - thứ không thể sai theo kiểu model
  nói dối.

Đổi bước này sang "cho model đọc các đoạn rồi chọn câu đắt nhất" là tháo bỏ đúng tính chất đó, kể cả
khi câu nó chọn đẹp hơn.

GUARD 3 LÀ THỪA THEO THIẾT KẾ, VÀ ĐƯỢC GIỮ LẠI CHÍNH VÌ THẾ. Nếu chunking đúng thì nó không bao giờ
nổ. Ngày nó nổ là ngày ai đó vô tình làm chunk khác đi so với văn bản gốc - đúng loại hồi quy sẽ âm
thầm biến mọi trích dẫn thành thứ người đọc không tìm thấy trên trang. Nó `raise` chứ không cảnh báo.

KHÔNG CÓ BƯỚC RERANK. Bản trước có tuỳ chọn dùng `AITeamVN/Vietnamese_Reranker`; đã bỏ vì cùng lý do
đã bỏ bi-encoder tiếng Việt: corpus v1 là tài liệu tiếng Anh, còn đó là cross-encoder tiếng Việt (xem
`embedding.py`). Muốn xếp lại ứng viên thì phải chọn model đúng ngôn ngữ và ĐO trước, không dựng sẵn
một cái cờ mặc định tắt rồi quên mất là nó sai.
"""

from __future__ import annotations

import re

from src.graph_triage.graph_schema import normalise_span
from src.source_support.index import Chunk, SearchHit, SourceIndex

_SENTENCE_START = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
_SENTENCE_END = re.compile(r"[.!?](?=\s|$)")

MIN_QUOTE_CHARS = 80
"""Dưới ngưỡng này thì cắt về câu trọn vẹn làm mất quá nhiều ngữ cảnh, thà giữ nguyên chunk."""


class QuoteIntegrityError(RuntimeError):
    """Guard 3 hoặc guard 5 phát hiện quote không còn khớp nguồn.

    Luôn là lỗi LẬP TRÌNH, không phải lỗi dữ liệu: quote sinh ra bằng cách cắt chuỗi, nên nó chỉ có
    thể lệch khi có code sửa nó trên đường đi. Vì thế raise chứ không bỏ qua ứng viên."""


def select_quote(candidates: list[SearchHit]) -> SearchHit | None:
    """Bước 5: lấy ứng viên điểm cao nhất. Không gọi model, không cắt lại chuỗi.

    `candidates` đã được `index.search` xếp giảm dần, nên đây chỉ là lấy phần tử đầu - viết thành hàm
    riêng để chỗ này có tên gọi và có chỗ để test, chứ không phải vì nó phức tạp."""
    return candidates[0] if candidates else None


def trim_to_sentences(text: str) -> str:
    """Cắt một chunk về các CÂU TRỌN VẸN. Kết quả luôn là substring nguyên văn của chunk.

    VÌ SAO CẦN. Chunk cắt theo cửa sổ ký tự nên phần lớn mở đầu giữa câu - đo trên corpus thật là
    **75%**. Chunk như vậy vẫn tra tốt (cosine không quan tâm câu bắt đầu ở đâu), nhưng nó là chuỗi
    được đem đi TRÍCH DẪN cho điều dưỡng đọc, và một trích dẫn mở đầu bằng "...and liver function
    tests" đọc lên như trích sai.

    Bất biến trụ cột KHÔNG bị phá: kết quả vẫn là lát cắt nguyên văn của chunk, mà chunk là lát cắt
    nguyên văn của trang. Quote vẫn nguyên văn THEO CẤU TRÚC, chỉ là lát cắt gọn hơn.

    Không tìm được câu trọn vẹn nào đủ dài thì trả nguyên chunk - thà trích dẫn hơi thô còn hơn trích
    dẫn cụt nghĩa."""
    stripped = text.strip()
    first = _SENTENCE_START.search(stripped)
    start = first.end() if first else _clause_start(stripped)
    ends = list(_SENTENCE_END.finditer(stripped, start))
    end = ends[-1].end() if ends else len(stripped)
    candidate = stripped[start:end].strip()
    return candidate if len(candidate) >= MIN_QUOTE_CHARS else stripped


def _clause_start(text: str) -> int:
    """Không có câu trọn vẹn nào -> ít nhất bỏ mệnh đề CỤT ở đầu.

    Chunk kiểu danh sách gạch đầu dòng (NHS dùng rất nhiều) không có dấu chấm nào, nên `trim` không có
    ranh giới câu để bám. Đo trên corpus thật: **20%** chunk rơi vào nhóm này, và chúng là nội dung
    lâm sàng TỐT - lọc bỏ là phá nội dung tốt.

    Nhưng chúng vẫn mở đầu cụt: "and kidney function tests: ...", "any medicine they're taking, ...".
    Cắt tới ranh giới mệnh đề gần nhất (sau `;` hoặc `:`) hoặc tới chữ viết hoa đầu tiên thì trích dẫn
    đọc được, và vẫn là lát cắt nguyên văn."""
    marker = max(text.find("; ", 0, 200), text.find(": ", 0, 200))
    if marker > 0:
        return marker + 2
    capital = re.search(r"\s([A-Z])", text[:200])
    return capital.start() + 1 if capital else 0


def assert_quote_matches_index(quote: str, chunk_id: str, index: SourceIndex) -> Chunk:
    """**Guard 3.** Quote phải là lát cắt NGUYÊN VĂN của chunk đang nằm trong index.

    Trước đây cổng này đòi BẰNG NHAU. Nới thành quan hệ substring vì `trim_to_sentences` cắt quote về
    câu trọn vẹn - và phép nới này không làm yếu guard đi chút nào: quote ⊂ chunk ⊂ trang vẫn là một
    chuỗi phép so chuỗi thuần, vẫn không có chỗ nào cho model bịa trích dẫn. Cái mất đi chỉ là khả
    năng phát hiện "quote ngắn hơn chunk", vốn không phải một lỗi.

    Chuẩn hoá khoảng trắng trước khi so (`normalise_span`, cùng hàm `llm_decision.py` dùng chặn
    evidence bịa): xuống dòng và khoảng trắng thừa là thứ mọi tầng hiển thị đều nghịch. Mọi khác biệt
    còn lại - một chữ, một dấu câu - đều là thật và đều raise."""
    chunk = next((item for item in index.chunks if item.chunk_id == chunk_id), None)
    if chunk is None:
        raise QuoteIntegrityError(f"Guard 3: chunk_id {chunk_id!r} không có trong index.")
    if normalise_span(quote) not in normalise_span(chunk.text):
        raise QuoteIntegrityError(
            f"Guard 3: quote không khớp nguyên văn chunk {chunk_id!r}.\n"
            f"  quote: {quote[:160]!r}\n"
            f"  chunk: {chunk.text[:160]!r}\n"
            "Quote sinh ra bằng cách cắt chuỗi, nên lệch được nghĩa là có code sửa nó trên đường đi."
        )
    return chunk


def assert_quote_within_page(quote: str, page: str, url: str) -> None:
    """**Guard 3, phiên bản lúc NẠP** - dùng khi còn cầm nguyên trang trong tay.

    Đây là chỗ phép kiểm "quote nằm trong trang" thật sự có nghĩa. Lúc chạy thì quote LÀ một chunk,
    nên phép kiểm tương ứng là `assert_quote_matches_index`."""
    if quote not in page:
        raise QuoteIntegrityError(f"Guard 3: đoạn trích không phải lát cắt nguyên văn của trang {url}.")
