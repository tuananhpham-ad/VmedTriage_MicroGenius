"""Lấy trang y văn về: **Guard 1** (allowlist domain) và **Guard 2** (fetch hợp lệ). KHÔNG dùng LLM.

Dùng chung cho hai đường vào của corpus: nạp danh sách tài liệu duyệt tay (`build_source_corpus.py`)
và nhánh index-miss đi search. Cả hai đều phải qua đúng hai cổng này - nếu tách làm hai bản thì sớm
muộn một đường sẽ lỏng hơn đường kia, mà đường lỏng mới là đường bị lợi dụng.

GUARD 1 SO THEO NHÃN TÊN MIỀN, KHÔNG SO CHUỖI CON. `"nhs.uk" in url` là cách viết sai kinh điển:
`https://nhs.uk.evil.com/bai-viet` chứa chuỗi đó và sẽ lọt. Cổng này tách host ra rồi đòi host TRÙNG
KHỚP domain hoặc là tên miền con thật sự của nó (`www.nhs.uk` hợp lệ, `nhs.uk.evil.com` thì không).
Chỉ chấp nhận `https`: `http` để ngỏ đường sửa nội dung trên đường truyền, mà nội dung đó sẽ đi thẳng
vào một trích dẫn y khoa.

GUARD 2 ĐÒI ĐỦ CHỮ, KHÔNG CHỈ ĐÒI HTTP 200. Trang lỗi mềm, trang chuyển hướng, trang chỉ có menu đều
trả 200 kèm vài chục ký tự - nạp vào index thì chúng thành nhiễu vĩnh viễn, và tệ hơn là thành nguồn
có thể được trích. Ngưỡng 500 ký tự là sàn thô nhưng đủ để loại hết nhóm đó.

CẢ HAI CỔNG BỎ ỨNG VIÊN CHỨ KHÔNG RAISE. Một URL chết không phải lỗi hệ thống - URL guideline chết
khá thường xuyên. Nhưng chúng luôn BÁO RÕ cái gì bị loại và vì sao; im lặng bỏ qua là cách một corpus
teo dần mà không ai nhận ra.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse

from src.source_support.index import DocumentInput

logger = logging.getLogger("vmedtriage.source_support")

MIN_TEXT_CHARS = 500
"""Sàn của Guard 2. Xem docstring module."""

HTML_CONTENT_TYPES = ("text/html", "application/xhtml+xml", "text/plain")
"""Kiểu nội dung `extract_text` đọc được. MỌI thứ khác bị loại - xem `_looks_like_binary`."""

MAX_TEXT_CHARS = 400_000
"""Trần độ dài trang. Trang y văn dài nhất trong corpus tay (~110k ký tự) còn xa trần này, nên chạm
trần gần như luôn nghĩa là bóc nhầm thứ gì đó không phải văn bản."""

FETCH_TIMEOUT_SECONDS = 20.0

_USER_AGENT = "VMedTriage-SourceSupport/1.0 (clinical triage research; contact: repo maintainer)"

_STRIP_TAGS = ("script", "style", "nav", "header", "footer", "form", "aside", "noscript")


@dataclass(frozen=True, slots=True)
class FetchFailure:
    """Vì sao một URL bị loại. Tồn tại để `build_source_corpus.py` in được báo cáo thay vì đếm số."""

    url: str
    reason: str


def parse_allowlist(raw: str) -> tuple[str, ...]:
    """Chuỗi cấu hình -> tuple domain đã chuẩn hoá."""
    return tuple(item.strip().lower().lstrip(".") for item in raw.split(",") if item.strip())


def domain_allowed(url: str, allowlist: tuple[str, ...]) -> bool:
    """Guard 1. `True` khi host là chính một domain trong danh sách, hoặc tên miền con thật của nó."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        return False
    return any(host == domain or host.endswith("." + domain) for domain in allowlist)


def extract_text(html: str) -> str:
    """Bóc phần chữ đọc được của trang. Bỏ script/style/điều hướng trước khi lấy text.

    Giữ ranh giới khối bằng ký tự xuống dòng (`separator="\\n"`): nối liền các khối sẽ dán câu cuối
    của đoạn này vào câu đầu của đoạn sau và tạo ra những "câu" chưa từng tồn tại trên trang - trích
    dẫn nguyên văn một câu như thế thì vẫn khớp chunk nhưng người mở link sẽ không tìm thấy nó."""
    import warnings

    from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

    with warnings.catch_warnings():
        # Cảnh báo này nổi lên khi trang thật ra là XML/nhị phân. Nguyên nhân đã bị chặn ở
        # `fetch_document` (kiểm content-type), nên ở đây nó chỉ còn là tiếng ồn che mất log thật.
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        soup = BeautifulSoup(html, "lxml")
    for tag in soup(list(_STRIP_TAGS)):
        tag.decompose()
    return soup.get_text(separator="\n")


def page_title(html: str) -> str:
    import warnings

    from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        soup = BeautifulSoup(html, "lxml")
    if soup.title and soup.title.string:
        return " ".join(soup.title.string.split())[:200]
    return ""


def publisher_of(url: str, allowlist: tuple[str, ...]) -> str:
    """Domain đã khớp allowlist, dùng làm tên nhà xuất bản khi trang không tự khai."""
    host = (urlparse(url).hostname or "").lower()
    for domain in allowlist:
        if host == domain or host.endswith("." + domain):
            return domain
    return host


def fetch_document(
    url: str,
    *,
    allowlist: tuple[str, ...],
    publisher: str = "",
    title: str = "",
) -> DocumentInput | FetchFailure:
    """Guard 1 + Guard 2 + bóc text. Trả `DocumentInput` khi qua cả hai, `FetchFailure` khi không.

    Không raise: người gọi nạp hàng chục URL một lượt và cần biết cái nào hỏng chứ không cần dừng cả
    mẻ vì một trang chết."""
    import httpx

    if not domain_allowed(url, allowlist):
        return FetchFailure(url, "guard 1: domain không nằm trong allowlist (hoặc không phải https)")

    try:
        response = httpx.get(
            url,
            timeout=FETCH_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        )
    except Exception as error:
        return FetchFailure(url, f"guard 2: không gọi được ({type(error).__name__})")

    if response.status_code != 200:
        return FetchFailure(url, f"guard 2: HTTP {response.status_code}")

    # Chuyển hướng có thể đưa ra ngoài allowlist (rút gọn link, đổi tên miền). Kiểm lại URL CUỐI
    # CÙNG, vì đó mới là trang thật sự được trích và là URL sẽ hiện trong trích dẫn.
    final_url = str(response.url)
    if not domain_allowed(final_url, allowlist):
        return FetchFailure(url, f"guard 1: chuyển hướng ra ngoài allowlist ({final_url})")

    # Guard 2, phần KIỂU NỘI DUNG. Sàn "≥500 ký tự" một mình là không đủ: `bs4` parse nhị phân PDF
    # như HTML mà không báo lỗi, và cho ra hàng trăm nghìn ký tự rác kiểu "%PDF-1.5 %␦␦ 802 0 obj".
    # Đo thật 2026-08-19: một file PDF của AAFP lọt qua sàn, ra 828.369 ký tự -> 1.237 chunk rác,
    # chiếm 95% số chunk và gần như toàn bộ tiền nhúng của lần search đó. Rác đó nằm trong index và
    # có thể được TRÍCH DẪN cho điều dưỡng đọc.
    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type and not content_type.startswith(HTML_CONTENT_TYPES):
        return FetchFailure(url, f"guard 2: kiểu nội dung {content_type!r} không đọc được (chỉ nhận HTML)")

    text = extract_text(response.text)
    stripped = text.strip()
    if len(stripped) < MIN_TEXT_CHARS:
        return FetchFailure(url, f"guard 2: chỉ bóc được {len(stripped)} ký tự (<{MIN_TEXT_CHARS})")
    if len(stripped) > MAX_TEXT_CHARS:
        return FetchFailure(url, f"guard 2: bóc ra {len(stripped):,} ký tự (>{MAX_TEXT_CHARS:,}) - nhiều khả năng không phải văn bản")

    return DocumentInput(
        url=final_url,
        text=text,
        title=title or page_title(response.text),
        publisher=publisher or publisher_of(final_url, allowlist),
        retrieved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
