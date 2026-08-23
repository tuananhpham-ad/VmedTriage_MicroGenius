"""Unit tests for source-support search provider dispatch and PubMed ESearch."""

from __future__ import annotations

import httpx
import pytest

from src.config import get_settings
from src.source_support import search
from src.source_support.fetching import parse_allowlist

PUBMED_ALLOWLIST = parse_allowlist("ncbi.nlm.nih.gov")


class _Response:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


@pytest.fixture
def pubmed_settings(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "source_support_search_provider", "pubmed")
    monkeypatch.setattr(settings, "ncbi_api_key", "")
    return settings


def test_search_pubmed_builds_urls_from_pmids(monkeypatch, pubmed_settings):
    captured: dict = {}

    def fake_get(url, *, params, timeout):
        captured.update(url=url, params=params, timeout=timeout)
        return _Response({"esearchresult": {"idlist": ["12345", "67890"]}})

    monkeypatch.setattr(httpx, "get", fake_get)

    assert search._search_pubmed("acute abdominal pain", PUBMED_ALLOWLIST) == [
        "https://pubmed.ncbi.nlm.nih.gov/12345/",
        "https://pubmed.ncbi.nlm.nih.gov/67890/",
    ]
    assert captured["url"] == search._ESEARCH_URL
    assert captured["params"] == {
        "db": "pubmed",
        "term": "acute abdominal pain",
        "retmax": str(search.MAX_RESULTS),
        "retmode": "json",
        "sort": "relevance",
    }


def test_search_pubmed_returns_empty_for_empty_or_missing_idlist(monkeypatch, pubmed_settings):
    payloads = iter([{"esearchresult": {"idlist": []}}, {}])
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: _Response(next(payloads)))

    assert search._search_pubmed("query", PUBMED_ALLOWLIST) == []
    assert search._search_pubmed("query", PUBMED_ALLOWLIST) == []


def test_search_pubmed_respects_allowlist(monkeypatch, pubmed_settings):
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *args, **kwargs: _Response({"esearchresult": {"idlist": ["12345"]}}),
    )

    assert search._search_pubmed("query", parse_allowlist("who.int")) == []


def test_search_web_catches_pubmed_http_error(monkeypatch, pubmed_settings):
    def fake_get(*args, **kwargs):
        raise httpx.HTTPError("NCBI unavailable")

    monkeypatch.setattr(httpx, "get", fake_get)

    assert search.search_web("query", PUBMED_ALLOWLIST) == []


def test_search_web_dispatches_to_pubmed(monkeypatch, pubmed_settings):
    captured: dict = {}

    def fake_pubmed(query, allowlist, *, meter=None):
        captured.update(query=query, allowlist=allowlist, meter=meter)
        return ["https://pubmed.ncbi.nlm.nih.gov/12345/"]

    monkeypatch.setattr(search, "_search_pubmed", fake_pubmed)

    assert search.search_web("query", PUBMED_ALLOWLIST) == [
        "https://pubmed.ncbi.nlm.nih.gov/12345/"
    ]
    assert captured == {"query": "query", "allowlist": PUBMED_ALLOWLIST, "meter": None}


def test_search_pubmed_adds_api_key_only_when_configured(monkeypatch, pubmed_settings):
    params_seen: list[dict] = []

    def fake_get(*args, **kwargs):
        params_seen.append(kwargs["params"])
        return _Response({"esearchresult": {"idlist": []}})

    monkeypatch.setattr(httpx, "get", fake_get)

    search._search_pubmed("query", PUBMED_ALLOWLIST)
    pubmed_settings.ncbi_api_key = "test-key"
    search._search_pubmed("query", PUBMED_ALLOWLIST)

    assert "api_key" not in params_seen[0]
    assert params_seen[1]["api_key"] == "test-key"


# ---------- _pubmed_query: câu mệnh đề -> từ khoá ESearch ----------


def test_pubmed_query_strips_esearch_operator_chars():
    """Dấu ngoặc là toán tử boolean của ESearch, không phải chữ - để nguyên thì trả về 0 kết quả."""
    trimmed = search._pubmed_query("Acute liver failure (acetaminophen poisoning acceptable)")
    assert "(" not in trimmed and ")" not in trimmed
    assert "acetaminophen" in trimmed and "poisoning" in trimmed


def test_pubmed_query_drops_recommendation_and_filler_words():
    trimmed = search._pubmed_query(
        "COPD exacerbation in elderly patients with purulent sputum requires clinical evaluation"
    )
    for dropped in ("in", "with", "requires", "clinical", "evaluation", "patients"):
        assert dropped not in trimmed.split()
    for kept in ("COPD", "exacerbation", "elderly", "purulent", "sputum"):
        assert kept in trimmed.split()


def test_pubmed_query_caps_term_count():
    long_claim = " ".join(f"term{index}" for index in range(30))
    assert len(search._pubmed_query(long_claim).split()) == search._PUBMED_MAX_TERMS


def test_pubmed_query_falls_back_when_everything_is_filtered():
    """Chuỗi rỗng khiến ESearch khớp toàn bộ PubMed, nên phải trả lại câu gốc."""
    assert search._pubmed_query("the patient requires clinical evaluation") == (
        "the patient requires clinical evaluation"
    )


def test_search_pubmed_sends_the_trimmed_term(monkeypatch, pubmed_settings):
    captured: dict = {}

    def fake_get(url, *, params, timeout):
        captured.update(params=params)
        return _Response({"esearchresult": {"idlist": []}})

    monkeypatch.setattr(httpx, "get", fake_get)

    claim = "Acute appendicitis in patients with fever requires clinical evaluation"
    search._search_pubmed(claim, PUBMED_ALLOWLIST)

    assert captured["params"]["term"] == search._pubmed_query(claim)
    assert captured["params"]["term"] != claim


# ---------- auto (chain gemini -> tavily -> pubmed) ----------


@pytest.fixture
def auto_settings(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "source_support_search_provider", "auto")
    return settings


def test_chain_stops_at_first_provider_with_urls(monkeypatch, auto_settings):
    def unexpected(*args, **kwargs):
        raise AssertionError("should not be called: gemini already returned URLs")

    monkeypatch.setattr(search, "_search_gemini", lambda *a, **k: ["https://who.int/x"])
    monkeypatch.setattr(search, "_search_tavily", unexpected)
    monkeypatch.setattr(search, "_search_pubmed", unexpected)

    assert search._search_chain("query", PUBMED_ALLOWLIST) == ["https://who.int/x"]


def test_chain_falls_through_empty_results(monkeypatch, auto_settings):
    monkeypatch.setattr(search, "_search_gemini", lambda *a, **k: [])
    monkeypatch.setattr(search, "_search_tavily", lambda *a, **k: [])
    monkeypatch.setattr(search, "_search_pubmed", lambda *a, **k: ["https://pubmed.ncbi.nlm.nih.gov/1/"])

    assert search._search_chain("query", PUBMED_ALLOWLIST) == ["https://pubmed.ncbi.nlm.nih.gov/1/"]


def test_chain_falls_through_on_exception(monkeypatch, auto_settings):
    def raises(*args, **kwargs):
        raise httpx.HTTPError("gemini 429")

    monkeypatch.setattr(search, "_search_gemini", raises)
    monkeypatch.setattr(search, "_search_tavily", lambda *a, **k: ["https://cdc.gov/x"])
    monkeypatch.setattr(
        search, "_search_pubmed", lambda *a, **k: (_ for _ in ()).throw(AssertionError("unreachable"))
    )

    assert search._search_chain("query", PUBMED_ALLOWLIST) == ["https://cdc.gov/x"]


def test_chain_returns_empty_when_everything_fails(monkeypatch, auto_settings):
    monkeypatch.setattr(search, "_search_gemini", lambda *a, **k: [])
    monkeypatch.setattr(search, "_search_tavily", lambda *a, **k: (_ for _ in ()).throw(httpx.HTTPError("no key")))
    monkeypatch.setattr(search, "_search_pubmed", lambda *a, **k: [])

    assert search._search_chain("query", PUBMED_ALLOWLIST) == []


def test_search_web_dispatches_to_auto(monkeypatch, auto_settings):
    captured: dict = {}

    def fake_chain(query, allowlist, *, meter=None):
        captured.update(query=query, allowlist=allowlist, meter=meter)
        return ["https://who.int/x"]

    monkeypatch.setattr(search, "_search_chain", fake_chain)
    monkeypatch.setattr(
        search, "_search_gemini", lambda *a, **k: (_ for _ in ()).throw(AssertionError("unreachable"))
    )

    assert search.search_web("query", PUBMED_ALLOWLIST) == ["https://who.int/x"]
    assert captured == {"query": "query", "allowlist": PUBMED_ALLOWLIST, "meter": None}
