"""
FRED (Federal Reserve Economic Data) Client

Fetches macro series from the St. Louis Fed FRED API and formats them
into a context block the Macro Strategist can use directly.

Singleton — one `fredapi.Fred` instance is shared across all threads.
Gracefully degrades: any series that fails (missing key, network error,
unknown ticker) is omitted from the output rather than crashing the caller.
"""
from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Series catalogue
# ---------------------------------------------------------------------------
# Each entry: (fred_series_id, human_label, units_note)
# Groups are rendered as subsections in the formatted output.
# ---------------------------------------------------------------------------

# Each entry: (fred_series_id, human_label, units_note, lookback_days)
# lookback_days accounts for release lag: daily=7, monthly=45, quarterly=120
_SERIES_CATALOGUE: dict[str, list[tuple[str, str, str, int]]] = {
    "Rates & Yield Curve": [
        ("DGS10",     "10-Year Treasury Yield",       "%",              7),
        ("DGS2",      "2-Year Treasury Yield",        "%",              7),
        ("DGS1MO",    "1-Month T-Bill Yield",         "%",              7),
        ("FEDFUNDS",  "Fed Funds Rate (effective)",   "%",             45),
        ("T10Y2Y",    "10Y–2Y Yield Spread",          "pp",             7),
        ("SOFR",      "SOFR (overnight)",             "%",              7),
    ],
    "Inflation & Prices": [
        ("CPIAUCSL",  "CPI (All Urban, SA)",          "index level",   45),
        ("CPILFESL",  "Core CPI (ex-food & energy)",  "index level",   45),
        ("PCEPI",     "PCE Price Index",              "index level",   45),
        ("PCEPILFE",  "Core PCE",                     "index level",   45),
        ("T10YIE",    "10-Year Breakeven Inflation",  "%",              7),
    ],
    "Labour & Growth": [
        ("UNRATE",    "Unemployment Rate",            "%",             45),
        ("PAYEMS",    "Nonfarm Payrolls",              "thousands SA",  45),
        ("GDPC1",     "Real GDP (quarterly)",         "bil. 2017 USD", 120),
        ("INDPRO",    "Industrial Production Index",  "index",         45),
    ],
    "Credit & Liquidity": [
        ("BAMLH0A0HYM2", "ICE BofA HY OAS",          "bp",             7),
        ("BAMLC0A0CM",   "ICE BofA IG OAS",          "bp",             7),
        ("DEXUSEU",      "USD/EUR Exchange Rate",     "USD per EUR",    7),
        ("DTWEXBGS",     "USD Broad Trade-Weight Index", "index",       7),
        ("M2SL",         "M2 Money Supply",           "bil. USD SA",   45),
    ],
}

# Map common ticker-like names users might type to the relevant series group
_TICKER_SERIES_MAP: dict[str, list[str]] = {
    "DXY":    ["DTWEXBGS", "DEXUSEU"],
    "TNX":    ["DGS10", "DGS2", "T10Y2Y"],
    "VIX":    [],        # not on FRED; handled gracefully
    "WTI":    [],        # not on FRED
    "GOLD":   [],
    "SPY":    [],
    "QQQ":    [],
    "TLT":    ["DGS10", "DGS2"],
    "GLD":    [],
    "UUP":    ["DTWEXBGS"],
    "CPI":    ["CPIAUCSL", "CPILFESL", "T10YIE"],
    "PCE":    ["PCEPI", "PCEPILFE"],
    "RATES":  ["DGS10", "DGS2", "FEDFUNDS", "T10Y2Y", "SOFR"],
    "YIELDS": ["DGS10", "DGS2", "T10Y2Y", "DGS1MO"],
    "CREDIT": ["BAMLH0A0HYM2", "BAMLC0A0CM"],
    "USD":    ["DTWEXBGS", "DEXUSEU"],
}


class FREDClient:
    """Singleton wrapper around fredapi.Fred."""

    _instance: Optional["FREDClient"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "FREDClient":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._fred = None
                    cls._instance._available = False
        return cls._instance

    def _ensure_client(self) -> bool:
        if self._fred is not None:
            return self._available
        api_key = os.getenv("FRED_API_KEY", "")
        if not api_key:
            logger.debug("FRED_API_KEY not set — FRED client disabled")
            self._available = False
            return False
        try:
            from fredapi import Fred  # type: ignore
            self._fred = Fred(api_key=api_key)
            self._available = True
            logger.info("FRED client initialised")
        except ImportError:
            logger.warning("fredapi package not installed — run: pip install fredapi")
            self._available = False
        except Exception as exc:
            logger.warning("FRED client init failed: %s", exc)
            self._available = False
        return self._available

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_series_latest(self, series_id: str, lookback_days: int = 7) -> Optional[float]:
        """Return the most recent value for a series within the last `lookback_days`."""
        if not self._ensure_client():
            return None
        try:
            since = datetime.today() - timedelta(days=lookback_days)
            data = self._fred.get_series(series_id, observation_start=since.strftime("%Y-%m-%d"))
            if data is None or data.empty:
                return None
            return float(data.dropna().iloc[-1])
        except Exception as exc:
            logger.debug("FRED series %s fetch failed: %s", series_id, exc)
            return None

    def get_macro_context_block(self, ticker: Optional[str] = None) -> str:
        """
        Return a formatted multi-line string of current macro readings.

        If `ticker` is a recognisable macro symbol (DXY, TNX, etc.) the most
        relevant series are surfaced first. Otherwise the full catalogue is
        returned grouped by category.
        """
        if not self._ensure_client():
            return ""

        lines: list[str] = ["## FRED Macro Data (latest available readings)"]
        fetched_any = False
        ticker_upper = (ticker or "").strip().upper()

        # Determine priority series from ticker mapping
        priority_series: set[str] = set()
        if ticker_upper in _TICKER_SERIES_MAP:
            priority_series = set(_TICKER_SERIES_MAP[ticker_upper])

        for group_name, series_list in _SERIES_CATALOGUE.items():
            group_lines: list[str] = []
            for series_id, label, units, lookback in series_list:
                val = self.get_series_latest(series_id, lookback_days=lookback)
                if val is None:
                    continue
                star = " *" if series_id in priority_series else ""
                group_lines.append(f"  {label}: {val:.3f} ({units}){star}")
                fetched_any = True
            if group_lines:
                lines.append(f"\n### {group_name}")
                lines.extend(group_lines)

        if not fetched_any:
            return ""

        if priority_series:
            lines.append("\n* = most relevant series for this instrument")

        return "\n".join(lines)


# Module-level singleton accessor
def get_fred_client() -> FREDClient:
    return FREDClient()
