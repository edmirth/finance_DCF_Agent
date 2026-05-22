from __future__ import annotations

from types import SimpleNamespace

import pytest

from shared import web_research
from shared.web_research import WebResearchService


class FakeTavily:
    def __init__(self, *, extract_error: Exception | None = None):
        self.extract_error = extract_error

    def search(self, **_kwargs):
        return {
            "answer": "Apple reported stronger services growth and stable margins.",
            "results": [
                {
                    "title": "Apple results recap",
                    "url": "https://example.com/apple-results",
                    "content": "Services revenue increased and iPhone demand was stable.",
                }
            ],
        }

    def extract(self, urls, **_kwargs):
        if self.extract_error:
            raise self.extract_error
        url = urls[0] if isinstance(urls, list) else urls
        return {
            "results": [
                {
                    "title": "Apple results recap",
                    "url": url,
                    "raw_content": "Management highlighted services growth, stable margins, and AI investment.",
                }
            ]
        }


def test_web_research_service_searches_and_extracts_sources(monkeypatch):
    monkeypatch.setattr(web_research, "get_tavily_client", lambda: FakeTavily())
    monkeypatch.setattr(web_research, "_is_public_http_url", lambda _url: True)

    result = WebResearchService().research("AAPL latest earnings", max_results=1, extract_top_k=1)
    formatted = WebResearchService.format_for_prompt(result)

    assert result.answer.startswith("Apple reported")
    assert result.sources[0].source_type == "tavily_extract"
    assert "Management highlighted services growth" in formatted
    assert "https://example.com/apple-results" in formatted


def test_web_research_service_falls_back_to_static_extraction(monkeypatch):
    monkeypatch.setattr(web_research, "get_tavily_client", lambda: FakeTavily(extract_error=RuntimeError("down")))
    monkeypatch.setattr(web_research, "_is_public_http_url", lambda _url: True)

    class FakeResponse:
        headers = {"content-type": "text/html"}
        text = "<html><body><h1>Headline</h1><script>ignore()</script><p>Readable source text.</p></body></html>"

        def raise_for_status(self):
            return None

    monkeypatch.setattr(web_research.requests, "get", lambda *_args, **_kwargs: FakeResponse())

    sources = WebResearchService().extract_urls(["https://example.com/story"], max_sources=1)

    assert len(sources) == 1
    assert sources[0].source_type == "static_extract"
    assert "Readable source text" in sources[0].content
    assert "ignore" not in sources[0].content


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://localhost:8000/private",
        "https://internal.local/page",
    ],
)
def test_web_research_service_rejects_non_public_urls(url):
    assert web_research._is_public_http_url(url) is False
