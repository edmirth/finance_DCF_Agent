"""
SEC EDGAR API Client for Corporate Filings and Financial Data

Provides free access to:
- 10-K (annual), 10-Q (quarterly), 8-K (current event) filings
- XBRL-structured financial data
- CIK lookup for any public company

No API key required. SEC only requires a User-Agent header.
Rate limit: up to 10 requests/second; we cap at ~5 req/sec (200ms between requests).

API Docs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
"""
import os
import re
import time
import threading
import logging
from typing import Dict, Optional, List, Any

import requests
from shared.retry_utils import retry_with_backoff, RetryConfig

logger = logging.getLogger(__name__)

# SEC EDGAR base URLs
SUBMISSIONS_BASE = "https://data.sec.gov/submissions"
XBRL_BASE = "https://data.sec.gov/api/xbrl"
ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# SEC requires this header; use a descriptive app name + contact email
SEC_USER_AGENT = "FinanceDCFAgent research@finance-agent.com"

# Cache TTLs (seconds)
TTL_CIK_MAP = 7 * 24 * 3600       # 7 days — tickers rarely change
TTL_FILINGS_LIST = 24 * 3600      # 1 day — new filings appear daily
TTL_FILING_CONTENT = 7 * 24 * 3600  # 7 days — filing content never changes
TTL_COMPANY_FACTS = 24 * 3600     # 1 day — XBRL data refreshes with new filings

# Minimum delay between requests to stay well under SEC rate limit
REQUEST_DELAY_SECONDS = 0.2


class SECEdgarClient:
    """Thread-safe singleton SEC EDGAR client with caching and retry logic.

    Follows the same architecture as data/financial_data.py.
    No API key needed — SEC EDGAR is fully public.
    """

    _instance = None
    _shared_cache: Dict[str, Any] = {}
    _cache_lock = threading.RLock()
    _instance_lock = threading.Lock()

    # Rate limiting: track last request time to enforce minimum delay
    _last_request_time: float = 0.0
    _rate_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.cache = self._shared_cache
        self.headers = {
            "User-Agent": SEC_USER_AGENT,
            "Accept": "application/json",
        }
        self._initialized = True
        logger.info("SECEdgarClient initialized (no API key required)")

    # =========================================================================
    # Cache helpers
    # =========================================================================

    def _get_from_cache(self, cache_key: str, ttl: int) -> Optional[Any]:
        with self._cache_lock:
            if cache_key in self.cache:
                entry = self.cache[cache_key]
                if time.time() - entry["timestamp"] < ttl:
                    logger.debug(f"SEC cache hit: {cache_key}")
                    return entry["data"]
                else:
                    del self.cache[cache_key]
        return None

    def _save_to_cache(self, cache_key: str, data: Any) -> None:
        with self._cache_lock:
            self.cache[cache_key] = {"data": data, "timestamp": time.time()}
            logger.debug(f"SEC cached: {cache_key}")

    # =========================================================================
    # Rate limiting
    # =========================================================================

    def _wait_for_rate_limit(self) -> None:
        """Enforce minimum gap between requests (200ms = 5 req/sec max)."""
        with self._rate_lock:
            elapsed = time.time() - SECEdgarClient._last_request_time
            if elapsed < REQUEST_DELAY_SECONDS:
                time.sleep(REQUEST_DELAY_SECONDS - elapsed)
            SECEdgarClient._last_request_time = time.time()

    # =========================================================================
    # HTTP layer
    # =========================================================================

    @retry_with_backoff(RetryConfig(
        max_attempts=3,
        base_delay=1.5,
        max_delay=30.0,
    ))
    def _get_json_with_retry(self, url: str) -> Any:
        """Fetch JSON from URL with retry (raises on failure)."""
        self._wait_for_rate_limit()
        logger.info(f"SEC EDGAR request: {url}")
        response = requests.get(url, headers=self.headers, timeout=30)
        response.raise_for_status()
        return response.json()

    @retry_with_backoff(RetryConfig(
        max_attempts=3,
        base_delay=1.5,
        max_delay=30.0,
    ))
    def _get_text_with_retry(self, url: str) -> str:
        """Fetch raw text/HTML from URL with retry (raises on failure)."""
        self._wait_for_rate_limit()
        logger.info(f"SEC EDGAR text request: {url}")
        response = requests.get(
            url,
            headers={**self.headers, "Accept": "text/html,application/xhtml+xml,text/plain"},
            timeout=60,
            stream=False,
        )
        response.raise_for_status()
        return response.text

    def _get_json(self, url: str) -> Optional[Any]:
        """Fetch JSON with error handling. Returns None on failure."""
        try:
            return self._get_json_with_retry(url)
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            if status == 404:
                logger.info(f"SEC EDGAR: not found ({url})")
            elif status == 429:
                logger.warning(f"SEC EDGAR: rate limited ({url})")
            else:
                logger.error(f"SEC EDGAR HTTP {status}: {url}")
            return None
        except Exception as e:
            logger.error(f"SEC EDGAR request failed ({url}): {e}")
            return None

    def _get_text(self, url: str) -> Optional[str]:
        """Fetch text/HTML with error handling. Returns None on failure."""
        try:
            return self._get_text_with_retry(url)
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            logger.error(f"SEC EDGAR HTTP {status}: {url}")
            return None
        except Exception as e:
            logger.error(f"SEC EDGAR text request failed ({url}): {e}")
            return None

    # =========================================================================
    # CIK lookup
    # =========================================================================

    def _load_ticker_cik_map(self) -> Dict[str, str]:
        """Load and cache the full SEC ticker→CIK mapping.

        The bulk JSON at /files/company_tickers.json maps every public company.
        Returns dict of UPPER_TICKER -> zero-padded 10-digit CIK string.
        """
        cache_key = "sec_ticker_cik_map"
        cached = self._get_from_cache(cache_key, TTL_CIK_MAP)
        if cached is not None:
            return cached

        data = self._get_json(COMPANY_TICKERS_URL)
        if not data:
            logger.error("Failed to load SEC company tickers map")
            return {}

        # data = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
        ticker_map: Dict[str, str] = {}
        for entry in data.values():
            ticker = entry.get("ticker", "").upper().strip()
            cik_str = str(entry.get("cik_str", "")).strip()
            if ticker and cik_str:
                # Zero-pad CIK to 10 digits
                ticker_map[ticker] = cik_str.zfill(10)

        logger.info(f"SEC ticker map loaded: {len(ticker_map)} companies")
        self._save_to_cache(cache_key, ticker_map)
        return ticker_map

    def get_cik(self, ticker: str) -> Optional[str]:
        """Get zero-padded 10-digit CIK for a ticker symbol.

        Returns None if the ticker is not found in SEC EDGAR.
        """
        ticker_upper = ticker.upper().strip()
        ticker_map = self._load_ticker_cik_map()
        cik = ticker_map.get(ticker_upper)
        if not cik:
            logger.warning(f"SEC EDGAR: CIK not found for ticker '{ticker}'")
        return cik

    # =========================================================================
    # Filings
    # =========================================================================

    def _get_submissions(self, cik: str) -> Optional[Dict]:
        """Fetch company submissions (filing index) from SEC."""
        cache_key = f"sec_submissions_{cik}"
        cached = self._get_from_cache(cache_key, TTL_FILINGS_LIST)
        if cached is not None:
            return cached

        url = f"{SUBMISSIONS_BASE}/CIK{cik}.json"
        data = self._get_json(url)
        if data:
            self._save_to_cache(cache_key, data)
        return data

    def get_recent_filings(
        self,
        ticker: str,
        filing_type: str = "10-K",
        limit: int = 5,
    ) -> List[Dict]:
        """Get metadata for the most recent filings of a given type.

        Args:
            ticker: Stock ticker symbol
            filing_type: "10-K", "10-Q", "8-K", etc.
            limit: Maximum number of filings to return

        Returns:
            List of dicts with keys:
                - filing_type: str
                - filing_date: str (YYYY-MM-DD)
                - accession_number: str (formatted with hyphens)
                - primary_document: str (filename of main document)
                - document_url: str (direct URL to primary document)
                - report_date: str (period of report, YYYY-MM-DD)
        """
        cik = self.get_cik(ticker)
        if not cik:
            return []

        submissions = self._get_submissions(cik)
        if not submissions:
            return []

        recent = submissions.get("filings", {}).get("recent", {})
        if not recent:
            return []

        forms = recent.get("form", [])
        filing_dates = recent.get("filingDate", [])
        accession_numbers = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])
        report_dates = recent.get("reportDate", [])

        results = []
        for i, form in enumerate(forms):
            if form != filing_type:
                continue
            if i >= len(accession_numbers):
                break

            accn = accession_numbers[i]
            accn_no_hyphens = accn.replace("-", "")
            primary_doc = primary_docs[i] if i < len(primary_docs) else ""
            filing_date = filing_dates[i] if i < len(filing_dates) else ""
            report_date = report_dates[i] if i < len(report_dates) else ""

            # Build direct URL to the primary document
            document_url = (
                f"{ARCHIVES_BASE}/{int(cik)}/{accn_no_hyphens}/{primary_doc}"
                if primary_doc else ""
            )

            results.append({
                "filing_type": form,
                "filing_date": filing_date,
                "accession_number": accn,
                "primary_document": primary_doc,
                "document_url": document_url,
                "report_date": report_date,
                "cik": cik,
            })

            if len(results) >= limit:
                break

        logger.info(f"SEC: found {len(results)} {filing_type} filings for {ticker}")
        return results

    def get_recent_8k(self, ticker: str, limit: int = 5) -> List[Dict]:
        """Get recent 8-K (material event) filings.

        Convenience wrapper around get_recent_filings for 8-K type.
        """
        return self.get_recent_filings(ticker, filing_type="8-K", limit=limit)

    # =========================================================================
    # Filing content
    # =========================================================================

    def get_filing_text(self, accession_number: str, cik: str, primary_document: str) -> Optional[str]:
        """Fetch and extract text content from a SEC filing document.

        Fetches the HTML/text filing and strips markup to return clean text.
        Truncates to 15,000 characters to keep LLM context manageable.

        Args:
            accession_number: Formatted accession number (e.g. "0000320193-24-000123")
            cik: Zero-padded 10-digit CIK
            primary_document: Primary document filename (e.g. "aapl-20240928.htm")

        Returns:
            Extracted plain text from the filing, or None on failure.
        """
        cache_key = f"sec_filing_text_{accession_number}"
        cached = self._get_from_cache(cache_key, TTL_FILING_CONTENT)
        if cached is not None:
            return cached

        accn_no_hyphens = accession_number.replace("-", "")
        cik_int = int(cik)  # Remove leading zeros for the path
        url = f"{ARCHIVES_BASE}/{cik_int}/{accn_no_hyphens}/{primary_document}"

        raw = self._get_text(url)
        if not raw:
            return None

        text = self._strip_html(raw)

        # Truncate to keep context manageable — 100K chars covers most of a 10-K
        # (15K was too small: financial statements appear well past the first 15K chars)
        if len(text) > 100000:
            text = text[:100000] + "\n\n[... document truncated for brevity ...]"

        self._save_to_cache(cache_key, text)
        return text

    @staticmethod
    def _strip_html(html: str) -> str:
        """Strip HTML tags and normalize whitespace from filing content."""
        # Remove script and style blocks
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        # Remove all remaining HTML tags
        text = re.sub(r"<[^>]+>", " ", text)
        # Decode common HTML entities
        text = (
            text
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&nbsp;", " ")
            .replace("&#160;", " ")
            .replace("&ldquo;", '"')
            .replace("&rdquo;", '"')
            .replace("&mdash;", "—")
            .replace("&ndash;", "–")
        )
        # Collapse whitespace (preserve paragraph breaks as double newlines)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    # =========================================================================
    # XBRL structured financials
    # =========================================================================

    def get_company_facts(self, ticker: str) -> Optional[Dict]:
        """Fetch XBRL-structured financial facts for a company.

        Returns the full companyfacts JSON from SEC, containing time-series
        data for every reported financial metric using US-GAAP taxonomy.
        """
        cik = self.get_cik(ticker)
        if not cik:
            return None

        cache_key = f"sec_company_facts_{cik}"
        cached = self._get_from_cache(cache_key, TTL_COMPANY_FACTS)
        if cached is not None:
            return cached

        url = f"{XBRL_BASE}/companyfacts/CIK{cik}.json"
        data = self._get_json(url)
        if data:
            self._save_to_cache(cache_key, data)
        return data

    def get_financial_concept(
        self,
        ticker: str,
        concept: str,
        taxonomy: str = "us-gaap",
        unit: str = "USD",
        annual_only: bool = True,
        limit: int = 10,
    ) -> List[Dict]:
        """Get time-series data for a specific financial concept.

        Args:
            ticker: Stock ticker symbol
            concept: US-GAAP concept name (e.g. "Revenues", "NetIncomeLoss")
            taxonomy: "us-gaap" (default) or "dei"
            unit: "USD" for dollar amounts, "shares" for share counts, "USD/shares" for EPS
            annual_only: If True, return only FY annual data (form 10-K)
            limit: Maximum number of data points to return (newest first)

        Returns:
            List of dicts: [{period, value, form, filed_date}, ...]
        """
        facts = self.get_company_facts(ticker)
        if not facts:
            return []

        taxonomy_data = facts.get("facts", {}).get(taxonomy, {})
        concept_data = taxonomy_data.get(concept, {})
        if not concept_data:
            # Try case-insensitive search
            for key, val in taxonomy_data.items():
                if key.lower() == concept.lower():
                    concept_data = val
                    break

        if not concept_data:
            logger.warning(f"SEC XBRL: concept '{concept}' not found for {ticker}")
            return []

        units_data = concept_data.get("units", {}).get(unit, [])
        if not units_data:
            # Try other unit types if specified unit not found
            all_units = concept_data.get("units", {})
            for u, entries in all_units.items():
                if entries:
                    units_data = entries
                    logger.info(f"SEC XBRL: using unit '{u}' for concept '{concept}'")
                    break

        if not units_data:
            return []

        # Filter to annual 10-K data if requested
        if annual_only:
            filtered = [
                e for e in units_data
                if e.get("form") in ("10-K", "10-K/A") and e.get("fp") == "FY"
            ]
        else:
            # Include both annual and quarterly, exclude duplicates (10-K/A amendments)
            filtered = [
                e for e in units_data
                if e.get("form") in ("10-K", "10-K/A", "10-Q", "10-Q/A")
            ]

        if not filtered:
            filtered = units_data  # Fall back to all entries

        # Sort newest first and deduplicate by period end date
        filtered.sort(key=lambda x: x.get("end", ""), reverse=True)
        seen_periods = set()
        unique = []
        for entry in filtered:
            period = entry.get("end", "")
            if period and period not in seen_periods:
                seen_periods.add(period)
                unique.append({
                    "period": period,
                    "value": entry.get("val"),
                    "form": entry.get("form", ""),
                    "filed_date": entry.get("filed", ""),
                    "fiscal_year": entry.get("fy"),
                    "fiscal_period": entry.get("fp", ""),
                })

        return unique[:limit]
