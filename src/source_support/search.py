"""Bước 3 - tìm URL khi index không phủ được claim. Đổi nhà cung cấp bằng CẤU HÌNH, không bằng sửa code.

HAI ĐƯỜNG, CÙNG MỘT HỢP ĐỒNG: nhận một mệnh đề tiếng Anh, trả về danh sách URL. Không fetch, không
chunk, không chấm - những việc đó nằm ở `retrieval` và `fetching`, và chúng không cần biết URL đến từ
đâu. Nhờ vậy đổi backend là đổi một dòng `.env`.

    gemini  (mặc định) - Grounding with Google Search, built-in tool của Gemini API
    tavily             - HTTP search API, cần TAVILY_API_KEY
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

CẢ HAI ĐƯỜNG ĐỀU KHÔNG TỰ QUYẾT ĐỊNH GÌ. Chúng chỉ đề xuất URL; guard 1 (allowlist) và guard 2 (fetch
hợp lệ) ở `fetching.py` mới là chỗ chặn, và chúng chạy y hệt nhau cho cả hai backend.
"""

from __future__ import annotations

import logging
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
