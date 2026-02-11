"""
Alpha Vantage API Client for Earnings Data and Transcripts

Provides free earnings history (15+ years) and earnings call transcripts.
Used as primary data source for the earnings agent, with FMP and Perplexity as fallbacks.

API Documentation: https://www.alphavantage.co/documentation/
Free tier: 25 requests/day
"""
import os
import time
import threading
import logging
from datetime import datetime, date
from typing import Dict, Optional, List

import requests
from shared.retry_utils import retry_with_backoff, RetryConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "https://www.alphavantage.co/query"
FREE_TIER_DAILY_LIMIT = 25


class AlphaVantageRateLimitError(Exception):
    """Raised when Alpha Vantage daily rate limit would be exceeded"""
    pass


class AlphaVantageClient:
    """Alpha Vantage API client with singleton pattern, caching, and rate limiting.

    Thread-safe singleton matching the pattern in data/financial_data.py.
    """

    _instance = None
    _shared_cache = {}
    _cache_lock = threading.RLock()
    _instance_lock = threading.Lock()

    # Rate tracking (shared across all instances via class vars)
    _request_count = 0
    _request_date = None
    _rate_lock = threading.Lock()

    def __new__(cls, api_key: Optional[str] = None):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, api_key: Optional[str] = None):
        if self._initialized:
            return

        self.api_key = api_key or os.getenv("ALPHA_VANTAGE_API_KEY")
        self.cache = self._shared_cache
        # TTL: 1 hour for earnings data, 24 hours for transcripts
        self.earnings_cache_ttl = 3600
        self.transcript_cache_ttl = 86400
        self._initialized = True

        if not self.api_key:
            logger.info("ALPHA_VANTAGE_API_KEY not set. Alpha Vantage features will be unavailable.")

    # =========================================================================
    # Cache helpers
    # =========================================================================

    def _get_from_cache(self, cache_key: str, ttl: int) -> Optional[Dict]:
        with self._cache_lock:
            if cache_key in self.cache:
                entry = self.cache[cache_key]
                if time.time() - entry["timestamp"] < ttl:
                    logger.info(f"Cache hit for {cache_key}")
                    return entry["data"]
                else:
                    logger.info(f"Cache expired for {cache_key}")
                    del self.cache[cache_key]
        return None

    def _save_to_cache(self, cache_key: str, data) -> None:
        with self._cache_lock:
            self.cache[cache_key] = {"data": data, "timestamp": time.time()}
            logger.info(f"Cached {cache_key}")

    # =========================================================================
    # Rate limiting
    # =========================================================================

    def _reset_if_new_day(self) -> None:
        """Reset counter if it's a new day (midnight UTC)."""
        today = date.today()
        with self._rate_lock:
            if self._request_date != today:
                AlphaVantageClient._request_date = today
                AlphaVantageClient._request_count = 0

    def _check_rate_limit(self, cost: int = 1) -> None:
        """Raise AlphaVantageRateLimitError if making `cost` requests would exceed daily limit."""
        self._reset_if_new_day()
        with self._rate_lock:
            if self._request_count + cost > FREE_TIER_DAILY_LIMIT:
                remaining = FREE_TIER_DAILY_LIMIT - self._request_count
                raise AlphaVantageRateLimitError(
                    f"Alpha Vantage rate limit: need {cost} requests but only {remaining} remaining today "
                    f"({self._request_count}/{FREE_TIER_DAILY_LIMIT} used)"
                )

    def _increment_request_count(self) -> None:
        self._reset_if_new_day()
        with self._rate_lock:
            AlphaVantageClient._request_count += 1

    def get_remaining_requests(self) -> int:
        """Return how many API calls remain today."""
        self._reset_if_new_day()
        with self._rate_lock:
            return max(0, FREE_TIER_DAILY_LIMIT - self._request_count)

    # =========================================================================
    # HTTP layer
    # =========================================================================

    @retry_with_backoff(RetryConfig(
        max_attempts=3,
        base_delay=1.5,
        max_delay=30.0,
    ))
    def _make_request_with_retry(self, params: Dict) -> Dict:
        """Make Alpha Vantage request with retry (raises on failure)."""
        params["apikey"] = self.api_key
        logger.info(f"Alpha Vantage request: function={params.get('function')}, symbol={params.get('symbol', 'N/A')}")
        response = requests.get(BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        # Alpha Vantage returns error messages inside JSON
        if "Error Message" in data:
            raise ValueError(f"Alpha Vantage error: {data['Error Message']}")
        if "Note" in data and "premium" in data["Note"].lower():
            raise ValueError(f"Alpha Vantage premium required: {data['Note']}")
        if "Information" in data and "rate limit" in data.get("Information", "").lower():
            raise AlphaVantageRateLimitError(data["Information"])

        return data

    def _make_request(self, params: Dict) -> Optional[Dict]:
        """Make request with error handling. Returns None on failure."""
        if not self.api_key:
            logger.info("ALPHA_VANTAGE_API_KEY not set, skipping Alpha Vantage")
            return None

        try:
            self._increment_request_count()
            return self._make_request_with_retry(params)
        except AlphaVantageRateLimitError:
            raise  # Let caller handle rate limits explicitly
        except requests.exceptions.HTTPError as e:
            if hasattr(e, "response") and e.response is not None:
                status = e.response.status_code
                if status in (401, 403):
                    logger.error("Alpha Vantage authentication failed — check ALPHA_VANTAGE_API_KEY")
                else:
                    logger.error(f"Alpha Vantage HTTP {status}: {e}")
            return None
        except ValueError as e:
            logger.error(str(e))
            return None
        except Exception as e:
            logger.error(f"Alpha Vantage request failed: {e}")
            return None

    # =========================================================================
    # Public methods
    # =========================================================================

    def get_earnings(self, ticker: str) -> Optional[Dict]:
        """Fetch full earnings history (annual + quarterly).

        Uses EARNINGS function — 1 API call returns all history.
        Returns dict with 'annualEarnings' and 'quarterlyEarnings' arrays.
        """
        cache_key = f"av_earnings_{ticker.upper()}"
        cached = self._get_from_cache(cache_key, self.earnings_cache_ttl)
        if cached is not None:
            return cached

        self._check_rate_limit(cost=1)
        data = self._make_request({
            "function": "EARNINGS",
            "symbol": ticker.upper(),
        })

        if not data:
            return None

        quarterly = data.get("quarterlyEarnings", [])
        annual = data.get("annualEarnings", [])

        if not quarterly and not annual:
            logger.warning(f"Alpha Vantage returned empty earnings for {ticker}")
            return None

        logger.info(f"Alpha Vantage earnings for {ticker}: {len(quarterly)} quarterly, {len(annual)} annual records")
        self._save_to_cache(cache_key, data)
        return data

    def get_earnings_transcript(self, ticker: str, quarter: str) -> Optional[Dict]:
        """Fetch a single earnings call transcript.

        Args:
            ticker: Stock ticker (e.g. "AAPL")
            quarter: Quarter identifier (e.g. "2024Q4")

        Returns dict with keys: symbol, quarter, year, transcript (list of segments).
        Each segment has: speaker, text, role.
        """
        cache_key = f"av_transcript_{ticker.upper()}_{quarter}"
        cached = self._get_from_cache(cache_key, self.transcript_cache_ttl)
        if cached is not None:
            return cached

        self._check_rate_limit(cost=1)

        # Parse quarter string "2024Q4" -> year=2024, quarter=4
        try:
            year_str = quarter[:4]
            q_num = quarter[-1]
        except (IndexError, ValueError):
            logger.error(f"Invalid quarter format '{quarter}' — expected e.g. '2024Q4'")
            return None

        data = self._make_request({
            "function": "EARNINGS_CALL_TRANSCRIPT",
            "symbol": ticker.upper(),
            "quarter": q_num,
            "year": year_str,
        })

        if not data:
            return None

        # AV returns transcript as list of segments
        transcript_segments = data.get("transcript", [])
        if not transcript_segments:
            logger.info(f"No transcript content for {ticker} {quarter}")
            return None

        logger.info(f"Fetched Alpha Vantage transcript for {ticker} {quarter}: {len(transcript_segments)} segments")
        self._save_to_cache(cache_key, data)
        return data

    def get_available_quarters(self, ticker: str) -> List[str]:
        """Derive available quarter identifiers from earnings history.

        Returns list like ["2024Q4", "2024Q3", "2024Q2", ...] sorted newest first.
        """
        earnings = self.get_earnings(ticker)
        if not earnings:
            return []

        quarterly = earnings.get("quarterlyEarnings", [])
        quarters = []
        for entry in quarterly:
            fiscal_date = entry.get("fiscalDateEnding", "")
            q_label = self._fiscal_date_to_quarter(fiscal_date)
            if q_label:
                quarters.append(q_label)

        # Deduplicate preserving order (newest first from API)
        seen = set()
        unique = []
        for q in quarters:
            if q not in seen:
                seen.add(q)
                unique.append(q)

        return unique

    def get_batch_transcripts(self, ticker: str, num_quarters: int = 1) -> Optional[List[Dict]]:
        """Fetch transcripts for the last N quarters.

        Cost: 1 call for get_available_quarters (if not cached) + N calls for transcripts.
        Checks rate limit upfront for the full batch.

        Returns list of transcript dicts, or None if no transcripts available.
        """
        available = self.get_available_quarters(ticker)
        if not available:
            logger.info(f"No available quarters for {ticker}")
            return None

        target_quarters = available[:num_quarters]

        # Check if we have enough budget for all transcripts
        try:
            self._check_rate_limit(cost=len(target_quarters))
        except AlphaVantageRateLimitError as e:
            logger.warning(f"Alpha Vantage rate limit — skipping batch transcripts: {e}")
            return None

        transcripts = []
        for quarter in target_quarters:
            transcript = self.get_earnings_transcript(ticker, quarter)
            if transcript:
                transcripts.append(transcript)

        if not transcripts:
            return None

        logger.info(f"Fetched {len(transcripts)}/{len(target_quarters)} transcripts for {ticker}")
        return transcripts

    # =========================================================================
    # Helpers
    # =========================================================================

    @staticmethod
    def _fiscal_date_to_quarter(fiscal_date_ending: str) -> Optional[str]:
        """Convert fiscal date ending to quarter label.

        "2024-12-31" -> "2024Q4"
        "2024-09-30" -> "2024Q3"
        """
        if not fiscal_date_ending or len(fiscal_date_ending) < 7:
            return None

        try:
            dt = datetime.strptime(fiscal_date_ending, "%Y-%m-%d")
        except ValueError:
            return None

        # Map month to fiscal quarter
        month = dt.month
        if month <= 3:
            q = 1
        elif month <= 6:
            q = 2
        elif month <= 9:
            q = 3
        else:
            q = 4

        return f"{dt.year}Q{q}"
