"""
Market Data Provider

Abstraction layer for market data sources. Designed to be extensible
for different data providers (FMP, massive.com, yfinance, etc.)
"""

import os
import time
import logging
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
from shared.retry_utils import retry_with_backoff, RetryConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MarketDataProvider(ABC):
    """Abstract base class for market data providers"""

    @abstractmethod
    def get_indices(self) -> Dict[str, Any]:
        """Get major market indices (S&P 500, Nasdaq, etc.)"""
        pass

    @abstractmethod
    def get_sector_performance(self) -> Dict[str, Any]:
        """Get sector ETF performance"""
        pass

    @abstractmethod
    def get_market_breadth(self) -> Dict[str, Any]:
        """Get market breadth indicators (advance/decline, etc.)"""
        pass

    @abstractmethod
    def get_volatility_index(self) -> Dict[str, Any]:
        """Get VIX and other volatility measures"""
        pass

    def get_historical_context(self, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
        """Get 52-week historical context. Override in subclasses that support it."""
        return {}


class MassiveMarketData(MarketDataProvider):
    """
    Market data provider using massive.com API

    Fetches real-time market data from massive.com (formerly Polygon.io)
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("MASSIVE_API_KEY")
        self.base_url = "https://api.massive.com"
        self.use_placeholder = not self.api_key

        if not self.api_key:
            logger.warning("MASSIVE_API_KEY not found - using placeholder data")
        else:
            logger.info("Massive.com API initialized with key")

        # Index ticker mappings (massive.com uses different symbols)
        self.index_tickers = {
            "SPX": "I:SPX",      # S&P 500
            "CCMP": "I:COMP",    # Nasdaq Composite
            "INDU": "I:DJI",     # Dow Jones
            "RUT": "I:RUT"       # Russell 2000
        }

        # Sector ETF tickers
        self.sector_etfs = [
            "XLK",   # Technology
            "XLF",   # Financials
            "XLE",   # Energy
            "XLV",   # Healthcare
            "XLY",   # Consumer Discretionary
            "XLP",   # Consumer Staples
            "XLI",   # Industrials
            "XLB",   # Materials
            "XLRE",  # Real Estate
            "XLC",   # Communication
            "XLU"    # Utilities
        ]

    def get_indices(self) -> Dict[str, Any]:
        """
        Get major market indices from massive.com API

        Returns:
            {
                "SPX": {"name": "S&P 500", "price": 4783.45, "change": 35.67, "change_pct": 0.75, ...},
                "CCMP": {"name": "Nasdaq Composite", "price": 16789.23, ...},
                ...
            }
        """
        if self.use_placeholder:
            return self._get_indices_placeholder()

        try:
            # Construct API request for indices snapshot
            ticker_symbols = ",".join(self.index_tickers.values())
            url = f"{self.base_url}/v3/snapshot/indices"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            params = {"ticker": ticker_symbols}

            logger.info(f"Fetching indices from massive.com: {ticker_symbols}")
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            if data.get("status") != "OK" or not data.get("results"):
                logger.warning("No results from indices API, falling back to placeholder")
                return self._get_indices_placeholder()

            # Parse response into our format
            indices = {}
            for result in data["results"]:
                # Map massive.com ticker back to our simplified format
                ticker_map = {v: k for k, v in self.index_tickers.items()}
                our_ticker = ticker_map.get(result.get("ticker"), result.get("ticker"))

                session = result.get("session", {})
                value = result.get("value", 0)

                # Calculate change from session data
                prev_close = session.get("previous_close", value)
                change = value - prev_close if value and prev_close else 0
                change_pct = (change / prev_close * 100) if prev_close else 0

                indices[our_ticker] = {
                    "name": result.get("name", our_ticker),
                    "price": value,
                    "change": round(change, 2),
                    "change_pct": round(change_pct, 2),
                    "52w_high": None,   # session.high is intraday, not 52-week (Bug #12)
                    "52w_low": None,
                    "volume": session.get("volume", 0)
                }

            logger.info(f"Successfully fetched {len(indices)} indices from massive.com")
            return indices

        except Exception as e:
            logger.error(f"Error fetching indices from massive.com: {e}")
            logger.info("Falling back to placeholder data")
            return self._get_indices_placeholder()

    def _get_indices_placeholder(self) -> Dict[str, Any]:
        """Placeholder data for indices when API is unavailable"""
        logger.info("Using placeholder indices data")
        return {
            "_placeholder": True,
            "SPX": {
                "name": "S&P 500",
                "price": 4783.45,
                "change": 35.67,
                "change_pct": 0.75,
                "52w_high": 4800.00,
                "52w_low": 4100.00,
                "volume": 3.2e9
            },
            "CCMP": {
                "name": "Nasdaq Composite",
                "price": 16789.23,
                "change": 198.45,
                "change_pct": 1.20,
                "52w_high": 17000.00,
                "52w_low": 14500.00,
                "volume": 4.1e9
            },
            "INDU": {
                "name": "Dow Jones",
                "price": 37896.45,
                "change": 123.89,
                "change_pct": 0.33,
                "52w_high": 38000.00,
                "52w_low": 33000.00,
                "volume": 2.8e9
            },
            "RUT": {
                "name": "Russell 2000",
                "price": 2045.67,
                "change": -12.34,
                "change_pct": -0.60,
                "52w_high": 2100.00,
                "52w_low": 1700.00,
                "volume": 1.5e9
            }
        }

    def get_sector_performance(self) -> Dict[str, Any]:
        """
        Get sector ETF performance (1D, 5D, 1M, 3M, YTD) from massive.com API

        Returns sector rotation data
        """
        if self.use_placeholder:
            return self._get_sector_performance_placeholder()

        try:
            # Get current snapshot for 1D performance
            tickers_str = ",".join(self.sector_etfs)
            url = f"{self.base_url}/v2/snapshot/locale/us/markets/stocks/tickers"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            params = {"tickers": tickers_str}

            logger.info(f"Fetching sector ETF snapshots from massive.com: {tickers_str}")
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            if data.get("status") != "OK" or not data.get("tickers"):
                logger.warning("No results from stocks snapshot API, falling back to placeholder")
                return self._get_sector_performance_placeholder()

            # Sector names mapping
            sector_names = {
                "XLK": "Technology", "XLF": "Financials", "XLE": "Energy",
                "XLV": "Healthcare", "XLY": "Consumer Disc.", "XLP": "Consumer Staples",
                "XLI": "Industrials", "XLB": "Materials", "XLRE": "Real Estate",
                "XLC": "Communication", "XLU": "Utilities"
            }

            # Parse sector performance
            sectors = {}
            for ticker_data in data["tickers"]:
                ticker = ticker_data.get("ticker")
                if ticker not in self.sector_etfs:
                    continue

                # Get 1D performance from todaysChangePerc
                day_1d = ticker_data.get("todaysChangePerc", 0)

                # Only 1D is real from the snapshot; longer timeframes
                # will be filled by _enhance_with_aggregate_bars if possible
                sectors[ticker] = {
                    "name": sector_names.get(ticker, ticker),
                    "1D": round(day_1d, 1),
                    "5D": None,
                    "1M": None,
                    "3M": None,
                    "YTD": None,
                }

            # If we got real 1D data, try to enhance with aggregate bars for longer periods
            sectors = self._enhance_with_aggregate_bars(sectors)

            logger.info(f"Successfully fetched {len(sectors)} sector ETFs from massive.com")
            return sectors if sectors else self._get_sector_performance_placeholder()

        except Exception as e:
            logger.error(f"Error fetching sector performance from massive.com: {e}")
            logger.info("Falling back to placeholder data")
            return self._get_sector_performance_placeholder()

    def _enhance_with_aggregate_bars(self, sectors: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enhance sector data with historical aggregate bars for accurate timeframe performance

        This is optional - if it fails, we keep the estimates
        """
        try:
            from datetime import datetime, timedelta

            # Calculate date ranges
            today = datetime.now()
            dates = {
                "5D": (today - timedelta(days=7)).strftime("%Y-%m-%d"),
                "1M": (today - timedelta(days=35)).strftime("%Y-%m-%d"),
                "3M": (today - timedelta(days=95)).strftime("%Y-%m-%d"),
                "YTD": f"{today.year}-01-01"
            }
            to_date = today.strftime("%Y-%m-%d")

            headers = {"Authorization": f"Bearer {self.api_key}"}

            # Fetch aggregate bars for each sector — throttled to avoid rate limits (Bug #6)
            import time
            for ticker in sectors.keys():
                for timeframe, from_date in dates.items():
                    try:
                        time.sleep(0.1)  # 100ms between requests to respect rate limits
                        url = f"{self.base_url}/v2/aggs/ticker/{ticker}/range/1/day/{from_date}/{to_date}"
                        response = requests.get(url, headers=headers, params={"adjusted": "true"}, timeout=5)

                        if response.status_code == 200:
                            agg_data = response.json()
                            if agg_data.get("results") and len(agg_data["results"]) >= 2:
                                agg_results = agg_data["results"]
                                first_close = agg_results[0]["c"]
                                last_close = agg_results[-1]["c"]
                                pct_change = ((last_close - first_close) / first_close) * 100
                                sectors[ticker][timeframe] = round(pct_change, 1)

                    except Exception as e:
                        logger.debug(f"Could not fetch aggregate bars for {ticker} {timeframe}: {e}")
                        continue

            return sectors

        except Exception as e:
            logger.debug(f"Could not enhance with aggregate bars: {e}")
            return sectors

    def _get_sector_performance_placeholder(self) -> Dict[str, Any]:
        """Placeholder data for sector performance when API is unavailable"""
        logger.info("Using placeholder sector performance data")
        return {
            "_placeholder": True,
            "XLK": {"name": "Technology", "1D": 1.5, "5D": 3.2, "1M": 8.5, "3M": 15.2, "YTD": 42.3},
            "XLF": {"name": "Financials", "1D": 0.8, "5D": 2.1, "1M": 5.3, "3M": 10.8, "YTD": 18.5},
            "XLE": {"name": "Energy", "1D": -0.5, "5D": -1.2, "1M": 2.1, "3M": 8.5, "YTD": 15.2},
            "XLV": {"name": "Healthcare", "1D": 0.3, "5D": 1.5, "1M": 3.8, "3M": 7.2, "YTD": 12.5},
            "XLY": {"name": "Consumer Disc.", "1D": 1.2, "5D": 2.8, "1M": 7.5, "3M": 14.8, "YTD": 28.9},
            "XLP": {"name": "Consumer Staples", "1D": -0.2, "5D": 0.5, "1M": 1.8, "3M": 4.2, "YTD": 6.5},
            "XLI": {"name": "Industrials", "1D": 0.6, "5D": 1.8, "1M": 4.5, "3M": 9.8, "YTD": 16.7},
            "XLB": {"name": "Materials", "1D": 0.4, "5D": 1.2, "1M": 3.2, "3M": 7.5, "YTD": 11.2},
            "XLRE": {"name": "Real Estate", "1D": -0.8, "5D": -1.5, "1M": 0.5, "3M": 3.2, "YTD": 8.5},
            "XLC": {"name": "Communication", "1D": 1.1, "5D": 2.5, "1M": 6.8, "3M": 13.5, "YTD": 32.1},
            "XLU": {"name": "Utilities", "1D": -0.3, "5D": 0.2, "1M": 1.2, "3M": 2.8, "YTD": 4.5}
        }

    def get_market_breadth(self, indices: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Get market breadth indicators

        NOTE: Market breadth calculations (advance/decline, new highs/lows) require
        fetching and analyzing thousands of individual stocks, which is not practical
        with the massive.com API rate limits. These values are estimated based on
        index performance for now.

        For production use, consider:
        1. Pre-calculated breadth data from a specialized provider
        2. Batch processing of market breadth during off-hours
        3. Cached breadth calculations updated periodically

        Returns advance/decline, new highs/lows, etc.
        """
        # Use estimated breadth based on index performance
        if indices is None:
            indices = self.get_indices()

        # Estimate breadth based on how many major indices are positive
        # Filter out metadata keys (e.g. _placeholder) which are not index dicts
        index_dicts = {k: v for k, v in indices.items() if isinstance(v, dict)}
        positive_indices = sum(1 for idx in index_dicts.values() if idx.get("change_pct", 0) > 0)
        total_indices = len(index_dicts)

        # Generate estimated breadth (better correlation with actual market)
        if positive_indices >= 3:  # Strong breadth
            adv_ratio = 2.5
            hl_ratio = 4.0
        elif positive_indices >= 2:  # Moderate breadth
            adv_ratio = 1.8
            hl_ratio = 2.5
        else:  # Weak breadth
            adv_ratio = 0.9
            hl_ratio = 0.8

        logger.info(f"Estimating market breadth based on {positive_indices}/{total_indices} positive indices")

        return {
            "nyse_advance_decline": {
                "advancing": int(2000 * (adv_ratio / (adv_ratio + 1))),
                "declining": int(2000 * (1 / (adv_ratio + 1))),
                "unchanged": 100,
                "ratio": round(adv_ratio, 2)
            },
            "nasdaq_advance_decline": {
                "advancing": int(3000 * (adv_ratio / (adv_ratio + 1))),
                "declining": int(3000 * (1 / (adv_ratio + 1))),
                "unchanged": 150,
                "ratio": round(adv_ratio * 0.95, 2)  # Slightly different than NYSE
            },
            "new_highs_lows": {
                "new_52w_highs": int(200 * (hl_ratio / (hl_ratio + 1))),
                "new_52w_lows": int(200 * (1 / (hl_ratio + 1))),
                "ratio": round(hl_ratio, 2)
            },
            "percentage_above_200ma": {
                "sp500": round(max(0.0, min(100.0, 50 + (adv_ratio - 1) * 20)), 1),
                "nasdaq": round(max(0.0, min(100.0, 50 + (adv_ratio - 1) * 18)), 1),
                "russell2000": round(max(0.0, min(100.0, 50 + (adv_ratio - 1) * 15)), 1)
            },
            "_estimated": True,
            "note": "WARNING: Breadth metrics are ESTIMATED from index performance (not real advance/decline data). Do not rely on these for trading decisions."
        }

    def get_volatility_index(self) -> Dict[str, Any]:
        """
        Get VIX and volatility measures from massive.com API
        """
        if self.use_placeholder:
            return self._get_volatility_placeholder()

        try:
            # Fetch VIX from indices endpoint
            url = f"{self.base_url}/v3/snapshot/indices"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            params = {"ticker": "I:VIX"}

            logger.info("Fetching VIX from massive.com")
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            if data.get("status") != "OK" or not data.get("results"):
                logger.warning("No VIX data from API, falling back to placeholder")
                return self._get_volatility_placeholder()

            vix_data = data["results"][0]
            vix_value = vix_data.get("value", 0)
            session = vix_data.get("session", {})

            # Calculate change
            prev_close = session.get("previous_close", vix_value)
            change = vix_value - prev_close if vix_value and prev_close else 0
            change_pct = (change / prev_close * 100) if prev_close else 0

            # Classify VIX level
            if vix_value < 15:
                level = "LOW"
            elif vix_value < 20:
                level = "NORMAL"
            elif vix_value < 30:
                level = "ELEVATED"
            else:
                level = "HIGH"

            result = {
                "VIX": {
                    "value": round(vix_value, 2),
                    "change": round(change, 2),
                    "change_pct": round(change_pct, 2),
                    "level": level,
                    "percentile_1y": 50  # Would need historical data to calculate
                },
                "VVIX": {
                    "value": None,
                    "description": "Volatility of VIX (not available from this data source)",
                    "_unavailable": True,
                },
                "put_call_ratio": {
                    "ratio": None,
                    "interpretation": "UNKNOWN",
                    "_unavailable": True,
                }
            }

            logger.info(f"Successfully fetched VIX: {vix_value} ({level})")
            return result

        except Exception as e:
            logger.error(f"Error fetching VIX from massive.com: {e}")
            logger.info("Falling back to placeholder data")
            return self._get_volatility_placeholder()

    def _get_volatility_placeholder(self) -> Dict[str, Any]:
        """Placeholder data for volatility when API is unavailable"""
        logger.info("Using placeholder volatility data")
        return {
            "_placeholder": True,
            "VIX": {
                "value": 14.25,
                "change": -0.85,
                "change_pct": -5.63,
                "level": "LOW",
                "percentile_1y": 25.5
            },
            "VVIX": {
                "value": 85.34,
                "description": "Volatility of VIX"
            },
            "put_call_ratio": {
                "ratio": 0.68,
                "interpretation": "BULLISH"
            }
        }

    def get_historical_context(self, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
        """Massive.com does not provide 52-week historical context — return placeholder."""
        return {"_placeholder": True}


class FMPMarketData(MarketDataProvider):
    """
    Market data provider using FMP (Financial Modeling Prep) API

    Uses batch-quote endpoints for indices and sector ETFs, and
    historical-price-eod for multi-timeframe sector returns.
    """

    FMP_BASE = "https://financialmodelingprep.com/stable"

    INDEX_SYMBOLS = {
        "^GSPC": {"name": "S&P 500", "key": "SPX"},
        "^IXIC": {"name": "Nasdaq Composite", "key": "CCMP"},
        "^DJI":  {"name": "Dow Jones", "key": "INDU"},
        "^RUT":  {"name": "Russell 2000", "key": "RUT"},
    }

    SECTOR_ETFS = {
        "XLK": "Technology", "XLF": "Financials", "XLE": "Energy",
        "XLV": "Healthcare", "XLY": "Consumer Disc.", "XLP": "Consumer Staples",
        "XLI": "Industrials", "XLB": "Materials", "XLRE": "Real Estate",
        "XLC": "Communication", "XLU": "Utilities",
    }

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("FMP_API_KEY")
        self.use_placeholder = not self.api_key

        if not self.api_key:
            logger.warning("FMP_API_KEY not found - using placeholder market data")
        else:
            logger.info("FMP Market Data provider initialized")

    @retry_with_backoff(RetryConfig(max_attempts=3, base_delay=2.0, max_delay=60.0))
    def _fmp_get(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Any]:
        """Shared request helper for FMP API calls"""
        url = f"{self.FMP_BASE}/{endpoint}"
        request_params = {"apikey": self.api_key}
        if params:
            request_params.update(params)

        response = requests.get(url, params=request_params, timeout=10)
        if response.status_code not in (200, 400, 401, 403, 404):
            response.raise_for_status()
        return response.json()

    def get_indices(self) -> Dict[str, Any]:
        """Get major market indices via FMP batch-quote"""
        if self.use_placeholder:
            return MassiveMarketData()._get_indices_placeholder()

        try:
            symbols = ",".join(self.INDEX_SYMBOLS.keys())
            data = self._fmp_get("batch-quote", {"symbols": symbols})

            if not data:
                logger.warning("No index data from FMP, falling back to placeholder")
                return MassiveMarketData()._get_indices_placeholder()

            indices = {}
            for quote in data:
                symbol = quote.get("symbol", "")
                meta = self.INDEX_SYMBOLS.get(symbol)
                if not meta:
                    continue

                price = quote.get("price", 0) or 0
                change = quote.get("change", 0) or 0
                change_pct = quote.get("changePercentage", 0) or 0

                indices[meta["key"]] = {
                    "name": meta["name"],
                    "price": round(price, 2),
                    "change": round(change, 2),
                    "change_pct": round(change_pct, 2),
                    "52w_high": quote.get("yearHigh", price) or price,
                    "52w_low": quote.get("yearLow", price) or price,
                    "volume": quote.get("volume", 0) or 0,
                }

            if not indices:
                logger.warning("Could not parse any index data, falling back to placeholder")
                return MassiveMarketData()._get_indices_placeholder()

            logger.info(f"Successfully fetched {len(indices)} indices from FMP")
            return indices

        except Exception as e:
            logger.error(f"Error fetching indices from FMP: {e}")
            return MassiveMarketData()._get_indices_placeholder()

    def get_sector_performance(self) -> Dict[str, Any]:
        """Get sector ETF performance (1D + historical multi-timeframe) from FMP"""
        if self.use_placeholder:
            return MassiveMarketData()._get_sector_performance_placeholder()

        try:
            # Batch quote for all sector ETFs (1D data)
            symbols = ",".join(self.SECTOR_ETFS.keys())
            data = self._fmp_get("batch-quote", {"symbols": symbols})

            if not data:
                logger.warning("No sector data from FMP, falling back to placeholder")
                return MassiveMarketData()._get_sector_performance_placeholder()

            sectors = {}
            for quote in data:
                ticker = quote.get("symbol", "")
                if ticker not in self.SECTOR_ETFS:
                    continue

                day_change = quote.get("changePercentage", 0) or 0
                sectors[ticker] = {
                    "name": self.SECTOR_ETFS[ticker],
                    "1D": round(day_change, 1),
                    "5D": None,
                    "1M": None,
                    "3M": None,
                    "YTD": None,
                }

            if not sectors:
                logger.warning("Could not parse sector ETF data, falling back to placeholder")
                return MassiveMarketData()._get_sector_performance_placeholder()

            # Enhance with historical returns for 5D, 1M, 3M, YTD
            for ticker in list(sectors.keys()):
                hist_returns = self._get_historical_returns(ticker)
                if hist_returns:
                    for tf, val in hist_returns.items():
                        if val is not None:
                            sectors[ticker][tf] = round(val, 1)

            logger.info(f"Successfully fetched {len(sectors)} sector ETFs from FMP")
            return sectors

        except Exception as e:
            logger.error(f"Error fetching sector performance from FMP: {e}")
            return MassiveMarketData()._get_sector_performance_placeholder()

    def _get_historical_returns(self, ticker: str) -> Optional[Dict[str, Optional[float]]]:
        """
        Fetch historical EOD data for one ETF and calculate returns
        for 5D, 1M, 3M, and YTD timeframes.
        """
        try:
            data = self._fmp_get("historical-price-eod/full", {"symbol": ticker})

            # FMP /full endpoint returns {"symbol": "XLK", "historical": [...]} (Bug #7)
            if isinstance(data, dict) and "historical" in data:
                data = data["historical"]

            if not data or not isinstance(data, list) or len(data) < 2:
                return None

            # FMP returns newest first; build a date->close lookup
            # Limit to ~260 trading days (1 year) to avoid processing huge lists
            prices = data[:260]
            latest_close = prices[0].get("close")
            if not latest_close:
                return None

            today = datetime.now()
            targets = {
                "5D": today - timedelta(days=7),
                "1M": today - timedelta(days=35),
                "3M": today - timedelta(days=95),
                "YTD": datetime(today.year, 1, 1),
            }

            results = {}
            for tf, target_date in targets.items():
                target_str = target_date.strftime("%Y-%m-%d")
                # Find the closest date on or before the target
                best_close = None
                for row in prices:
                    row_date = row.get("date", "")
                    if row_date <= target_str:
                        best_close = row.get("close")
                        break

                if best_close and best_close > 0:
                    results[tf] = ((latest_close - best_close) / best_close) * 100
                else:
                    results[tf] = None

            return results

        except Exception as e:
            logger.debug(f"Could not fetch historical returns for {ticker}: {e}")
            return None

    def get_volatility_index(self) -> Dict[str, Any]:
        """Get VIX data from FMP"""
        if self.use_placeholder:
            return MassiveMarketData()._get_volatility_placeholder()

        try:
            data = self._fmp_get("quote", {"symbol": "^VIX"})

            if not data or not isinstance(data, list) or len(data) == 0:
                logger.warning("No VIX data from FMP, falling back to placeholder")
                return MassiveMarketData()._get_volatility_placeholder()

            vix_quote = data[0]
            vix_value = vix_quote.get("price", 0) or 0
            change = vix_quote.get("change", 0) or 0
            # Use FMP's pre-calculated percentage directly (consistent with get_indices) (Bug #5)
            change_pct = vix_quote.get("changesPercentage") or vix_quote.get("changePercentage", 0) or 0

            # Classify VIX level
            if vix_value < 15:
                level = "LOW"
            elif vix_value < 20:
                level = "NORMAL"
            elif vix_value < 30:
                level = "ELEVATED"
            else:
                level = "HIGH"

            result = {
                "VIX": {
                    "value": round(vix_value, 2),
                    "change": round(change, 2),
                    "change_pct": round(change_pct, 2),
                    "level": level,
                    "percentile_1y": 50,  # Would need historical data to calculate
                },
                "VVIX": {
                    "value": None,
                    "description": "Volatility of VIX (not available from this data source)",
                    "_unavailable": True,
                },
                "put_call_ratio": {
                    "ratio": None,
                    "interpretation": "UNKNOWN",
                    "_unavailable": True,
                },
            }

            logger.info(f"Successfully fetched VIX: {vix_value} ({level})")
            return result

        except Exception as e:
            logger.error(f"Error fetching VIX from FMP: {e}")
            return MassiveMarketData()._get_volatility_placeholder()

    def _estimate_breadth_from_indices(self) -> Dict[str, Any]:
        """Fallback: estimate breadth from index performance when real data is unavailable."""
        indices = self.get_indices()
        index_dicts = {k: v for k, v in indices.items() if isinstance(v, dict)}
        positive_indices = sum(1 for idx in index_dicts.values() if idx.get("change_pct", 0) > 0)
        total_indices = len(index_dicts)

        if positive_indices >= 3:
            adv_ratio = 2.5
            hl_ratio = 4.0
        elif positive_indices >= 2:
            adv_ratio = 1.8
            hl_ratio = 2.5
        else:
            adv_ratio = 0.9
            hl_ratio = 0.8

        logger.info(f"Estimating market breadth based on {positive_indices}/{total_indices} positive indices")

        return {
            "nyse_advance_decline": {
                "advancing": int(2000 * (adv_ratio / (adv_ratio + 1))),
                "declining": int(2000 * (1 / (adv_ratio + 1))),
                "unchanged": 100,
                "ratio": round(adv_ratio, 2)
            },
            "nasdaq_advance_decline": {
                "advancing": int(3000 * (adv_ratio / (adv_ratio + 1))),
                "declining": int(3000 * (1 / (adv_ratio + 1))),
                "unchanged": 150,
                "ratio": round(adv_ratio * 0.95, 2)
            },
            "new_highs_lows": {
                "new_52w_highs": int(200 * (hl_ratio / (hl_ratio + 1))),
                "new_52w_lows": int(200 * (1 / (hl_ratio + 1))),
                "ratio": round(hl_ratio, 2)
            },
            "percentage_above_200ma": {
                "sp500": round(max(0.0, min(100.0, 50 + (adv_ratio - 1) * 20)), 1),
                "nasdaq": round(max(0.0, min(100.0, 50 + (adv_ratio - 1) * 18)), 1),
                "russell2000": round(max(0.0, min(100.0, 50 + (adv_ratio - 1) * 15)), 1)
            },
            "_estimated": True,
            "note": "WARNING: Breadth metrics are ESTIMATED from index performance (not real advance/decline data). Do not rely on these for trading decisions."
        }

    def get_market_breadth(self) -> Dict[str, Any]:
        """
        Get real market breadth data from FMP /stable/market-breadth.

        Falls back to index-based estimation if endpoint is unavailable.
        """
        if self.use_placeholder:
            return MassiveMarketData().get_market_breadth()

        try:
            data = self._fmp_get("market-breadth")

            if data and isinstance(data, list) and len(data) > 0:
                latest = data[0]

                # FMP field names (handle variations across API versions)
                advancing = (
                    latest.get("advancing") or
                    latest.get("advancingStocks") or
                    latest.get("advance") or 0
                )
                declining = (
                    latest.get("declining") or
                    latest.get("decliningStocks") or
                    latest.get("decline") or 0
                )
                unchanged = (
                    latest.get("unchanged") or
                    latest.get("unchangedStocks") or 0
                )
                new_highs = (
                    latest.get("newHighs") or
                    latest.get("new52WeekHighs") or
                    latest.get("highs") or 0
                )
                new_lows = (
                    latest.get("newLows") or
                    latest.get("new52WeekLows") or
                    latest.get("lows") or 0
                )

                if advancing and declining:
                    ad_ratio = advancing / declining if declining > 0 else 2.5
                    hl_ratio = (
                        new_highs / new_lows if new_lows > 0
                        else (5.0 if new_highs > 0 else 1.0)
                    )

                    # % above 200MA if provided
                    pct_above = (
                        latest.get("percentAbove200Dma") or
                        latest.get("pctAbove200") or None
                    )
                    sp500_pct = (
                        round(max(0.0, min(100.0, float(pct_above))), 1)
                        if pct_above is not None
                        else round(max(0.0, min(100.0, 50 + (ad_ratio - 1) * 20)), 1)
                    )

                    logger.info(
                        f"Real breadth from FMP: {advancing} adv, {declining} dec, "
                        f"{new_highs} new highs, {new_lows} new lows"
                    )

                    return {
                        "nyse_advance_decline": {
                            "advancing": int(advancing),
                            "declining": int(declining),
                            "unchanged": int(unchanged),
                            "ratio": round(ad_ratio, 2),
                        },
                        "nasdaq_advance_decline": {
                            "advancing": int(advancing),
                            "declining": int(declining),
                            "unchanged": int(unchanged),
                            "ratio": round(ad_ratio * 0.95, 2),
                            "_derived_from_nyse": True,
                        },
                        "new_highs_lows": {
                            "new_52w_highs": int(new_highs),
                            "new_52w_lows": int(new_lows),
                            "ratio": round(hl_ratio, 2),
                        },
                        "percentage_above_200ma": {
                            "sp500": sp500_pct,
                            "nasdaq": round(max(0.0, min(100.0, 50 + (ad_ratio - 1) * 18)), 1),
                            "russell2000": round(max(0.0, min(100.0, 50 + (ad_ratio - 1) * 15)), 1),
                        },
                        "_estimated": False,
                    }

            logger.warning("FMP market-breadth returned no usable data, falling back to estimation")

        except Exception as e:
            logger.warning(f"FMP market-breadth unavailable ({e}), falling back to estimation")

        return self._estimate_breadth_from_indices()

    def get_historical_context(self, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Fetch 52-week historical context for key market metrics.

        For each symbol returns current value, 52W high/low, and percentile rank
        (0% = at 52W low, 100% = at 52W high).

        Args:
            symbols: List of FMP-compatible symbols. Defaults to ['^VIX', '^GSPC', '^IXIC'].

        Returns:
            Dict keyed by symbol with historical context data.
        """
        if self.use_placeholder:
            return {"_placeholder": True}

        if symbols is None:
            symbols = ["^VIX", "^GSPC", "^IXIC"]

        result: Dict[str, Any] = {}
        for symbol in symbols:
            try:
                data = self._fmp_get("historical-price-eod/full", {"symbol": symbol})

                # Unwrap FMP envelope (same pattern as _get_historical_returns)
                if isinstance(data, dict) and "historical" in data:
                    data = data["historical"]

                if not data or not isinstance(data, list) or len(data) < 20:
                    logger.debug(f"Insufficient historical data for {symbol}")
                    continue

                # Newest first; take up to 260 trading days (~52 weeks)
                prices = data[:260]
                closes = [p.get("close") for p in prices if p.get("close") is not None]
                if not closes:
                    continue

                current = closes[0]
                high_52w = max(closes)
                low_52w = min(closes)

                if high_52w > low_52w:
                    percentile = ((current - low_52w) / (high_52w - low_52w)) * 100
                else:
                    percentile = 50.0

                result[symbol] = {
                    "current": round(current, 2),
                    "52w_high": round(high_52w, 2),
                    "52w_low": round(low_52w, 2),
                    "percentile": round(percentile, 1),
                }
                logger.info(
                    f"Historical context {symbol}: {current:.2f} "
                    f"(52W {low_52w:.2f}-{high_52w:.2f}, {percentile:.0f}th pct)"
                )

            except Exception as e:
                logger.debug(f"Could not fetch historical context for {symbol}: {e}")

        return result


class MarketDataFetcher:
    """
    Main interface for fetching market data.

    Automatically selects the best available data provider and caches responses
    for _CACHE_TTL seconds so that multiple tools in the same agent request
    (e.g. get_sentiment_score + get_market_overview) share a single API call.
    """

    _CACHE_TTL = 30  # seconds — covers all tools in a single agent request cycle

    def __init__(self, provider: Optional[MarketDataProvider] = None):
        if provider:
            self.provider = provider
        else:
            # Default to FMP provider (replaces Massive.com which returns 403)
            self.provider = FMPMarketData()
        self._cache: Dict[str, Any] = {}
        self._cache_ts: Dict[str, float] = {}

    def _cached(self, key: str, fn) -> Any:
        """Return cached result if fresh, otherwise call fn(), cache, and return."""
        now = time.monotonic()
        if key in self._cache and (now - self._cache_ts[key]) < self._CACHE_TTL:
            return self._cache[key]
        result = fn()
        self._cache[key] = result
        self._cache_ts[key] = now
        return result

    def get_indices(self) -> Dict[str, Any]:
        return self._cached("indices", self.provider.get_indices)

    def get_sector_performance(self) -> Dict[str, Any]:
        return self._cached("sectors", self.provider.get_sector_performance)

    def get_market_breadth(self) -> Dict[str, Any]:
        return self._cached("breadth", self.provider.get_market_breadth)

    def get_volatility_index(self) -> Dict[str, Any]:
        return self._cached("vix", self.provider.get_volatility_index)

    def get_historical_context(self, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
        key = f"hist_{'_'.join(sorted(symbols or []))}"
        if hasattr(self.provider, "get_historical_context"):
            return self._cached(key, lambda: self.provider.get_historical_context(symbols))
        return {}

    def calculate_market_regime(self) -> Dict[str, Any]:
        """
        Calculate current market regime based on multiple factors.

        All sub-calls go through the TTL cache so concurrent tool calls
        (sentiment + overview) share a single set of API round-trips.

        Returns:
            {
                "regime": "BULL" | "BEAR" | "NEUTRAL",
                "risk_mode": "RISK_ON" | "RISK_OFF",
                "confidence": 0-100,
                "signals": {...}
            }
        """
        indices = self.get_indices()
        breadth = self.get_market_breadth()
        vix = self.get_volatility_index()

        # Trend: majority of indices positive (more robust than single SPX day change)
        # Use .get() to avoid KeyError if SPX is missing from API response (Bug #4)
        index_dicts = {k: v for k, v in indices.items() if isinstance(v, dict)}
        positive_count = sum(1 for v in index_dicts.values() if v.get("change_pct", 0) > 0)
        trend_bullish = positive_count >= max(1, len(index_dicts) // 2)  # majority positive (Bug #3)

        signals = {
            "trend": "BULLISH" if trend_bullish else "BEARISH",
            "breadth": "POSITIVE" if breadth["nyse_advance_decline"]["ratio"] > 1.5 else "NEGATIVE",
            "volatility": vix["VIX"]["level"],
            "high_low_ratio": breadth["new_highs_lows"]["ratio"]
        }

        # Determine regime
        bullish_signals = sum([
            signals["trend"] == "BULLISH",
            signals["breadth"] == "POSITIVE",
            signals["volatility"] == "LOW",
            signals["high_low_ratio"] > 2.0
        ])

        if bullish_signals >= 3:
            regime = "BULL"
            confidence = bullish_signals * 25
        elif bullish_signals <= 1:
            regime = "BEAR"
            confidence = (4 - bullish_signals) * 25
        else:
            regime = "NEUTRAL"
            confidence = 50

        # Determine risk mode (put/call may be unavailable)
        pcr = vix.get("put_call_ratio", {})
        pcr_ratio = pcr.get("ratio")
        vix_value = vix.get("VIX", {}).get("value", 20)
        risk_on = vix_value < 20 and (pcr_ratio is None or pcr_ratio < 0.85)

        return {
            "regime": regime,
            "risk_mode": "RISK_ON" if risk_on else "RISK_OFF",
            "confidence": confidence,
            "signals": signals,
            "summary": self._get_regime_summary(regime, "RISK_ON" if risk_on else "RISK_OFF"),
            "_indices": indices,
            "_breadth": breadth,
            "_vix": vix,
        }

    def _get_regime_summary(self, regime: str, risk_mode: str) -> str:
        """Get human-readable regime summary"""
        summaries = {
            ("BULL", "RISK_ON"): "Strong bullish market with risk appetite. Favor growth stocks, technology, and cyclicals.",
            ("BULL", "RISK_OFF"): "Bullish trend but caution emerging. Consider taking profits and adding defensive positions.",
            ("NEUTRAL", "RISK_ON"): "Choppy market with selective opportunities. Focus on stock picking and sector rotation.",
            ("NEUTRAL", "RISK_OFF"): "Uncertain market with defensive tone. Favor quality, dividends, and lower beta stocks.",
            ("BEAR", "RISK_ON"): "Bearish trend with occasional rallies. Be cautious of bear market rallies.",
            ("BEAR", "RISK_OFF"): "Risk-off bear market. Preserve capital, favor cash, bonds, and defensive sectors."
        }
        return summaries.get((regime, risk_mode), "Market regime unclear.")
