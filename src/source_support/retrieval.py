"""Bước 2-4: tra index, và chỉ khi trượt mới đi search rồi **ghi kết quả vào index**. KHÔNG dùng LLM.

INDEX TỰ BỒI ĐẮP. Mỗi lần một claim không tra được, hệ thống đi search, fetch trang, cắt chunk và nạp
vào index. Nhờ vậy mỗi lần search là một khoản ĐẦU TƯ chứ không phải khoản chi lặp lại: sau vài trăm
ca, phần lớn claim đã có trang tương ứng và chi phí hội tụ về gần bằng RAG thuần.

NGƯỠNG LÀ NÚM VẶN CHI PHÍ, KHÔNG CHỈ LÀ NÚM VẶN CHẤT LƯỢNG. Hạ `source_support_threshold` thì ít lần
search hơn - mà search là ~89% tiền của một ca đắt - đổi lại quote yếu hơn. Chỗ đỡ đòn cho quote yếu
đã có sẵn: bước 6 chấm blind sẽ gạt nó thành `unsupported`. Vì thế hiệu chỉnh ngưỡng phải làm CÙNG
LÚC với đo hit-rate, không tách rời.

ALLOWLIST ĐẨY VÀO THAM SỐ SEARCH, KHÔNG LỌC SAU. Đặc tả gốc đặt guard 1 SAU bước search, tức trả tiền
cho một lần search rồi mới vứt phần lớn kết quả. Đưa danh sách domain thẳng vào `include_domains` thì
cùng số tiền đó mua được kết quả dùng được. Guard 1 vẫn chạy lại ở `fetching.fetch_document` - tin
một tham số gửi đi không phải là kiểm.

ĐO TÁCH "SEARCH CHẠY MẤY LẦN" VÀ "SEARCH CỨU ĐƯỢC MẤY CLAIM". Corpus ban đầu đã nạp ~40 tài liệu từ
đúng những domain trong allowlist, nên một claim index không phủ được, đem search giới hạn trong CÙNG
những domain ấy, phần nhiều sẽ lại trượt. Gộp hai con số làm một sẽ giấu mất điều đó.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.config import get_settings
from src.source_support.fetching import FetchFailure, fetch_document, parse_allowlist
from src.source_support.index import SearchHit, SourceIndex
from src.source_support.llm import CostMeter
from src.source_support.progress import Progress, ProgressReporter, reporter_for
from src.source_support.schemas import Claim, Retrieval
from src.source_support.search import search_web

logger = logging.getLogger("vmedtriage.source_support")

TOP_K = 5
"""Số chunk ứng viên đưa sang bước chấm. Nhiều hơn thì prompt phình ra mà bước 5 vẫn chỉ lấy top-1."""

SEARCH_RESULTS = 5


@dataclass
class ClaimEvidence:
    """Kết quả tra cho MỘT claim: các chunk ứng viên + sổ sách retrieval."""

    claim: Claim
    candidates: list[SearchHit] = field(default_factory=list)
    retrieval: Retrieval = field(default_factory=lambda: Retrieval(from_index=False, searched_web=False, best_score=0.0))
    failures: list[FetchFailure] = field(default_factory=list)

    @property
    def best_score(self) -> float:
        return self.candidates[0].score if self.candidates else 0.0



def retrieve(
    claim: Claim,
    index: SourceIndex,
    *,
    meter: CostMeter | None = None,
    threshold: float | None = None,
    index_only: bool | None = None,
    on_progress: Progress | ProgressReporter | None = None,
    claim_index: int = 0,
    claim_total: int = 0,
) -> ClaimEvidence:
    """Bước 2 (+3+4 khi trượt) cho một claim.

    Tra bằng `claim_en`: corpus v1 toàn tài liệu tiếng Anh, nên bản tiếng Việt để hiển thị chứ không
    để tra - trộn hai ngôn ngữ trong một không gian cosine với ngưỡng cố định làm nhóm nào ít hơn gần
    như không bao giờ được lấy ra."""
    from src.source_support.embedding import embed_one, last_token_usage

    reporter = reporter_for(on_progress)
    position = f"{claim_index}/{claim_total} " if claim_total else ""
    reporter.emit(
        "claim_lookup",
        f"Tra index cho mệnh đề {position}- {claim.claim_vi[:70]}",
        index=claim_index, total=claim_total, claim_vi=claim.claim_vi,
    )

    settings = get_settings()
    threshold = settings.source_support_threshold if threshold is None else threshold
    index_only = settings.source_support_index_only if index_only is None else index_only
    allowlist = parse_allowlist(settings.source_support_allowlist)

    vector = embed_one(claim.claim_en)
    if meter is not None:
        meter.embed_tokens += last_token_usage()
    candidates = index.search(vector, top_k=TOP_K)
    best = candidates[0].score if candidates else 0.0

    if best >= threshold:
        reporter.emit(
            "index_hit",
            f"Index phủ được mệnh đề {position}(điểm {best:.3f}) - không cần search",
            index=claim_index, total=claim_total, best_score=best,
        )
        return ClaimEvidence(
            claim=claim,
            candidates=candidates,
            retrieval=Retrieval(from_index=True, searched_web=False, best_score=best),
        )

    if index_only or settings.source_support_search_provider == "none":
        # Ghi rõ VÌ SAO không search: thiếu key và bật cờ đo là hai chuyện khác nhau, và người đọc log
        # cần phân biệt được "hệ thống chưa được cấu hình" với "hệ thống đang chạy chế độ chỉ-index".
        logger.info(
            "source_support.search_skipped reason=%s best_score=%.3f",
            "index_only" if index_only else "search_provider_none", best,
        )
        reporter.emit(
            "search_skipped",
            "Bỏ qua search web ({}), chỉ dùng index".format(
                "chế độ chỉ-index" if index_only else "chưa cấu hình provider search"
            ),
            index=claim_index, total=claim_total, best_score=best,
        )
        return ClaimEvidence(
            claim=claim,
            candidates=candidates,
            retrieval=Retrieval(from_index=bool(candidates), searched_web=False, best_score=best),
        )

    reporter.emit(
        "search_start",
        f"Index không phủ mệnh đề {position}(điểm {best:.3f} < ngưỡng {threshold:.2f}) - đi search web",
        index=claim_index, total=claim_total, best_score=best, threshold=threshold,
    )
    evidence = _search_and_ingest(claim, index, allowlist, meter=meter, reporter=reporter)
    candidates = index.search(vector, top_k=TOP_K)
    best = candidates[0].score if candidates else 0.0
    evidence.candidates = candidates
    evidence.retrieval = Retrieval(from_index=False, searched_web=True, best_score=best)
    reporter.emit(
        "search_done",
        f"Search xong cho mệnh đề {position}- điểm tốt nhất sau khi nạp: {best:.3f}",
        index=claim_index, total=claim_total, best_score=best,
    )
    return evidence


def _search_and_ingest(
    claim: Claim,
    index: SourceIndex,
    allowlist: tuple[str, ...],
    *,
    meter: CostMeter | None = None,
    reporter: ProgressReporter | None = None,
) -> ClaimEvidence:
    """Bước 3 + 4. Nạp mọi trang qua được hai cổng vào index, kể cả trang không cứu được claim này -
    nó vẫn có thể phủ một claim ở ca sau, và tiền search thì đã trả rồi."""
    from src.source_support.embedding import embed_many, last_token_usage
    from src.source_support.index import prepare_chunks

    reporter = reporter or ProgressReporter()
    urls = search_web(claim.claim_en, allowlist, meter=meter)
    if meter is not None:
        meter.web_searches += 1
    reporter.emit("search_results", f"Search trả về {len(urls)} đường dẫn", urls=len(urls))

    failures: list[FetchFailure] = []
    for position, url in enumerate(urls, start=1):
        if index.has_document(url):
            reporter.emit(
                "fetch_cached", f"[{position}/{len(urls)}] đã có trong index: {_host(url)}",
                url=url, index=position, total=len(urls),
            )
            continue
        # Báo TRƯỚC khi fetch, không phải sau: đây là chỗ một request có thể treo tới hết timeout, và
        # dòng người dùng cần đọc lúc đó là "đang tải trang nào", không phải "đã tải xong trang nào".
        reporter.emit(
            "fetch_start", f"[{position}/{len(urls)}] đang tải {_host(url)}",
            url=url, index=position, total=len(urls),
        )
        document = fetch_document(url, allowlist=allowlist)
        if isinstance(document, FetchFailure):
            failures.append(document)
            logger.info("source_support.fetch_rejected url=%s reason=%s", document.url, document.reason)
            reporter.emit(
                "fetch_rejected", f"[{position}/{len(urls)}] bỏ {_host(url)}: {document.reason}",
                url=url, reason=document.reason, index=position, total=len(urls),
            )
            continue
        _, pieces = prepare_chunks(document.text)
        if not pieces:
            failures.append(FetchFailure(url, "guard 2: không cắt được chunk nào"))
            reporter.emit(
                "fetch_rejected", f"[{position}/{len(urls)}] bỏ {_host(url)}: không cắt được chunk nào",
                url=url, reason="guard 2", index=position, total=len(urls),
            )
            continue
        reporter.emit(
            "embed_start", f"[{position}/{len(urls)}] nhúng {len(pieces)} chunk từ {_host(url)}",
            url=url, chunks=len(pieces), index=position, total=len(urls),
        )
        # Nhúng theo LÔ: một trang tách ra hàng chục chunk, gọi từng cái một là chỗ chậm nhất của cả
        # nhánh miss.
        index.add_document(document=document, vectors=embed_many(pieces))
        if meter is not None:
            meter.embed_tokens += last_token_usage()

    return ClaimEvidence(claim=claim, failures=failures)


def _host(url: str) -> str:
    """Tên miền cho dòng tiến trình. URL đầy đủ của nhs.uk dài tới ~120 ký tự và đẩy phần còn lại của
    dòng ra khỏi màn hình - thứ người đọc cần lúc đang chờ là "đang ở nguồn nào", còn URL đầy đủ thì
    đã nằm trong phần trích dẫn cuối cùng."""
    from urllib.parse import urlparse

    return urlparse(url).netloc or url[:60]
