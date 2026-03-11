"""
FRED API client for Treasury yield lookups.

Uses the fredapi library to fetch official Federal Reserve Economic Data,
primarily the 10-year Treasury yield (DGS10) for DCF risk-free rate.
"""

import os
import time
import logging
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Singleton instance
_fred_client_instance = None

# Cache: (value, timestamp)
_cache: dict = {}
CACHE_TTL_SECONDS = 3600  # 1 hour


class FredClient:
    """Client for FRED API with caching."""

    def __init__(self):
        self.api_key = os.getenv("FRED_API_KEY")
        if not self.api_key:
            logger.warning("FRED_API_KEY not found in environment variables")
            self._client = None
        else:
            from fredapi import Fred
            self._client = Fred(api_key=self.api_key)

    def get_treasury_yield(self, series: str = "DGS10") -> Optional[float]:
        """
        Get the latest Treasury yield from FRED.

        Args:
            series: FRED series ID. Common:
                - "DGS10": 10-Year Treasury Constant Maturity Rate
                - "DGS2": 2-Year Treasury
                - "DGS30": 30-Year Treasury

        Returns:
            Latest yield as a decimal (e.g., 0.045 for 4.5%), or None if unavailable.
        """
        if not self._client:
            logger.info("FRED client not configured (no API key)")
            return None

        # Check cache
        cache_key = f"fred_{series}"
        if cache_key in _cache:
            cached_value, cached_time = _cache[cache_key]
            if time.time() - cached_time < CACHE_TTL_SECONDS:
                logger.info(f"FRED cache hit for {series}: {cached_value}")
                return cached_value

        try:
            data = self._client.get_series(series)
            if data is not None and len(data) > 0:
                # Get the latest non-NaN value
                latest = data.dropna().iloc[-1]
                # FRED returns percentage (e.g., 4.5 for 4.5%), convert to decimal
                value = float(latest) / 100.0
                logger.info(f"FRED {series}: {latest}% -> {value:.4f}")

                # Cache it
                _cache[cache_key] = (value, time.time())
                return value
            else:
                logger.warning(f"No data returned from FRED for series {series}")
                return None

        except Exception as e:
            logger.error(f"Error fetching FRED series {series}: {e}")
            return None


def get_fred_client() -> FredClient:
    """Get singleton FRED client instance."""
    global _fred_client_instance
    if _fred_client_instance is None:
        _fred_client_instance = FredClient()
    return _fred_client_instance
