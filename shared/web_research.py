"""Reusable web research layer for agent runs.

The service intentionally starts with safe, source-oriented browsing:
Tavily search/extract first, then a static HTML fallback for public pages.
It does not run an interactive browser yet; that can be added behind this
interface later without changing the agent runner.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from ipaddress import ip_address
import logging
import re
import socket
from typing import Any, Iterable
from urllib.parse import urlparse

import requests

from shared.tavily_client import get_tavily_client

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "PhronesisAIResearchBot/0.1 "
    "(financial research; contact: research@finance-agent.com)"
)


@dataclass
class WebSource:
    title: str
    url: str
    content: str = ""
    source_type: str = "search"


@dataclass
class WebResearchResult:
    query: str
    answer: str
    sources: list[WebSource]


class _ReadableTextParser(HTMLParser):
    """Small stdlib HTML text extractor for static fallback pages."""

    _SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas", "iframe"}

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self._SKIP_TAGS:
            self._skip_depth += 1
        if tag.lower() in {"p", "br", "li", "tr", "h1", "h2", "h3", "h4"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        if tag.lower() in {"p", "li", "tr", "h1", "h2", "h3", "h4"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip()
        if text:
            self._parts.append(text)

    def text(self) -> str:
        raw = " ".join(self._parts)
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n\s+", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def _compact_text(value: str, *, max_chars: int) -> str:
    compact = re.sub(r"\s+", " ", (value or "")).strip()
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1].rstrip() + "..."


def _is_public_http_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False

    hostname = parsed.hostname.lower()
    if hostname in {"localhost", "0.0.0.0"} or hostname.endswith(".local"):
        return False

    try:
        resolved = socket.getaddrinfo(hostname, None)
    except OSError:
        # Let requests/Tavily fail naturally if DNS is unavailable.
        return True

    for item in resolved:
        address = item[4][0]
        try:
            ip = ip_address(address)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
            return False
    return True


class WebResearchService:
    """Search and extract public web context for finance agents."""

    def __init__(self, *, user_agent: str = DEFAULT_USER_AGENT, request_timeout: int = 12) -> None:
        self.user_agent = user_agent
        self.request_timeout = request_timeout

    def search(
        self,
        query: str,
        *,
        topic: str = "finance",
        max_results: int = 5,
        time_range: str | None = None,
        include_domains: list[str] | None = None,
    ) -> WebResearchResult:
        tavily = get_tavily_client()
        result = tavily.search(
            query=query,
            topic=topic,
            search_depth="advanced",
            max_results=max_results,
            include_answer="advanced",
            time_range=time_range,
            include_domains=include_domains,
        )
        sources = [
            WebSource(
                title=str(item.get("title") or "Untitled source"),
                url=str(item.get("url") or ""),
                content=str(item.get("content") or ""),
                source_type="search",
            )
            for item in result.get("results", [])
            if item.get("url")
        ]
        return WebResearchResult(query=query, answer=str(result.get("answer") or ""), sources=sources)

    def extract_urls(
        self,
        urls: Iterable[str],
        *,
        query: str | None = None,
        max_sources: int = 3,
        max_chars_per_source: int = 1800,
    ) -> list[WebSource]:
        safe_urls = [url for url in urls if _is_public_http_url(url)]
        if not safe_urls:
            return []
        safe_urls = safe_urls[:max_sources]

        tavily_sources = self._extract_with_tavily(
            safe_urls,
            query=query,
            max_chars_per_source=max_chars_per_source,
        )
        found_urls = {source.url for source in tavily_sources}
        fallback_urls = [url for url in safe_urls if url not in found_urls]
        fallback_sources = [
            source
            for source in (
                self._extract_static_url(url, max_chars=max_chars_per_source)
                for url in fallback_urls
            )
            if source is not None
        ]
        return tavily_sources + fallback_sources

    def research(
        self,
        query: str,
        *,
        topic: str = "finance",
        max_results: int = 5,
        extract_top_k: int = 2,
        time_range: str | None = None,
        include_domains: list[str] | None = None,
    ) -> WebResearchResult:
        result = self.search(
            query,
            topic=topic,
            max_results=max_results,
            time_range=time_range,
            include_domains=include_domains,
        )
        extracted = self.extract_urls(
            [source.url for source in result.sources],
            query=query,
            max_sources=extract_top_k,
        )
        extracted_by_url = {source.url: source for source in extracted}
        merged_sources = [
            extracted_by_url.get(source.url)
            or WebSource(
                title=source.title,
                url=source.url,
                content=_compact_text(source.content, max_chars=800),
                source_type=source.source_type,
            )
            for source in result.sources
        ]
        return WebResearchResult(query=query, answer=result.answer, sources=merged_sources)

    def research_text(self, query: str, **kwargs: Any) -> str:
        return self.format_for_prompt(self.research(query, **kwargs))

    @staticmethod
    def format_for_prompt(result: WebResearchResult, *, max_chars: int = 6500) -> str:
        lines = [
            "WEB RESEARCH CONTEXT",
            f"Query: {result.query}",
        ]
        if result.answer:
            lines.extend(["", "Summary:", result.answer.strip()])
        if result.sources:
            lines.append("")
            lines.append("Sources and extracted context:")
            for index, source in enumerate(result.sources, start=1):
                lines.append(f"{index}. {source.title}")
                lines.append(f"   URL: {source.url}")
                if source.content:
                    lines.append(f"   Context: {_compact_text(source.content, max_chars=1200)}")
        return _compact_text("\n".join(lines), max_chars=max_chars)

    def _extract_with_tavily(
        self,
        urls: list[str],
        *,
        query: str | None,
        max_chars_per_source: int,
    ) -> list[WebSource]:
        try:
            raw = get_tavily_client().extract(
                urls,
                extract_depth="advanced",
                format="markdown",
                timeout=30,
                query=query,
            )
        except Exception as exc:
            logger.warning("Tavily extract failed: %s", exc)
            return []

        rows = raw.get("results") if isinstance(raw, dict) else None
        if not isinstance(rows, list):
            return []

        sources: list[WebSource] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            url = str(row.get("url") or "")
            content = str(row.get("raw_content") or row.get("content") or "")
            if not url or not content:
                continue
            sources.append(
                WebSource(
                    title=str(row.get("title") or urlparse(url).netloc or "Extracted source"),
                    url=url,
                    content=_compact_text(content, max_chars=max_chars_per_source),
                    source_type="tavily_extract",
                )
            )
        return sources

    def _extract_static_url(self, url: str, *, max_chars: int) -> WebSource | None:
        if not _is_public_http_url(url):
            return None
        try:
            response = requests.get(
                url,
                headers={"User-Agent": self.user_agent, "Accept": "text/html,text/plain"},
                timeout=self.request_timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Static page extraction failed for %s: %s", url, exc)
            return None

        content_type = response.headers.get("content-type", "")
        text = response.text
        if "html" in content_type.lower():
            parser = _ReadableTextParser()
            parser.feed(text)
            text = parser.text()
        else:
            text = text.strip()

        if not text:
            return None
        return WebSource(
            title=urlparse(url).netloc or "Extracted source",
            url=url,
            content=_compact_text(text, max_chars=max_chars),
            source_type="static_extract",
        )
