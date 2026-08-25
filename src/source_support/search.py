"""Bước 3 - tìm URL khi index không phủ được claim. Đổi nhà cung cấp bằng CẤU HÌNH, không bằng sửa code.

BA BACKEND TÌM KIẾM + CHẾ ĐỘ TẮT, CÙNG MỘT HỢP ĐỒNG: nhận một mệnh đề tiếng Anh, trả về danh sách URL. Không fetch, không
chunk, không chấm - những việc đó nằm ở `retrieval` và `fetching`, và chúng không cần biết URL đến từ
đâu. Nhờ vậy đổi backend là đổi một dòng `.env`.

    gemini  (mặc định) - Grounding with Google Search, built-in tool của Gemini API
    tavily             - HTTP search API, cần TAVILY_API_KEY
    pubmed             - NCBI ESearch, không cần key, trả URL PubMed dựng từ PMID
    auto               - thử gemini -> tavily -> pubmed theo thứ tự, dừng ở backend đầu tiên có URL;
                          rỗng hoặc lỗi ở một backend đều rớt sang backend kế tiếp (xem `_search_chain`)
    none               - tắt hẳn, tương đương SOURCE_SUPPORT_INDEX_ONLY

VÌ SAO MẶC ĐỊNH GEMINI: dự án đã có key Gemini và chưa có key Tavily. Đánh đổi thật nằm ở chỗ khác
tiền: Tavily tốn ~$0,008/lần search nhưng KHÔNG đụng quota LLM; grounding không tốn tiền riêng nhưng
mỗi lần search là một lượt `generate_content` đầy đủ, tức **+1 call Gemini cho mỗi claim phải tìm**.
Trần một ca vì thế đi từ 10 lên 13 call. Với free tier, giới hạn ràng buộc là RPD chứ không phải tiền
- nên khi chạy hàng loạt thì Tavily hợp lý hơn, còn chạy lẻ thì grounding rẻ hơn.

HAI KHÁC BIỆT KỸ THUẬT PHẢI XỬ LÝ, không phải chi tiết vặt:

1. **Grounding trả URL CHUYỂN HƯỚNG của Google** (`vertexaisearch.cloud.google.com/...`), không phải
   `nhs.uk` trực tiếp. Guard 1 so theo NHÃN TÊN MIỀN nên sẽ chặn sạch. Phải resolve trước khi kiểm -
   xem `_resolve_redirect`.
2. **Grounding không có `include_domains`.** Tavily giới hạn được ngay trong tham số search, tức cùng
   số tiền mua được kết quả dùng được; grounding chỉ nêu được trong câu hỏi, và Guard 1 vẫn phải lọc
   sau. Nghĩa là nhánh grounding sẽ có tỉ lệ URL bị vứt cao hơn.

CÁC BACKEND ĐỀU KHÔNG TỰ QUYẾT ĐỊNH GÌ. Chúng chỉ đề xuất URL; guard 1 (allowlist) và guard 2 (fetch
hợp lệ) ở `fetching.py` mới là chỗ chặn. Với PubMed, điểm khác biệt là trang tóm tắt thường ngắn và
có thể không qua Guard 2, không phải dạng URL chuyển hướng như Gemini.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from src.config import get_settings
from src.source_support.fetching import FETCH_TIMEOUT_SECONDS, domain_allowed

logger = logging.getLogger("vmedtriage.source_support")

MAX_RESULTS = 5

_GROUNDING_REDIRECT_HOSTS = ("vertexaisearch.cloud.google.com", "googleusercontent.com")
"""Host mà Gemini bọc kết quả grounding vào. Thấy host này thì phải resolve mới biết trang thật."""


def search_web(query: str, allowlist: tuple[str, ...], *, meter=None) -> list[str]:
    """Tìm URL cho một mệnh đề. Trả về rỗng khi tắt hoặc khi lỗi.

    KHÔNG raise: search hỏng nghĩa là ca đó thiếu nguồn, không phải ca đó hỏng. Bước 6 sẽ chấm
    `unsupported` và đoạn diễn giải nói thẳng là không tìm được tài liệu - đúng hành vi mong muốn."""
    provider = get_settings().source_support_search_provider.strip().lower()
    if provider == "none":
        return []
    try:
        if provider == "tavily":
            return _search_tavily(query, allowlist, meter=meter)
        if provider == "pubmed":
            return _search_pubmed(query, allowlist, meter=meter)
        if provider == "auto":
            return _search_chain(query, allowlist, meter=meter)
        return _search_gemini(query, allowlist, meter=meter)
    except Exception as error:
        logger.warning("source_support.search_failed provider=%s reason=%s", provider, type(error).__name__)
        return []


# ---------- Gemini grounding ----------


def _search_gemini(query: str, allowlist: tuple[str, ...], *, meter=None) -> list[str]:
    """Grounding with Google Search. Tốn ĐÚNG MỘT call Gemini cho mỗi lần gọi.

    Câu hỏi nêu rõ danh sách domain mong muốn, nhưng đó chỉ là gợi ý - grounding không có cơ chế ép
    như `include_domains` của Tavily. Guard 1 vẫn là chỗ chặn thật."""
    from google import genai
    from google.genai import types

    settings = get_settings()
    if not settings.gemini_api_key.strip():
        logger.info("source_support.search_skipped reason=no_gemini_key")
        return []

    client = genai.Client(api_key=settings.gemini_api_key)
    response = client.models.generate_content(
        model=settings.gemini_model_name,
        contents=_grounding_prompt(query, allowlist),
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.0,
        ),
    )
    if meter is not None:
        meter.record_call("gemini", query, "(grounding)")

    raw = _grounding_uris(response)
    logger.info("source_support.search provider=gemini raw_urls=%s", len(raw))
    return _resolve_and_filter(raw, allowlist)


def _grounding_prompt(query: str, allowlist: tuple[str, ...]) -> str:
    return (
        "Find authoritative clinical guideline pages that discuss the following statement. "
        "Prefer these publishers: " + ", ".join(allowlist) + ".\n"
        "Do not answer the statement and do not give medical advice; only look up sources.\n\n"
        f"Statement: {query}"
    )


def _grounding_uris(response) -> list[str]:
    """Bóc URL khỏi `grounding_metadata`. Viết phòng thủ vì hình dạng metadata đổi theo phiên bản SDK.

    Lấy từ `grounding_chunks[].web.uri`, KHÔNG lấy từ phần text model sinh ra: text là văn bản tự
    sinh, còn đây là danh sách nguồn nó thật sự tra."""
    uris: list[str] = []
    for candidate in getattr(response, "candidates", None) or []:
        metadata = getattr(candidate, "grounding_metadata", None)
        for chunk in getattr(metadata, "grounding_chunks", None) or []:
            web = getattr(chunk, "web", None)
            uri = getattr(web, "uri", None)
            if uri and uri not in uris:
                uris.append(uri)
    return uris[:MAX_RESULTS]


def _resolve_and_filter(uris: list[str], allowlist: tuple[str, ...]) -> list[str]:
    """Resolve link chuyển hướng rồi lọc theo allowlist.

    Guard 1 chạy LẠI ở `fetching.fetch_document`; lọc ở đây chỉ để khỏi tốn một vòng fetch cho URL
    chắc chắn bị loại. Tin một phép lọc sớm không phải là kiểm."""
    resolved: list[str] = []
    for uri in uris:
        url = _resolve_redirect(uri) if _is_redirect(uri) else uri
        if not url:
            continue
        if not domain_allowed(url, allowlist):
            logger.info("source_support.search_url_rejected url=%s reason=ngoai_allowlist", url[:100])
            continue
        if url not in resolved:
            resolved.append(url)
    logger.info("source_support.search_urls_kept kept=%s of=%s", len(resolved), len(uris))
    return resolved


def _is_redirect(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == item or host.endswith("." + item) for item in _GROUNDING_REDIRECT_HOSTS)


def _resolve_redirect(url: str) -> str:
    """Đi theo chuyển hướng để lấy URL thật. Rỗng khi không resolve được.

    Dùng GET chứ không HEAD: nhiều CDN trả 405 cho HEAD, và ta chỉ cần header chuyển hướng nên chi
    phí thêm là chấp nhận được - nhánh này vốn đã phải fetch cả trang ngay sau đó."""
    import httpx

    try:
        response = httpx.get(url, timeout=FETCH_TIMEOUT_SECONDS, follow_redirects=True)
        return str(response.url)
    except Exception as error:
        logger.info("source_support.redirect_failed reason=%s", type(error).__name__)
        return ""


# ---------- Tavily ----------


def _search_tavily(query: str, allowlist: tuple[str, ...], *, meter=None) -> list[str]:
    """HTTP search API. KHÔNG tốn call LLM nào.

    `include_domains` là chỗ allowlist phát huy tác dụng KINH TẾ: không có nó thì phần lớn kết quả
    trả về sẽ bị guard 1 vứt đi SAU KHI đã trả tiền cho lượt search."""
    import httpx

    settings = get_settings()
    if not settings.tavily_api_key.strip():
        logger.info("source_support.search_skipped reason=no_tavily_key")
        return []

    response = httpx.post(
        "https://api.tavily.com/search",
        json={
            "api_key": settings.tavily_api_key,
            "query": query,
            "max_results": MAX_RESULTS,
            "include_domains": list(allowlist),
            "search_depth": "basic",
        },
        timeout=30.0,
    )
    response.raise_for_status()
    urls = [item["url"] for item in response.json().get("results", []) if item.get("url")]
    logger.info("source_support.search provider=tavily raw_urls=%s", len(urls))
    return [url for url in urls if domain_allowed(url, allowlist)]


# ---------- PubMed (NCBI E-utilities) ----------
_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

_PUBMED_OPERATOR_CHARS = re.compile(r'[()\[\]{}"&|:]')
"""Ký tự ESearch đọc là CÚ PHÁP, không phải chữ. Dấu ngoặc là toán tử gộp boolean, `[...]` là field
tag (`[tiab]`), `:` là khoảng giá trị. Đo thật 2026-08-23: claim
`"Acute liver failure (acetaminophen poisoning acceptable) ..."` trả về ĐÚNG 0 kết quả; bỏ mỗi cặp
ngoặc đi thì ra 5. Một mệnh đề lâm sàng vô tình có ngoặc đơn - rất thường gặp - sẽ âm thầm mất nguồn
chứ không báo lỗi."""

_PUBMED_STOPWORDS = frozenset({
    # từ chức năng tiếng Anh
    "a", "an", "the", "of", "in", "on", "at", "by", "to", "for", "from", "with", "without",
    "and", "or", "as", "is", "are", "be", "being", "been", "that", "this", "these", "those",
    "it", "its", "may", "can", "who", "which",
    # ngôn ngữ KHUYẾN CÁO - không giúp truy hồi vì abstract nghiên cứu không bao giờ viết kiểu này
    "requires", "require", "required", "needs", "need", "needed", "should", "must",
    "warrants", "warrant", "indicated", "recommended", "advise", "advised",
    # từ lâm sàng rỗng nghĩa - bài nào trên PubMed cũng "clinical"/"patient"
    "clinical", "clinically", "patient", "patients", "prompt", "promptly", "urgent", "urgently",
    "immediate", "immediately", "evaluation", "evaluate", "assessment", "assess", "review",
})
"""Bỏ khỏi câu truy vấn ESearch. HAI NHÓM CÓ CHỦ ĐÍCH KHÁC NHAU: nhóm từ chức năng là để câu ngắn lại
(xem `_PUBMED_MAX_TERMS`), còn nhóm khuyến cáo/rỗng nghĩa là vì chúng CHỦ ĐỘNG làm hỏng truy hồi -
`requires clinical evaluation` không xuất hiện trong abstract nghiên cứu nào, nên giữ lại chỉ siết
chặt thêm phép AND ngầm của ESearch mà không lọc được gì."""

_PUBMED_MAX_TERMS = 10
"""Trần số từ khoá. ESearch nối các từ bằng AND ngầm, nên câu càng dài kết quả càng teo. Đo thật
2026-08-23, cùng một mệnh đề COPD: câu đầy đủ (14 từ) -> 1 kết quả, `best_score` 0.532, verdict
`unsupported`; bản rút còn 7 từ khoá -> 5 kết quả, `best_score` 0.644, verdict `supports`."""


def _pubmed_query(claim: str) -> str:
    """Câu mệnh đề tiếng Anh -> chuỗi từ khoá cho ESearch. Hàm THUẦN: không mạng, không LLM.

    Phải deterministic. Nhánh `documented_rule` của C6 đã có một tầng LLM trích fact không tái lập
    được (chạy 3 lần ra 2 kết quả khác nhau); thêm một tầng LLM nữa ở chỗ dựng câu truy vấn thì
    không còn cách nào truy ngược vì sao một ca trích được nguồn còn ca kia thì không.

    Rỗng sau khi lọc thì TRẢ LẠI câu gốc: chuỗi rỗng khiến ESearch khớp toàn bộ PubMed."""
    cleaned = _PUBMED_OPERATOR_CHARS.sub(" ", claim)
    terms = [word for word in cleaned.split() if word.lower().strip(",.;") not in _PUBMED_STOPWORDS]
    return " ".join(terms[:_PUBMED_MAX_TERMS]) if terms else claim


def _search_pubmed(query: str, allowlist: tuple[str, ...], *, meter=None) -> list[str]:
    """Gọi NCBI ESearch và dựng URL PubMed trực tiếp từ PMID.

    Không tốn LLM call và không cần key. URL PubMed vẫn phải đi qua allowlist trước khi fetch.
    `query` là câu mệnh đề đầy đủ; ESearch cần từ khoá nên đi qua `_pubmed_query` trước.
    """
    import httpx

    settings = get_settings()
    term = _pubmed_query(query)
    if term != query:
        logger.info("source_support.pubmed_query_trimmed term=%r", term[:120])
    params = {
        "db": "pubmed",
        "term": term,
        "retmax": str(MAX_RESULTS),
        "retmode": "json",
        # BẮT BUỘC truyền `sort`. Mặc định của ESearch là trả bài MỚI NHẤT, không phải bài LIÊN QUAN
        # NHẤT - đo thật 2026-08-23: claim về đợt cấp COPD nhận về 5 chunk đều từ CÙNG một bài về ô
        # nhiễm không khí (PMID 42xxxxxx, tức vừa đăng), và bước chấm loại sạch. Nguồn tra cứu sắp
        # theo ngày đăng là vô nghĩa với một mệnh đề lâm sàng.
        "sort": "relevance",
    }
    if settings.ncbi_api_key.strip():
        params["api_key"] = settings.ncbi_api_key

    response = httpx.get(_ESEARCH_URL, params=params, timeout=FETCH_TIMEOUT_SECONDS)
    response.raise_for_status()
    pmids = response.json().get("esearchresult", {}).get("idlist", [])
    urls = [f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" for pmid in pmids]
    logger.info("source_support.search provider=pubmed raw_urls=%s", len(urls))
    return [url for url in urls if domain_allowed(url, allowlist)]


# ---------- Auto (chain gemini -> tavily -> pubmed) ----------


def _search_chain(query: str, allowlist: tuple[str, ...], *, meter=None) -> list[str]:
    """Thử lần lượt Gemini -> Tavily -> PubMed, dừng ở backend đầu tiên có URL.

    TỰ BẮT LỖI Ở TỪNG BƯỚC, không dựa vào catch chung của `search_web()` - catch đó bọc quanh TOÀN BỘ
    dispatch, nên nếu để lộ ra đây thì Gemini lỗi (vd 429 free tier, xem config.py) sẽ làm hỏng luôn
    cả chuỗi thay vì rớt xuống Tavily/PubMed - đúng ngược với mục đích của "auto". Rỗng (backend chạy
    xong nhưng không có URL nào qua được allowlist) cũng tính là "không được", vì 429 của Gemini vốn
    đã bị chính `_search_gemini`/`search_web` nuốt thành danh sách rỗng ở tầng ngoài - chỉ bắt
    exception thì tình huống hay gặp nhất sẽ không bao giờ kích hoạt fallback."""
    for name, backend in (("gemini", _search_gemini), ("tavily", _search_tavily), ("pubmed", _search_pubmed)):
        try:
            urls = backend(query, allowlist, meter=meter)
        except Exception as error:
            logger.warning("source_support.search_chain_step_failed provider=%s reason=%s", name, type(error).__name__)
            continue
        if urls:
            logger.info("source_support.search_chain_selected provider=%s urls=%s", name, len(urls))
            return urls
    logger.info("source_support.search_chain_exhausted")
    return []
