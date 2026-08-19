"""Hợp đồng dữ liệu của tầng `source_support` (part 3). KHÔNG có logic, KHÔNG gọi mạng.

VÌ SAO VIẾT TRƯỚC: bảy bước của part 3 chạy trên ba provider khác nhau và bốn trong năm lớp guard là
so chuỗi thuần. Cả hai thứ đó chỉ kiểm được khi hình dạng dữ liệu đã cố định trước, nên module này
là thứ đầu tiên tồn tại và mọi bước khác nhập từ đây.

BA RÀNG BUỘC ĐƯỢC MÃ HOÁ THẲNG VÀO SCHEMA (không phải lời dặn trong prompt):

1. `Method.can_change_label` là `Literal[False]`. Part 3 chạy SAU khi nhãn đã chốt và không có đường
   nào đổi được nó - xem ràng buộc 4 của `graph_triage/service.py`. Khai báo bằng `Literal` để một
   thay đổi tương lai làm nó thành `True` sẽ hỏng lúc validate chứ không lặng lẽ đi qua.
2. `ClaimBatch.claims` tối đa 3. Mỗi claim tốn một lời gọi ở bước chấm verdict, nên đây vừa là trần
   chi phí vừa là trần quota - chỗ chặn phải nằm ở schema, không nằm ở prompt.
3. `VerdictResponse.claim_matches_reasoning` là field BẮT BUỘC. Nó là Guard 0c: bước chấm phải nói
   claim có cùng mệnh đề với đoạn lập luận gốc hay không. Để `Optional` là mời model bỏ trống.

QUOTE GIỮ NGUYÊN VĂN NGÔN NGỮ GỐC. `SourceHit.quote` không bao giờ được dịch: nó phải đối chiếu
verbatim với chunk trong index (guard 5), mà bản dịch thì không đối chiếu được nữa. Phần hiển thị
tiếng Việt nằm ở `Claim.claim_vi` và `SourceSupport.explanation_vi`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Verdict = Literal["supports", "partial", "unsupported", "contradicts"]
"""Thang bốn nấc. `contradicts` là kết quả CÓ THẬT chứ không phải hình thức: bước chấm chạy blind
(không biết có quyết định triage nào tồn tại) nên nó không có động cơ gật cho vừa lòng ai."""

ClaimKind = Literal["red_flag", "rule_out", "temporal", "risk_modifier", "management"]
"""`rule_out` là loại NGUY HIỂM NHẤT: mệnh đề dạng "vắng X thì loại trừ Y". Nguồn thường chỉ liệt kê
X như dấu hiệu cảnh báo của Y - đó là MỆNH ĐỀ ĐẢO, không chứng minh được chiều ngược lại. Xem
`verdict.py` và Guard 0b trong `claims.py`."""

SUPPORTIVE_VERDICTS: frozenset[str] = frozenset({"supports", "partial"})
"""Chỉ hai nấc này mới được phép xuất hiện kèm trích dẫn trong đoạn diễn giải (guard 5)."""


class Claim(BaseModel):
    """Một mệnh đề lâm sàng TỔNG QUÁT tách ra từ lập luận của quyết định.

    Vì sao phải tổng quát hoá: không nguồn y văn nào nói về bệnh nhân cụ thể của mình, nên "bệnh nhân
    này cần cấp cứu" là thứ không tra được. Nhưng chính bước tổng quát hoá đó là chỗ dễ trôi nhất -
    nên có `grounded_in`."""

    model_config = ConfigDict(extra="forbid")

    claim_en: str = Field(min_length=1, max_length=400)
    """Bản tiếng Anh, dùng để TRA index (corpus v1 toàn tài liệu tiếng Anh)."""

    claim_vi: str = Field(min_length=1, max_length=400)
    """Bản tiếng Việt, dùng để HIỂN THỊ. Không dùng để tra."""

    claim_kind: ClaimKind

    grounded_in: str = Field(min_length=1, max_length=600)
    """Đoạn lập luận GỐC mà claim này rút ra, chép nguyên văn từ `decision_summary` hoặc
    `uncertainty_summary`.

    Đây là mắt xích duy nhất nối claim với quyết định, và là thứ Guard 0a/0b kiểm bằng code. Không có
    nó thì mọi lớp guard phía sau chỉ kiểm được claim ↔ nguồn, còn claim ↔ quyết định thì bỏ ngỏ - và
    một claim bị làm mềm sẽ đi lọt toàn bộ hệ guard."""


class ClaimBatch(BaseModel):
    """Structured output của bước 1. Trần 3 claim - xem ràng buộc 2 ở đầu file."""

    model_config = ConfigDict(extra="forbid")

    claims: list[Claim] = Field(default_factory=list, max_length=3)


class VerdictResponse(BaseModel):
    """Structured output của bước 6, chấm MỘT claim trên các đoạn trích ứng viên.

    Prompt sinh ra nó KHÔNG hề biết có một quyết định triage nào tồn tại: không nhận `triage_label`,
    không nhận claim khác. Đó là lý do `contradicts` mới có nghĩa."""

    model_config = ConfigDict(extra="forbid")

    verdict: Verdict
    verdict_reason: str = Field(min_length=1, max_length=500)
    """Viết bằng tiếng Việt - điều dưỡng đọc khi mở phần audit."""

    claim_matches_reasoning: bool
    """Guard 0c. `false` = claim đã bị viết lệch khỏi `grounded_in`, loại khỏi bước diễn giải.

    Vẫn giữ được tính blind: câu hỏi này chỉ so claim với đoạn lập luận gốc, không hề nhắc tới nhãn."""

    best_chunk_id: str = Field(default="", max_length=200)
    """Chunk mà verdict này dựa vào. Rỗng khi không đoạn nào dùng được."""


class SourceHit(BaseModel):
    """Một đoạn trích đã qua chấm, kèm đủ thứ để truy lại nguồn."""

    model_config = ConfigDict(extra="forbid")

    url: str
    title: str = ""
    publisher: str = ""
    chunk_id: str = ""
    quote: str
    """NGUYÊN VĂN ngôn ngữ gốc, không dịch. Guard 5 so verbatim chuỗi này với chunk trong index."""

    verdict: Verdict
    verdict_reason: str = ""
    retrieved_at: str = ""


class Retrieval(BaseModel):
    """Claim này lấy nguồn từ đâu. Đây là số liệu để hiệu chỉnh ngưỡng, không phải trang trí."""

    model_config = ConfigDict(extra="forbid")

    from_index: bool
    searched_web: bool
    best_score: float


class ClaimResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: Claim
    verdict: Verdict
    retrieval: Retrieval
    sources: list[SourceHit] = Field(default_factory=list)


class Citation(BaseModel):
    """Một mục `[n]` trong đoạn diễn giải. Guard 5 kiểm cả `url` lẫn `quote` của mục này."""

    model_config = ConfigDict(extra="forbid")

    marker: str
    url: str
    publisher: str = ""
    title: str = ""
    quote: str


class SupportSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims_examined: int = 0
    claims_with_support: int = 0
    verified_citations: int = 0
    contradicted_claims: list[str] = Field(default_factory=list)
    """`claim_vi` của các claim bị nguồn nói ngược. Không rỗng thì `requires_human_review` phải bật."""

    requires_human_review: bool = False
    """Đường DUY NHẤT part 3 tác động tới ca. Người gọi OR cờ này vào cờ của part 2 - chỉ BẬT THÊM,
    không bao giờ hạ."""

    web_searches_performed: int = 0


class CostReport(BaseModel):
    """Chi phí ghi vào output để nó là số ĐO ĐƯỢC, không phải số ước.

    `provider_calls` tách theo từng provider vì bước nào trượt cổng lọc thì RIÊNG bước đó rơi về
    OpenAI - không nhìn số này thì không biết lượt vừa rồi thật sự chạy ở đâu."""

    model_config = ConfigDict(extra="forbid")

    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    embed_tokens: int = 0
    web_searches: int = 0
    provider_calls: dict[str, int] = Field(default_factory=dict)


class Method(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runs_after_decision: Literal[True] = True
    can_change_label: Literal[False] = False
    """Xem ràng buộc 1 ở đầu file. Đây là sự thật được kiểm, không phải một dòng khai báo."""

    scope_note: str = (
        "Nguồn tham khảo hỗ trợ mệnh đề lâm sàng tổng quát; việc áp vào ca này là suy luận của hệ "
        "thống, không phải điều tài liệu khẳng định. Đây là ý kiến tham khảo - mức ưu tiên có hiệu "
        "lực do quy trình phân loại quyết định."
    )


class SourceSupport(BaseModel):
    """Khối gắn CẠNH quyết định của part 2, không sửa một chữ nào của nó."""

    model_config = ConfigDict(extra="forbid")

    explanation_vi: str = ""
    explanation_citations: list[Citation] = Field(default_factory=list)
    claims: list[ClaimResult] = Field(default_factory=list)
    summary: SupportSummary = Field(default_factory=SupportSummary)
    cost: CostReport = Field(default_factory=CostReport)
    method: Method = Field(default_factory=Method)
