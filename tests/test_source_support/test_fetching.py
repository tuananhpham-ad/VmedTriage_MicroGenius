"""Guard 1 (allowlist domain) và bóc text. Không chạm mạng - mọi bài ở đây là hàm thuần.

Bài đáng chú ý là `test_rejects_spoofed_domains`. Cách viết sai kinh điển của một allowlist là
`"nhs.uk" in url`, và nó lọt `https://nhs.uk.evil.com/...` - một trang do người khác kiểm soát hoàn
toàn, nhưng trong đoạn diễn giải cho điều dưỡng nó hiện ra như một trích dẫn NHS.
"""

from __future__ import annotations

import pytest

from src.source_support.fetching import (
    domain_allowed,
    extract_text,
    page_title,
    parse_allowlist,
    publisher_of,
)

ALLOWLIST = parse_allowlist("who.int,nhs.uk,cdc.gov,msdmanuals.com")


# --- Guard 1 -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://nhs.uk/conditions/febrile-seizures/",
        "https://www.nhs.uk/conditions/febrile-seizures/",
        "https://www.who.int/publications/i/item/imci-chart-booklet",
        "https://www.msdmanuals.com/professional/pediatrics/febrile-seizures",
    ],
)
def test_accepts_allowlisted_domains_and_subdomains(url: str) -> None:
    assert domain_allowed(url, ALLOWLIST)


@pytest.mark.parametrize(
    "url",
    [
        "https://nhs.uk.evil.com/conditions/febrile-seizures/",
        "https://evil-nhs.uk/bai-viet",
        "https://evil.com/?ref=nhs.uk",
        "https://evil.com/nhs.uk/conditions",
        "https://cdc.gov.attacker.net/page",
    ],
)
def test_rejects_spoofed_domains(url: str) -> None:
    """Mọi biến thể chứa tên domain hợp lệ như CHUỖI CON đều phải bị loại."""
    assert not domain_allowed(url, ALLOWLIST)


def test_rejects_domains_outside_allowlist() -> None:
    assert not domain_allowed("https://vi.wikipedia.org/wiki/Sot", ALLOWLIST)
    assert not domain_allowed("https://some-blog.net/tri-sot-tai-nha", ALLOWLIST)


def test_rejects_plain_http() -> None:
    """`http` để ngỏ đường sửa nội dung trên đường truyền, mà nội dung đó đi thẳng vào trích dẫn."""
    assert not domain_allowed("http://www.nhs.uk/conditions/febrile-seizures/", ALLOWLIST)


@pytest.mark.parametrize("url", ["", "not-a-url", "https://", "ftp://nhs.uk/x", "https://NHS.UK./x"])
def test_handles_malformed_urls(url: str) -> None:
    """URL rác không được làm cổng nổ; chỉ đơn giản là không qua - trừ biến thể hoa/dấu chấm cuối của
    một host hợp lệ, vốn là cùng một host."""
    expected = url == "https://NHS.UK./x"
    assert domain_allowed(url, ALLOWLIST) is expected


# --- nhà xuất bản ------------------------------------------------------------------------------


def test_publisher_is_the_matched_domain() -> None:
    assert publisher_of("https://www.nhs.uk/conditions/x", ALLOWLIST) == "nhs.uk"
    assert publisher_of("https://www.msdmanuals.com/x", ALLOWLIST) == "msdmanuals.com"


# --- bóc text ----------------------------------------------------------------------------------


def test_extract_text_drops_script_style_and_navigation() -> None:
    html = """
    <html><head><title>Febrile seizures</title><style>.a{color:red}</style></head>
    <body>
      <nav>Trang chủ | Liên hệ</nav>
      <script>window.track("x")</script>
      <p>Call 999 if the seizure lasts longer than 5 minutes.</p>
      <footer>Bản quyền</footer>
    </body></html>
    """
    text = extract_text(html)
    assert "Call 999 if the seizure lasts longer than 5 minutes." in text
    assert "window.track" not in text
    assert "color:red" not in text
    assert "Trang chủ" not in text
    assert "Bản quyền" not in text


def test_extract_text_keeps_block_boundaries() -> None:
    """Hai khối không được dán liền: nối chúng sẽ tạo ra những "câu" chưa từng có trên trang, và một
    trích dẫn nguyên văn câu như thế thì khớp chunk nhưng người mở link không tìm thấy."""
    text = extract_text("<p>Câu một.</p><p>Câu hai.</p>")
    assert "Câu một.Câu hai." not in text
    assert "Câu một." in text and "Câu hai." in text


def test_page_title() -> None:
    assert page_title("<html><head><title>  Febrile   seizures </title></head></html>") == "Febrile seizures"
    assert page_title("<html><head></head><body>x</body></html>") == ""


# --- Guard 2: kiểu nội dung ---------------------------------------------------------------------


class _Response:
    def __init__(self, *, content_type: str, text: str, url: str = "https://www.nhs.uk/x"):
        self.status_code = 200
        self.headers = {"content-type": content_type}
        self.text = text
        self.url = url


@pytest.mark.parametrize(
    ("content_type", "accepted"),
    [
        ("text/html; charset=utf-8", True),
        ("application/xhtml+xml", True),
        ("text/plain", True),
        ("application/pdf", False),
        ("image/png", False),
        ("application/octet-stream", False),
    ],
)
def test_guard2_only_accepts_readable_content_types(content_type: str, accepted: bool, monkeypatch) -> None:
    """Sàn "≥500 ký tự" một mình KHÔNG đủ, và đây là lỗi đo được chứ không phải lo xa.

    2026-08-19: một file PDF của AAFP lọt qua sàn vì `bs4` parse nhị phân như HTML mà không báo lỗi -
    828.369 ký tự rác kiểu "%PDF-1.5 %␦␦ 802 0 obj" thành 1.237 chunk, chiếm 95% số chunk của lần
    search đó và gần như toàn bộ tiền nhúng. Rác đó nằm trong index và CÓ THỂ ĐƯỢC TRÍCH DẪN cho điều
    dưỡng đọc."""
    import httpx

    from src.source_support import fetching

    body = "<html><body><p>" + ("Nội dung lâm sàng đủ dài. " * 60) + "</p></body></html>"
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Response(content_type=content_type, text=body))

    result = fetching.fetch_document("https://www.nhs.uk/x", allowlist=ALLOWLIST)
    assert hasattr(result, "text") is accepted
    if not accepted:
        assert "kiểu nội dung" in result.reason


def test_guard2_rejects_absurdly_long_extractions(monkeypatch) -> None:
    """Trần độ dài là lớp phòng thủ thứ hai: trang y văn dài nhất trong corpus tay (~110k ký tự) còn
    xa trần, nên chạm trần gần như luôn nghĩa là bóc nhầm thứ không phải văn bản."""
    import httpx

    from src.source_support import fetching

    body = "<html><body><p>" + ("x" * (fetching.MAX_TEXT_CHARS + 1000)) + "</p></body></html>"
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Response(content_type="text/html", text=body))

    result = fetching.fetch_document("https://www.nhs.uk/x", allowlist=ALLOWLIST)
    assert not hasattr(result, "text")
    assert "không phải văn bản" in result.reason
