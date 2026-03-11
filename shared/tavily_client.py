"""
Shared Tavily search client for financial data queries.

Singleton wrapper around tavily-python SDK with retry logic and caching.
Replaces Perplexity API calls across all tool files.
"""

import os
import logging
from typing import Optional, Dict, List, Any
from dotenv import load_dotenv
from shared.retry_utils import retry_with_backoff, RetryConfig

load_dotenv()

logger = logging.getLogger(__name__)

# Singleton instance
_tavily_client_instance = None

# Curated domain lists by topic
FINANCE_DOMAINS = [
    "finance.yahoo.com",
    "reuters.com",
    "bloomberg.com",
    "wsj.com",
    "ft.com",
    "seekingalpha.com",
    "morningstar.com",
    "macrotrends.net",
    "sec.gov",
    "marketwatch.com",
    "cnbc.com",
    "barrons.com",
    "investing.com",
    "fool.com",
]

NEWS_DOMAINS = [
    "reuters.com",
    "bloomberg.com",
    "cnbc.com",
    "wsj.com",
    "ft.com",
    "marketwatch.com",
    "barrons.com",
    "finance.yahoo.com",
    "seekingalpha.com",
    "thestreet.com",
    "businessinsider.com",
    "forbes.com",
]

EARNINGS_DOMAINS = [
    "seekingalpha.com",
    "finance.yahoo.com",
    "reuters.com",
    "bloomberg.com",
    "cnbc.com",
    "marketwatch.com",
    "barrons.com",
    "fool.com",
    "sec.gov",
    "earningswhispers.com",
    "zacks.com",
]

# Map topic to default domain list
DEFAULT_DOMAINS = {
    "finance": FINANCE_DOMAINS,
    "news": NEWS_DOMAINS,
}


class TavilySearchClient:
    """Wrapper around Tavily SDK with retry logic for financial searches."""

    def __init__(self):
        self.api_key = os.getenv("TAVILY_API_KEY")
        if not self.api_key:
            logger.warning("TAVILY_API_KEY not found in environment variables")
            self._client = None
        else:
            from tavily import TavilyClient
            self._client = TavilyClient(api_key=self.api_key)

    @retry_with_backoff(RetryConfig(
        max_attempts=3,
        base_delay=1.5,
        max_delay=45.0
    ))
    def _execute_search(self, **kwargs) -> Dict:
        """Execute Tavily search with retry logic."""
        if not self._client:
            raise ValueError("TAVILY_API_KEY not configured")
        return self._client.search(**kwargs)

    def search(
        self,
        query: str,
        topic: str = "finance",
        search_depth: str = "advanced",
        max_results: int = 5,
        include_answer: str = "advanced",
        time_range: Optional[str] = None,
        include_domains: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Perform a Tavily search optimized for financial queries.

        Args:
            query: Search query string
            topic: Search topic - "finance", "news", or "general"
            search_depth: "basic" or "advanced"
            max_results: Number of results to return (1-10)
            include_answer: "basic", "advanced", or False
            time_range: Optional time filter - "day", "week", "month", "year"
            include_domains: Optional list of domains to search. If None, uses
                curated defaults for the topic (finance/news). Pass an empty
                list [] to disable domain filtering.

        Returns:
            Dict with keys:
                - answer: AI-generated answer based on search results
                - results: List of dicts with title, url, content
        """
        if not self._client:
            raise ValueError(
                "TAVILY_API_KEY not found in environment variables. "
                "Please add it to your .env file."
            )

        kwargs = {
            "query": query,
            "topic": topic,
            "search_depth": search_depth,
            "max_results": max_results,
            "include_answer": include_answer,
        }

        if time_range:
            kwargs["time_range"] = time_range

        # Apply domain filtering: explicit override > topic defaults
        if include_domains is not None:
            if include_domains:  # non-empty list = use those domains
                kwargs["include_domains"] = include_domains
            # empty list = no filtering (skip)
        elif topic in DEFAULT_DOMAINS:
            kwargs["include_domains"] = DEFAULT_DOMAINS[topic]

        raw_result = self._execute_search(**kwargs)

        # Normalize the response
        answer = raw_result.get("answer", "")
        results = []
        for r in raw_result.get("results", []):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
            })

        return {
            "answer": answer,
            "results": results,
        }

    def search_text(
        self,
        query: str,
        topic: str = "finance",
        search_depth: str = "advanced",
        max_results: int = 5,
        include_answer: str = "advanced",
        time_range: Optional[str] = None,
        include_domains: Optional[List[str]] = None,
    ) -> str:
        """
        Convenience method: search and return answer + source URLs as a formatted string.

        Returns:
            Formatted string with the AI answer and source URLs.
        """
        result = self.search(
            query=query,
            topic=topic,
            search_depth=search_depth,
            max_results=max_results,
            include_answer=include_answer,
            time_range=time_range,
            include_domains=include_domains,
        )

        output = result.get("answer") or "No answer generated."

        # Append source URLs
        sources = result.get("results", [])
        if sources:
            output += "\n\nSources:\n"
            for s in sources[:5]:
                title = s.get("title", "")
                url = s.get("url", "")
                if title and url:
                    output += f"- {title}: {url}\n"

        return output


def get_tavily_client() -> TavilySearchClient:
    """Get singleton Tavily client instance."""
    global _tavily_client_instance
    if _tavily_client_instance is None:
        _tavily_client_instance = TavilySearchClient()
    return _tavily_client_instance
