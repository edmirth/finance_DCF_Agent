"""
Market Analysis Tools

Tools for analyzing market conditions, sentiment, and regime
"""

import os
import logging
import requests
from typing import Optional, List, Dict, Any
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
from data.market_data import MarketDataFetcher
from shared.tavily_client import get_tavily_client
from shared.retry_utils import retry_with_backoff, RetryConfig

logger = logging.getLogger(__name__)

_FMP_RETRY = RetryConfig(max_attempts=3, base_delay=2.0, max_delay=60.0)


@retry_with_backoff(_FMP_RETRY)
def _fmp_get(url: str, params: dict) -> requests.Response:
    """Thin wrapper around requests.get for FMP calls with retry logic."""
    resp = requests.get(url, params=params, timeout=10)
    if resp.status_code not in (200, 400, 401, 403, 404):
        resp.raise_for_status()
    return resp


_fetcher: Optional[MarketDataFetcher] = None
_financial_fetcher = None  # FinancialDataFetcher singleton for screener tools


def _get_fetcher() -> MarketDataFetcher:
    """Return a module-level MarketDataFetcher singleton to avoid re-instantiation per call."""
    global _fetcher
    if _fetcher is None:
        _fetcher = MarketDataFetcher()
    return _fetcher


def _get_financial_fetcher():
    """Return a module-level FinancialDataFetcher singleton for screener tools."""
    global _financial_fetcher
    if _financial_fetcher is None:
        from data.financial_data import FinancialDataFetcher
        _financial_fetcher = FinancialDataFetcher()
    return _financial_fetcher


class MarketOverviewInput(BaseModel):
    """Input for market overview (no parameters needed)"""
    pass


class GetMarketOverviewTool(BaseTool):
    """Tool for getting overall market overview"""

    name: str = "get_market_overview"
    description: str = """Get a comprehensive overview of current market conditions.

    Provides:
    - Major indices performance (S&P 500, Nasdaq, Dow, Russell 2000)
    - Market breadth (advance/decline ratios)
    - Volatility (VIX)
    - Market regime classification (BULL/BEAR/NEUTRAL)

    Use this when the user asks about:
    - "How's the market doing?"
    - "What's the market sentiment?"
    - "Should I be buying or selling?"
    """
    args_schema: type[BaseModel] = MarketOverviewInput

    def _run(self) -> str:
        """Get market overview"""
        try:
            fetcher = _get_fetcher()

            # calculate_market_regime fetches indices/breadth/vix internally;
            # reuse those results to avoid redundant API calls (Bug #3)
            regime = fetcher.calculate_market_regime()
            indices = regime.pop("_indices", fetcher.get_indices())
            breadth = regime.pop("_breadth", fetcher.get_market_breadth())
            vix_data = regime.pop("_vix", fetcher.get_volatility_index())

            # Check if any data is placeholder (no real API key)
            is_placeholder = indices.get("_placeholder", False) or vix_data.get("_placeholder", False)

            # Build comprehensive overview
            result = ""
            if is_placeholder:
                result += "**WARNING: FMP_API_KEY not configured. All market data below is STATIC PLACEHOLDER data and does NOT reflect current market conditions. Do not use for investment decisions.**\n\n"
            result += "## Market Overview\n\n"

            # Indices
            result += "**Major Indices:**\n"
            for symbol, data in indices.items():
                if symbol.startswith("_"):
                    continue
                result += f"  **{data['name']}**: {data['price']:.2f} ({data['change_pct']:+.2f}%)\n"

            # Market regime
            result += f"\n**Market Regime:** "
            if regime["regime"] == "BULL":
                result += "**BULLISH**"
            elif regime["regime"] == "BEAR":
                result += "**BEARISH**"
            else:
                result += "**NEUTRAL**"

            result += "\n"
            result += f"**Confidence:** {regime['confidence']}%\n"
            result += f"\n_{regime['summary']}_\n"
            # Only surface a risk-sentiment note when there's a meaningful divergence —
            # e.g. bullish trend but investors rotating defensive, or a bear market with
            # unusual buying suggesting a potential relief rally.
            r, rm = regime["regime"], regime["risk_mode"]
            if r == "BULL" and rm == "RISK_OFF":
                result += "_Note: Despite the bullish trend, elevated volatility is pushing investors toward defensives. Consider trimming high-beta exposure._\n"
            elif r == "BEAR" and rm == "RISK_ON":
                result += "_Note: Some risk appetite persists within the broader downturn — watch for a bear market rally, but treat it with caution._\n"

            # Breadth
            nyse_ad = breadth["nyse_advance_decline"]
            breadth_label = " (estimated)" if breadth.get("_estimated") else ""
            result += f"\n**Market Breadth{breadth_label}:**\n"
            result += f"  NYSE: {nyse_ad['advancing']} advancing vs {nyse_ad['declining']} declining (ratio: {nyse_ad['ratio']:.2f})\n"

            highs_lows = breadth["new_highs_lows"]
            result += f"  New 52w Highs/Lows: {highs_lows['new_52w_highs']}/{highs_lows['new_52w_lows']} (ratio: {highs_lows['ratio']:.2f})\n"

            # Volatility (with 52W context inline)
            vix = vix_data["VIX"]
            result += f"\n**Volatility:**\n"
            vix_line = f"  VIX: {vix['value']:.2f} ({vix['level']}) - {vix['change_pct']:+.2f}%"
            # Attempt to add 52W percentile context
            try:
                hist = fetcher.get_historical_context(["^VIX"])
                vix_hist = hist.get("^VIX", {})
                if vix_hist:
                    vix_line += (
                        f" | 52W range {vix_hist['52w_low']:.1f}–{vix_hist['52w_high']:.1f}"
                        f" ({vix_hist['percentile']:.0f}th pct)"
                    )
            except Exception as e:
                logger.warning("Could not fetch VIX historical context: %s", e)
            result += vix_line + "\n"

            vvix = vix_data.get("VVIX", {})
            if vvix.get("value") is not None and not vvix.get("_unavailable"):
                result += f"  VVIX: {vvix['value']:.2f} (volatility of VIX)\n"

            pcr = vix_data.get("put_call_ratio", {})
            pcr_ratio = pcr.get("ratio")
            if pcr.get("_unavailable") or pcr_ratio is None:
                result += "  Put/Call Ratio: Not available\n"
            else:
                result += f"  Put/Call Ratio: {pcr_ratio:.2f} ({pcr.get('interpretation', 'N/A')})\n"

            return result.strip()

        except Exception as e:
            return f"Error fetching market overview: {str(e)}"

    async def _arun(self) -> str:
        return self._run()


class SectorAnalysisInput(BaseModel):
    """Input for sector analysis"""
    timeframe: str = Field(
        default="1M",
        description="Timeframe for analysis: '1D', '5D', '1M', '3M', or 'YTD'"
    )


class GetSectorRotationTool(BaseTool):
    """Tool for analyzing sector rotation"""

    name: str = "get_sector_rotation"
    description: str = """Analyze sector rotation and identify hot/cold sectors.

    Shows which sectors are leading and lagging over different timeframes.
    Helps identify sector rotation patterns and investment opportunities.

    Use this when the user asks:
    - "Which sectors are hot?"
    - "What sectors should I invest in?"
    - "Is there sector rotation happening?"
    """
    args_schema: type[BaseModel] = SectorAnalysisInput

    def _run(self, timeframe: str = "1M") -> str:
        """Analyze sector rotation"""
        try:
            fetcher = _get_fetcher()
            sectors = fetcher.get_sector_performance()

            # Validate timeframe
            valid_timeframes = ["1D", "5D", "1M", "3M", "YTD"]
            if timeframe not in valid_timeframes:
                timeframe = "1M"

            is_placeholder = sectors.get("_placeholder", False)

            result = ""
            if is_placeholder:
                result += "**WARNING: FMP_API_KEY not configured. Sector data below is STATIC PLACEHOLDER data and does NOT reflect current market conditions.**\n\n"
            result += f"## Sector Rotation Analysis ({timeframe})\n\n"

            # Sort sectors by performance (skip metadata keys)
            # Filter out sectors with None for the requested timeframe
            sector_list = []
            unavailable = []
            for symbol, data in sectors.items():
                if symbol.startswith("_"):
                    continue
                perf = data.get(timeframe)
                if perf is not None:
                    sector_list.append((symbol, data["name"], perf))
                else:
                    unavailable.append((symbol, data["name"]))

            # If no data for this timeframe, fall back to 1D
            if not sector_list and unavailable:
                result += f"**No real data available for {timeframe} timeframe. Showing 1D data instead.**\n\n"
                timeframe = "1D"
                unavailable = []
                for s, d in sectors.items():
                    if s.startswith("_") or not isinstance(d, dict):
                        continue
                    perf_1d = d.get("1D")
                    if perf_1d is not None:
                        sector_list.append((s, d.get("name", s), perf_1d))
                    else:
                        unavailable.append((s, d.get("name", s)))

            sector_list.sort(key=lambda x: x[2], reverse=True)

            # Top/bottom slice size — avoid overlap when fewer than 6 sectors (Bug #10)
            slice_n = min(3, max(1, len(sector_list) // 2))

            # Top performers
            result += "**Top Performing Sectors:**\n"
            for i, (symbol, name, perf) in enumerate(sector_list[:slice_n], 1):
                result += f"  {i}. **{name}** ({symbol}): {perf:+.1f}%\n"

            # Bottom performers
            result += "\n**Lagging Sectors:**\n"
            for i, (symbol, name, perf) in enumerate(sector_list[-slice_n:] if slice_n else [], 1):
                result += f"  {i}. **{name}** ({symbol}): {perf:+.1f}%\n"

            # All sectors
            result += "\n**All Sectors:**\n"
            for symbol, name, perf in sector_list:
                result += f"  {name:20s} {perf:+6.1f}%\n"

            if unavailable:
                result += f"\n_Note: {len(unavailable)} sectors had no data for {timeframe} (aggregate bars unavailable)._\n"

            # Rotation analysis (skip for placeholder data — conclusions would be meaningless)
            if not is_placeholder:
                result += self._analyze_rotation(sectors, timeframe)

            return result.strip()

        except Exception as e:
            return f"Error analyzing sector rotation: {str(e)}"

    def _analyze_rotation(self, sectors: Dict, timeframe: str) -> str:
        """Analyze rotation patterns"""
        analysis = "\n**Rotation Analysis:**\n"

        def _safe_avg(tickers: List[str]) -> Optional[float]:
            vals = [sectors[s][timeframe] for s in tickers if s in sectors and sectors[s].get(timeframe) is not None]
            return sum(vals) / len(vals) if vals else None

        # Defensive vs Cyclical
        defensive_avg = _safe_avg(["XLP", "XLU", "XLV"])
        cyclical_avg = _safe_avg(["XLY", "XLF", "XLE"])

        if defensive_avg is not None and cyclical_avg is not None:
            if cyclical_avg > defensive_avg + 2:
                analysis += "  - **Risk-On** rotation: Cyclicals outperforming defensives\n"
            elif defensive_avg > cyclical_avg + 2:
                analysis += "  - **Risk-Off** rotation: Defensives outperforming cyclicals\n"
            else:
                analysis += "  - **Balanced** market: No clear defensive/cyclical preference\n"

            # Growth vs Value
            growth_avg = _safe_avg(["XLK", "XLC"])
            value_avg = _safe_avg(["XLF", "XLE"])

            if growth_avg is not None and value_avg is not None:
                if growth_avg > value_avg + 2:
                    analysis += "  - **Growth** leadership: Tech and growth sectors leading\n"
                elif value_avg > growth_avg + 2:
                    analysis += "  - **Value** rotation: Value sectors outperforming\n"
        else:
            analysis += "  _Insufficient data for rotation analysis at this timeframe._\n"

        return analysis

    async def _arun(self, timeframe: str = "1M") -> str:
        return self._run(timeframe)


class MarketNewsInput(BaseModel):
    """Input for market news"""
    query: Optional[str] = Field(
        default=None,
        description="Optional specific topic (e.g., 'Fed', 'inflation', 'earnings')"
    )


class GetMarketNewsTool(BaseTool):
    """Tool for fetching market news"""

    name: str = "get_market_news"
    description: str = """Fetch latest market news and developments.

    Get up-to-date market news, economic developments, and market-moving events.

    Use when the user asks:
    - "What's moving the market?"
    - "Any market news today?"
    - "What happened with the Fed?"
    """
    args_schema: type[BaseModel] = MarketNewsInput

    def _run(self, query: Optional[str] = None) -> str:
        """Fetch market news"""
        try:
            tavily = get_tavily_client()

            if query:
                search_query = f"Latest stock market news about {query}"
            else:
                search_query = "Most important stock market and economic news today: market performance, Fed news, economic data, major market-moving events"

            result = tavily.search_text(
                query=search_query,
                topic="news",
                search_depth="advanced",
                max_results=7,
                include_answer="advanced",
                time_range="day",
            )

            return f"**Market News**\n\n{result}"

        except Exception as e:
            return f"Error getting market news: {str(e)}"

    async def _arun(self, query: Optional[str] = None) -> str:
        return self._run(query)


class MarketRegimeInput(BaseModel):
    """Input for market regime analysis"""
    pass


class ClassifyMarketRegimeTool(BaseTool):
    """Tool for classifying current market regime"""

    name: str = "classify_market_regime"
    description: str = """Classify the current market regime (BULL/BEAR/NEUTRAL) and risk mode.

    Analyzes multiple factors:
    - Price trends
    - Market breadth
    - Volatility levels
    - New highs/lows

    Use when the user asks:
    - "Is this a bull or bear market?"
    - "What's the market regime?"
    - "Should I be risk-on or risk-off?"
    """
    args_schema: type[BaseModel] = MarketRegimeInput

    def _run(self) -> str:
        """Classify market regime"""
        try:
            fetcher = _get_fetcher()
            regime = fetcher.calculate_market_regime()

            result = "## Market Regime Classification\n\n"

            result += f"**{regime['regime']} MARKET**\n"
            result += f"**Confidence:** {regime['confidence']}%\n\n"

            # Signals
            result += "**Supporting Signals:**\n"
            for signal_name, signal_value in regime['signals'].items():
                result += f"  • {signal_name.replace('_', ' ').title()}: {signal_value}\n"

            # Recommendation
            result += f"\n**Investment Guidance:**\n"
            result += f"  {regime['summary']}\n"

            # Only add a risk-sentiment note when there's a divergence worth flagging
            r, rm = regime["regime"], regime["risk_mode"]
            if r == "BULL" and rm == "RISK_OFF":
                result += "\n  _Worth noting: volatility has been creeping up and investors are starting to rotate into defensives despite the bullish trend. Worth monitoring._\n"
            elif r == "BEAR" and rm == "RISK_ON":
                result += "\n  _Worth noting: there's some residual risk appetite here despite the broader downtrend — could be the early signs of a bear market rally. Treat with caution._\n"

            return result.strip()

        except Exception as e:
            return f"Error classifying market regime: {str(e)}"

    async def _arun(self) -> str:
        return self._run()


class MacroContextInput(BaseModel):
    """Input for macro context (no parameters needed)"""
    pass


class GetMacroContextTool(BaseTool):
    """Tool for fetching macro-economic context"""

    name: str = "get_macro_context"
    description: str = """Get macro-economic context: treasury yields, yield curve, Fed funds rate, and inflation data.

    Provides:
    - Treasury yields (2Y, 10Y, 30Y) and yield curve spread (10Y-2Y)
    - Yield curve inversion status (recession signal)
    - Federal funds rate
    - Recent CPI/inflation reading
    - GDP growth

    Use when the user asks about:
    - "What are interest rates doing?"
    - "Is the yield curve inverted?"
    - "What is the Fed funds rate?"
    - "What is inflation at?"
    - "Give me macro context"
    """
    args_schema: type[BaseModel] = MacroContextInput

    def _run(self) -> str:
        """Fetch macro-economic context"""
        fmp_key = os.getenv("FMP_API_KEY")
        result = "## Macro-Economic Context\n\n"

        # --- Treasury Yields ---
        try:
            if fmp_key:
                url = "https://financialmodelingprep.com/stable/treasury-rates"
                resp = _fmp_get(url, params={"apikey": fmp_key})
                data = resp.json() if resp.status_code == 200 else []

                if data and isinstance(data, list):
                    latest = data[0]  # Most recent date
                    y2  = latest.get("year2",  None)
                    y10 = latest.get("year10", None)
                    y30 = latest.get("year30", None)
                    y1  = latest.get("year1",  None)
                    date = latest.get("date", "")

                    result += f"**Treasury Yields** (as of {date}):\n"
                    if y1  is not None: result += f"  1-Year:  {y1:.2f}%\n"
                    if y2  is not None: result += f"  2-Year:  {y2:.2f}%\n"
                    if y10 is not None: result += f"  10-Year: {y10:.2f}%\n"
                    if y30 is not None: result += f"  30-Year: {y30:.2f}%\n"

                    # Yield curve spread
                    if y10 is not None and y2 is not None:
                        spread = y10 - y2
                        if spread < 0:
                            curve_status = f"INVERTED ({spread:+.2f}%) — historically a recession warning signal"
                        elif spread < 0.5:
                            curve_status = f"FLAT ({spread:+.2f}%) — caution territory"
                        else:
                            curve_status = f"NORMAL ({spread:+.2f}%) — healthy slope"
                        result += f"\n**Yield Curve (10Y-2Y):** {curve_status}\n"
                else:
                    result += "**Treasury Yields:** Data unavailable from FMP\n"
            else:
                result += "**Treasury Yields:** FMP_API_KEY not configured\n"
        except Exception as e:
            result += f"**Treasury Yields:** Error fetching data ({str(e)[:60]})\n"

        # --- Economic Indicators (Fed Rate + CPI) ---
        try:
            if fmp_key:
                # FMP economic indicators endpoint
                indicators_to_fetch = [
                    ("federalFunds", "Federal Funds Rate"),
                    ("CPI",          "CPI (Inflation)"),
                    ("GDP",          "GDP Growth"),
                ]
                result += "\n**Economic Indicators:**\n"
                for indicator, label in indicators_to_fetch:
                    try:
                        url = "https://financialmodelingprep.com/stable/economic"
                        resp = _fmp_get(url, params={"name": indicator, "apikey": fmp_key})
                        econ_data = resp.json() if resp.status_code == 200 else []

                        if econ_data and isinstance(econ_data, list):
                            latest_econ = econ_data[0]
                            value = latest_econ.get("value", None)
                            econ_date = latest_econ.get("date", "")
                            if value is not None:
                                if indicator == "CPI":
                                    result += f"  {label}: {value:.1f} (as of {econ_date})\n"
                                elif indicator == "federalFunds":
                                    result += f"  {label}: {value:.2f}% (as of {econ_date})\n"
                                else:
                                    result += f"  {label}: {value:.2f}% (as of {econ_date})\n"
                        else:
                            result += f"  {label}: Data unavailable\n"
                    except Exception:
                        result += f"  {label}: Error fetching\n"
            else:
                result += "\n**Economic Indicators:** FMP_API_KEY not configured\n"
        except Exception as e:
            result += f"\n**Economic Indicators:** Error ({str(e)[:60]})\n"

        return result.strip()

    async def _arun(self) -> str:
        return self._run()


# ============================================================================
# STOCK SCREENER TOOLS
# ============================================================================

class ScreenStocksInput(BaseModel):
    """Input for custom stock screening"""
    revenue_min: Optional[float] = Field(
        default=None,
        description="Minimum revenue (e.g., 1000000000 for $1B)"
    )
    revenue_max: Optional[float] = Field(
        default=None,
        description="Maximum revenue"
    )
    net_income_min: Optional[float] = Field(
        default=None,
        description="Minimum net income (profitability filter)"
    )
    pe_ratio_max: Optional[float] = Field(
        default=None,
        description="Maximum P/E ratio (value filter)"
    )
    total_debt_max: Optional[float] = Field(
        default=None,
        description="Maximum total debt"
    )
    industry: Optional[str] = Field(
        default=None,
        description="Filter by industry using the API's exact classification (e.g., 'Auto Manufacturers', 'Semiconductors', 'Pharmaceuticals')"
    )
    revenue_growth_min: Optional[float] = Field(
        default=None,
        description="Minimum revenue growth rate as decimal (e.g., 0.10 for 10% YoY growth)"
    )
    limit: int = Field(
        default=20,
        description="Maximum number of results (default: 20)"
    )


class ScreenStocksTool(BaseTool):
    """Tool for custom stock screening"""

    name: str = "screen_stocks"
    description: str = """Screen stocks based on custom financial criteria.

    Filter stocks by:
    - Revenue (minimum/maximum)
    - Net income (profitability)
    - P/E ratio (valuation)
    - Total debt (financial health)
    - Industry using exact API classification (e.g., 'Auto Manufacturers' for EVs/Tesla, 'Semiconductors', 'Pharmaceuticals')
    - Revenue growth rate (e.g., revenue_growth_min=0.10 for at least 10% YoY growth)

    Use this when the user asks:
    - "Find stocks with revenue above $X"
    - "Screen for profitable companies with P/E under Y"
    - "Show me stocks with low debt"
    - "Find Electric Vehicle stocks"
    - "Screen for tech companies with revenue over $1B"
    - "Find stocks growing revenue at least 10% per year"
    """
    args_schema: type[BaseModel] = ScreenStocksInput

    def _run(
        self,
        revenue_min: Optional[float] = None,
        revenue_max: Optional[float] = None,
        net_income_min: Optional[float] = None,
        pe_ratio_max: Optional[float] = None,
        total_debt_max: Optional[float] = None,
        industry: Optional[str] = None,
        revenue_growth_min: Optional[float] = None,
        limit: int = 20
    ) -> str:
        """Screen stocks with custom criteria"""
        try:
            # Build filters (only financial metrics - API doesn't support industry filtering)
            filters = []

            if revenue_min is not None:
                filters.append({"field": "revenue", "operator": "gte", "value": revenue_min})
            if revenue_max is not None:
                filters.append({"field": "revenue", "operator": "lte", "value": revenue_max})
            if net_income_min is not None:
                filters.append({"field": "net_income", "operator": "gte", "value": net_income_min})
            if pe_ratio_max is not None:
                filters.append({"field": "pe_ratio", "operator": "lte", "value": pe_ratio_max})
            if total_debt_max is not None:
                filters.append({"field": "total_debt", "operator": "lte", "value": total_debt_max})
            if revenue_growth_min is not None:
                filters.append({"field": "revenue_growth", "operator": "gte", "value": revenue_growth_min})

            # Industry filtering requires at least one financial filter since API doesn't support industry-only queries
            if not filters and industry:
                filters.append({"field": "revenue", "operator": "gte", "value": 0})

            if not filters:
                return "No screening criteria provided. Please specify at least one filter (revenue_min, net_income_min, pe_ratio_max, industry, etc.)"

            # Execute screening with higher limit if filtering by industry (need more results to filter)
            fetcher = _get_financial_fetcher()
            fetch_limit = limit * 5 if industry else limit  # Get 5x results if filtering by industry
            results = fetcher.screen_stocks(filters, limit=fetch_limit)

            # Post-filter by industry if specified (case-insensitive partial matching)
            if industry and results:
                industry_lower = industry.lower()
                filtered_results = [
                    stock for stock in results
                    if stock.get("industry") and industry_lower in stock.get("industry", "").lower()
                ]
                results = filtered_results[:limit]  # Limit to requested count

            if not results:
                error_msg = "No stocks matched your screening criteria.\n\n"
                if industry:
                    # Try to find similar industries from the unfiltered results
                    unfiltered_results = fetcher.screen_stocks(filters, limit=100)
                    found_industries = set()
                    for stock in unfiltered_results:
                        if stock.get("industry"):
                            found_industries.add(stock.get("industry"))

                    error_msg += f"**Note:** No stocks found with '{industry}' in their industry name.\n\n"

                    if found_industries:
                        # Show actual industries found in the results
                        error_msg += "**Industries found in your search results:**\n"
                        for ind in sorted(list(found_industries))[:15]:  # Show top 15
                            error_msg += f"  • {ind}\n"
                        error_msg += "\n**Tip:** Try using one of the industries listed above or use partial matching (e.g., 'auto', 'tech', 'pharma')."
                    else:
                        error_msg += "**Common Industry Names to Try:**\n"
                        error_msg += "  • Auto Manufacturers\n"
                        error_msg += "  • Semiconductors\n"
                        error_msg += "  • Software - Application\n"
                        error_msg += "  • Biotechnology\n"
                        error_msg += "  • Pharmaceuticals\n"
                else:
                    error_msg += "Try adjusting your filters (lower thresholds, remove some criteria)."
                return error_msg

            # Format results
            output = f"## Stock Screener Results ({len(results)} stocks found)\n\n"
            output += "**Screening Criteria:**\n"
            if industry:
                output += f"  • Industry: {industry}\n"
            if revenue_min is not None:
                output += f"  • Revenue >= ${revenue_min/1e9:.1f}B\n"
            if revenue_max is not None:
                output += f"  • Revenue <= ${revenue_max/1e9:.1f}B\n"
            if net_income_min is not None:
                output += f"  • Net Income >= ${net_income_min/1e9:.1f}B\n"
            if pe_ratio_max is not None:
                output += f"  • P/E Ratio <= {pe_ratio_max}\n"
            if total_debt_max is not None:
                output += f"  • Total Debt <= ${total_debt_max/1e9:.1f}B\n"
            if revenue_growth_min is not None:
                output += f"  • Revenue Growth >= {revenue_growth_min*100:.0f}%\n"

            output += "\n**Results:**\n\n"
            output += "| Ticker | Industry | Revenue | Net Income | P/E | Growth |\n"
            output += "|--------|----------|---------|------------|-----|--------|\n"

            for stock in results[:limit]:
                ticker = stock.get("ticker", "N/A")
                stock_industry = stock.get("industry", "N/A")
                revenue = stock.get("revenue", 0) or 0
                net_income = stock.get("net_income", 0) or 0
                pe_ratio = stock.get("pe_ratio", 0) or 0
                revenue_growth = stock.get("revenue_growth", None)
                growth_str = f"{revenue_growth*100:.0f}%" if revenue_growth is not None else "N/A"

                # Truncate long industry names
                if len(stock_industry) > 25:
                    stock_industry = stock_industry[:22] + "..."

                output += f"| **{ticker}** | {stock_industry} | ${revenue/1e9:.1f}B | ${net_income/1e9:.1f}B | {pe_ratio:.1f} | {growth_str} |\n"

            output += f"\n**Next Steps:** Use Finance Q&A or Equity Analyst to deep-dive on promising candidates."

            return output

        except Exception as e:
            return f"Error screening stocks: {str(e)}"

    async def _arun(self, **kwargs) -> str:
        return self._run(**kwargs)


class GetValueStocksInput(BaseModel):
    """Input for value stock screening"""
    limit: int = Field(default=15, description="Maximum results")


class GetValueStocksTool(BaseTool):
    """Tool for finding value stocks"""

    name: str = "get_value_stocks"
    description: str = """Find value stocks (low P/E, profitable, large cap).

    Pre-configured filters:
    - P/E ratio < 15 (undervalued)
    - Net income > 0 (profitable)
    - Revenue > $1B (large cap)

    Use when the user asks:
    - "Find value stocks"
    - "Show me undervalued companies"
    - "What are good value investments?"
    """
    args_schema: type[BaseModel] = GetValueStocksInput

    def _run(self, limit: int = 15) -> str:
        """Find value stocks"""
        try:
            # Pre-configured value filters
            filters = [
                {"field": "pe_ratio", "operator": "lte", "value": 15},
                {"field": "net_income", "operator": "gt", "value": 0},
                {"field": "revenue", "operator": "gte", "value": 1_000_000_000}
            ]

            fetcher = _get_financial_fetcher()
            # Sort by P/E ratio (ascending) to get best value stocks first
            results = fetcher.screen_stocks(filters, limit=limit, sort_by='pe_ratio')

            if not results:
                return "No value stocks found matching criteria (P/E < 15, profitable, revenue > $1B)"

            output = f"## Value Stocks ({len(results)} found, sorted by P/E ratio)\n\n"
            output += "**Criteria:** P/E < 15, Profitable, Revenue > $1B\n\n"
            output += "| Ticker | Industry | Revenue | Net Income | P/E |\n"
            output += "|--------|----------|---------|------------|-----|\n"

            for stock in results:
                ticker = stock.get("ticker", "N/A")
                stock_industry = stock.get("industry", "N/A")
                revenue = stock.get("revenue", 0) or 0
                net_income = stock.get("net_income", 0) or 0
                pe_ratio = stock.get("pe_ratio", 0) or 0

                # Truncate long industry names
                if len(stock_industry) > 25:
                    stock_industry = stock_industry[:22] + "..."

                output += f"| **{ticker}** | {stock_industry} | ${revenue/1e9:.1f}B | ${net_income/1e9:.1f}B | {pe_ratio:.1f} |\n"

            return output

        except Exception as e:
            return f"Error finding value stocks: {str(e)}"

    async def _arun(self, limit: int = 15) -> str:
        return self._run(limit)


class GetGrowthStocksInput(BaseModel):
    """Input for growth stock screening"""
    limit: int = Field(default=15, description="Maximum results")


class GetGrowthStocksTool(BaseTool):
    """Tool for finding growth stocks"""

    name: str = "get_growth_stocks"
    description: str = """Find high-growth stocks (strong revenue, profitable).

    Pre-configured filters:
    - Revenue > $500M (established companies)
    - Net income > 0 (profitable growth)

    For growth rate filtering (e.g., "growing at least 20% per year"), use screen_stocks
    with the revenue_growth_min parameter instead (e.g., revenue_growth_min=0.20).

    Use when the user asks:
    - "Find growth stocks"
    - "Show me high-growth companies"
    - "What stocks are growing fast?"
    """
    args_schema: type[BaseModel] = GetGrowthStocksInput

    def _run(self, limit: int = 15) -> str:
        """Find growth stocks"""
        try:
            # Pre-configured growth filters
            filters = [
                {"field": "revenue", "operator": "gte", "value": 500_000_000},
                {"field": "net_income", "operator": "gt", "value": 0}
            ]

            fetcher = _get_financial_fetcher()
            # Sort by revenue (descending) to get largest growth companies first
            results = fetcher.screen_stocks(filters, limit=limit, sort_by='revenue')

            if not results:
                return "No growth stocks found matching criteria (revenue > $500M, profitable)"

            output = f"## Growth Stocks ({len(results)} found, sorted by revenue)\n\n"
            output += "**Criteria:** Revenue > $500M, Profitable\n\n"
            output += "| Ticker | Industry | Revenue | Net Income | P/E |\n"
            output += "|--------|----------|---------|------------|-----|\n"

            for stock in results:
                ticker = stock.get("ticker", "N/A")
                stock_industry = stock.get("industry", "N/A")
                revenue = stock.get("revenue", 0) or 0
                net_income = stock.get("net_income", 0) or 0
                pe_ratio = stock.get("pe_ratio", 0) or 0

                # Truncate long industry names
                if len(stock_industry) > 25:
                    stock_industry = stock_industry[:22] + "..."

                output += f"| **{ticker}** | {stock_industry} | ${revenue/1e9:.1f}B | ${net_income/1e9:.1f}B | {pe_ratio:.1f} |\n"

            return output

        except Exception as e:
            return f"Error finding growth stocks: {str(e)}"

    async def _arun(self, limit: int = 15) -> str:
        return self._run(limit)


class GetDividendStocksInput(BaseModel):
    """Input for dividend stock screening"""
    limit: int = Field(default=15, description="Maximum results")


class GetDividendStocksTool(BaseTool):
    """Tool for finding dividend stocks"""

    name: str = "get_dividend_stocks"
    description: str = """Find dividend-paying stocks.

    Pre-configured filters:
    - Dividends per share > 0 (pays dividends)
    - Net income > 0 (profitable)
    - Revenue > $1B (established companies)

    Use when the user asks:
    - "Find dividend stocks"
    - "Show me income-generating investments"
    - "What stocks pay good dividends?"
    """
    args_schema: type[BaseModel] = GetDividendStocksInput

    def _run(self, limit: int = 15) -> str:
        """Find dividend stocks"""
        try:
            # Pre-configured dividend filters
            filters = [
                {"field": "dividends_per_common_share", "operator": "gt", "value": 0},
                {"field": "net_income", "operator": "gt", "value": 0},
                {"field": "revenue", "operator": "gte", "value": 1_000_000_000}
            ]

            fetcher = _get_financial_fetcher()
            # Use diverse sampling for dividend stocks (no specific sort priority)
            results = fetcher.screen_stocks(filters, limit=limit)

            if not results:
                return "No dividend stocks found matching criteria (DPS > 0, profitable, revenue > $1B)"

            output = f"## Dividend Stocks ({len(results)} found)\n\n"
            output += "**Criteria:** Pays Dividends, Profitable, Revenue > $1B\n\n"
            output += "| Ticker | Industry | Revenue | Net Income | DPS | P/E |\n"
            output += "|--------|----------|---------|------------|-----|-----|\n"

            for stock in results:
                ticker = stock.get("ticker", "N/A")
                stock_industry = stock.get("industry", "N/A")
                revenue = stock.get("revenue", 0) or 0
                net_income = stock.get("net_income", 0) or 0
                dps = stock.get("dividends_per_common_share", 0) or 0
                pe_ratio = stock.get("pe_ratio", 0) or 0

                # Truncate long industry names
                if len(stock_industry) > 25:
                    stock_industry = stock_industry[:22] + "..."

                output += f"| **{ticker}** | {stock_industry} | ${revenue/1e9:.1f}B | ${net_income/1e9:.1f}B | ${dps:.2f} | {pe_ratio:.1f} |\n"

            return output

        except Exception as e:
            return f"Error finding dividend stocks: {str(e)}"

    async def _arun(self, limit: int = 15) -> str:
        return self._run(limit)


class SentimentScoreInput(BaseModel):
    """Input for sentiment score (no parameters needed)"""
    pass


class GetSentimentScoreTool(BaseTool):
    """Tool for computing a composite market sentiment / fear-greed score"""

    name: str = "get_sentiment_score"
    description: str = """Compute a composite market sentiment score (0-100) with a Fear & Greed label.

    Aggregates 5 real market signals into a single score:
    - VIX level (25% weight)
    - VIX trend/direction (15% weight)
    - Market momentum — multi-index performance (25% weight)
    - Market breadth — advance/decline ratio (25% weight)
    - New 52-week highs vs lows ratio (10% weight)

    Score labels:
    - 0-20:  Extreme Fear
    - 21-40: Fear
    - 41-60: Neutral
    - 61-80: Greed
    - 81-100: Extreme Greed

    Use when the user asks:
    - "What is market sentiment?"
    - "Show me the fear and greed index"
    - "How fearful or greedy is the market right now?"
    - "Give me a sentiment score"
    - During a full daily briefing
    """
    args_schema: type[BaseModel] = SentimentScoreInput

    # ------------------------------------------------------------------ #
    # Signal scorers (each returns 0-100)                                  #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _score_vix_level(vix_value: float) -> tuple:
        """Score VIX level: low VIX = greed, high VIX = fear"""
        if vix_value < 12:
            return 95, f"VIX {vix_value:.1f} — exceptionally low, market pricing in near-zero risk"
        elif vix_value < 15:
            return 80, f"VIX {vix_value:.1f} — low, well below long-run average of ~20"
        elif vix_value < 18:
            return 65, f"VIX {vix_value:.1f} — slightly below average, calm conditions"
        elif vix_value < 22:
            return 50, f"VIX {vix_value:.1f} — near long-run average, moderate uncertainty"
        elif vix_value < 27:
            return 30, f"VIX {vix_value:.1f} — elevated, meaningful market anxiety"
        elif vix_value < 35:
            return 15, f"VIX {vix_value:.1f} — high, significant fear in the market"
        else:
            return 5, f"VIX {vix_value:.1f} — extreme, panic-level volatility"

    @staticmethod
    def _score_vix_trend(vix_change_pct: float) -> tuple:
        """Score VIX direction: falling = greed, rising = fear"""
        if vix_change_pct < -10:
            return 90, f"VIX fell {vix_change_pct:+.1f}% — sharp volatility collapse, risk appetite surging"
        elif vix_change_pct < -4:
            return 75, f"VIX fell {vix_change_pct:+.1f}% — volatility retreating, fear easing"
        elif vix_change_pct < 0:
            return 60, f"VIX fell {vix_change_pct:+.1f}% — mildly calmer"
        elif vix_change_pct < 4:
            return 45, f"VIX rose {vix_change_pct:+.1f}% — slight anxiety creeping in"
        elif vix_change_pct < 10:
            return 30, f"VIX rose {vix_change_pct:+.1f}% — fear building"
        else:
            return 10, f"VIX surged {vix_change_pct:+.1f}% — fear spiking sharply"

    @staticmethod
    def _score_momentum(index_dicts: dict) -> tuple:
        """Score market momentum from multi-index performance"""
        if not index_dicts:
            return 50, "No index data available"

        changes = [v.get("change_pct", 0) for v in index_dicts.values() if isinstance(v, dict)]
        if not changes:
            return 50, "No change data available"

        avg_change = sum(changes) / len(changes)
        positive = sum(1 for c in changes if c > 0)
        total = len(changes)

        if avg_change > 1.5 and positive == total:
            return 88, f"All {total} indices up, avg {avg_change:+.2f}% — strong broad rally"
        elif avg_change > 0.5 and positive >= total * 0.75:
            return 72, f"{positive}/{total} indices up, avg {avg_change:+.2f}% — solid market advance"
        elif avg_change > 0:
            return 58, f"{positive}/{total} indices up, avg {avg_change:+.2f}% — modest gains"
        elif avg_change > -0.5:
            return 44, f"{positive}/{total} indices up, avg {avg_change:+.2f}% — mild weakness"
        elif avg_change > -1.5:
            return 28, f"{positive}/{total} indices up, avg {avg_change:+.2f}% — broad selling pressure"
        else:
            return 12, f"{positive}/{total} indices up, avg {avg_change:+.2f}% — sharp market-wide decline"

    @staticmethod
    def _score_breadth(ad_ratio: float) -> tuple:
        """Score advance/decline ratio"""
        if ad_ratio > 3.0:
            return 90, f"A/D ratio {ad_ratio:.2f} — overwhelming breadth, near-universal participation"
        elif ad_ratio > 2.0:
            return 75, f"A/D ratio {ad_ratio:.2f} — strong broad participation"
        elif ad_ratio > 1.4:
            return 60, f"A/D ratio {ad_ratio:.2f} — more advancing than declining"
        elif ad_ratio > 0.8:
            return 45, f"A/D ratio {ad_ratio:.2f} — roughly balanced, mixed internals"
        elif ad_ratio > 0.5:
            return 28, f"A/D ratio {ad_ratio:.2f} — declining stocks dominating"
        else:
            return 12, f"A/D ratio {ad_ratio:.2f} — overwhelming selling, very weak internals"

    @staticmethod
    def _score_highs_lows(hl_ratio: float, new_highs: int, new_lows: int) -> tuple:
        """Score new 52-week highs vs lows"""
        if hl_ratio > 5.0:
            return 88, f"{new_highs} new 52W highs vs {new_lows} lows (ratio {hl_ratio:.1f}x) — breakouts dominating"
        elif hl_ratio > 2.5:
            return 72, f"{new_highs} new 52W highs vs {new_lows} lows (ratio {hl_ratio:.1f}x) — more highs than lows"
        elif hl_ratio > 1.0:
            return 55, f"{new_highs} new 52W highs vs {new_lows} lows (ratio {hl_ratio:.1f}x) — slightly more highs"
        elif hl_ratio > 0.4:
            return 35, f"{new_highs} new 52W highs vs {new_lows} lows (ratio {hl_ratio:.1f}x) — more new lows"
        else:
            return 15, f"{new_highs} new 52W highs vs {new_lows} lows (ratio {hl_ratio:.1f}x) — new lows dominating"

    @staticmethod
    def _label(score: float) -> str:
        if score <= 20:  return "Extreme Fear"
        if score <= 40:  return "Fear"
        if score <= 60:  return "Neutral"
        if score <= 80:  return "Greed"
        return "Extreme Greed"

    @staticmethod
    def _score_to_prose(score: float) -> str:
        """Plain-text score indicator — no ASCII art."""
        return f"Score: {score:.0f}/100"

    # ------------------------------------------------------------------ #
    # Main run                                                             #
    # ------------------------------------------------------------------ #

    def _run(self) -> str:
        try:
            fetcher = _get_fetcher()
            indices  = fetcher.get_indices()
            breadth  = fetcher.get_market_breadth()
            vix_data = fetcher.get_volatility_index()

            # Extract raw values
            vix_value      = vix_data.get("VIX", {}).get("value", 20)
            vix_change_pct = vix_data.get("VIX", {}).get("change_pct", 0)
            ad_ratio       = breadth.get("nyse_advance_decline", {}).get("ratio", 1.0)
            hl             = breadth.get("new_highs_lows", {})
            new_highs      = hl.get("new_52w_highs", 100)
            new_lows       = hl.get("new_52w_lows", 50)
            hl_ratio       = hl.get("ratio", 1.0)
            index_dicts    = {k: v for k, v in indices.items() if isinstance(v, dict)}

            # Score each signal
            vix_score,       vix_note       = self._score_vix_level(vix_value)
            trend_score,     trend_note     = self._score_vix_trend(vix_change_pct)
            momentum_score,  momentum_note  = self._score_momentum(index_dicts)
            breadth_score,   breadth_note   = self._score_breadth(ad_ratio)
            hl_score,        hl_note        = self._score_highs_lows(hl_ratio, new_highs, new_lows)

            # Weighted composite
            weights = {
                "vix_level":  0.25,
                "vix_trend":  0.15,
                "momentum":   0.25,
                "breadth":    0.25,
                "highs_lows": 0.10,
            }
            composite = (
                vix_score       * weights["vix_level"]  +
                trend_score     * weights["vix_trend"]   +
                momentum_score  * weights["momentum"]    +
                breadth_score   * weights["breadth"]     +
                hl_score        * weights["highs_lows"]
            )
            composite = round(composite, 1)
            label = self._label(composite)
            score_display = self._score_to_prose(composite)

            # Historical context blurb
            if composite >= 80:
                context = "Historically, scores above 80 have preceded near-term pullbacks as markets become overextended. Elevated risk of mean reversion."
            elif composite >= 65:
                context = "Markets are leaning greedy but not at extremes. Momentum favors bulls, though selective caution is warranted."
            elif composite >= 45:
                context = "Sentiment is balanced. No strong directional signal — stock picking and sector rotation tend to matter more here."
            elif composite >= 25:
                context = "Fear is elevated. Historically, periods of fear have offered better forward returns for patient investors, though downside risk remains."
            else:
                context = "Extreme fear readings have historically marked major buying opportunities, but catching falling knives requires high conviction. Capital preservation first."

            # Format output
            out  = "## Market Sentiment Score\n\n"
            if indices.get("_placeholder") or vix_data.get("_placeholder"):
                out += "**WARNING: FMP_API_KEY not configured. Sentiment score is calculated from STATIC PLACEHOLDER data and does NOT reflect current market conditions.**\n\n"
            out += f"**{score_display} — {label}**\n\n"
            out += "| Signal | Weight | Score | Reading |\n"
            out += "|--------|--------|-------|---------|\n"
            out += f"| VIX Level      | 25% | {vix_score:.0f}/100   | {vix_note} |\n"
            out += f"| VIX Trend      | 15% | {trend_score:.0f}/100   | {trend_note} |\n"
            out += f"| Mkt Momentum   | 25% | {momentum_score:.0f}/100   | {momentum_note} |\n"
            out += f"| Mkt Breadth    | 25% | {breadth_score:.0f}/100   | {breadth_note} |\n"
            out += f"| 52W Hi/Lo      | 10% | {hl_score:.0f}/100   | {hl_note} |\n"
            out += f"\n**Composite: {composite}/100 — {label}**\n\n"
            out += f"_{context}_\n\n"

            # Breadth data caveat
            if breadth.get("_estimated"):
                out += "_Note: Breadth and new highs/lows are estimated from index performance, not live advance/decline data._\n"

            return out.strip()

        except Exception as e:
            return f"Error computing sentiment score: {str(e)}"

    async def _arun(self) -> str:
        return self._run()


class HistoricalContextInput(BaseModel):
    """Input for historical context tool (no parameters needed)"""
    pass


class GetHistoricalContextTool(BaseTool):
    """Tool for fetching 52-week historical context for key market metrics"""

    name: str = "get_historical_context"
    description: str = """Get 52-week historical context for key market metrics: VIX, S&P 500, Nasdaq.

    For each metric shows:
    - Current value
    - 52-week high and low
    - Percentile rank (0% = at 52W low, 100% = at 52W high)

    Use when the user asks:
    - "Is the market cheap or expensive relative to recent history?"
    - "Where does the VIX sit historically?"
    - "How does today's S&P 500 level compare to this year's range?"
    - "Is volatility elevated or suppressed vs normal?"
    - During a full daily briefing to add historical perspective
    """
    args_schema: type[BaseModel] = HistoricalContextInput

    def _run(self) -> str:
        """Fetch 52-week historical context for VIX, S&P 500, Nasdaq"""
        try:
            fetcher = _get_fetcher()
            symbols = ["^VIX", "^GSPC", "^IXIC"]
            context = fetcher.get_historical_context(symbols)

            if not context or context.get("_placeholder"):
                return "Historical context unavailable (FMP_API_KEY not configured)."

            LABELS = {
                "^VIX":  "VIX (Volatility Index)",
                "^GSPC": "S&P 500",
                "^IXIC": "Nasdaq Composite",
            }

            result = "## 52-Week Historical Context\n\n"
            result += "| Metric | Current | 52W Low | 52W High | Percentile |\n"
            result += "|--------|---------|---------|----------|------------|\n"

            for symbol in symbols:
                data = context.get(symbol)
                if not data:
                    continue
                label = LABELS.get(symbol, symbol)
                pct = data["percentile"]
                # Verbal description of percentile
                if pct >= 80:
                    pct_label = f"{pct:.0f}th — near 52W high"
                elif pct >= 60:
                    pct_label = f"{pct:.0f}th — upper half"
                elif pct >= 40:
                    pct_label = f"{pct:.0f}th — mid-range"
                elif pct >= 20:
                    pct_label = f"{pct:.0f}th — lower half"
                else:
                    pct_label = f"{pct:.0f}th — near 52W low"

                result += (
                    f"| **{label}** | {data['current']:,.2f} | "
                    f"{data['52w_low']:,.2f} | {data['52w_high']:,.2f} | {pct_label} |\n"
                )

            result += "\n"

            # Add interpretive commentary for each metric
            vix_data = context.get("^VIX")
            sp_data  = context.get("^GSPC")
            ixic_data = context.get("^IXIC")

            if vix_data:
                vix_pct = vix_data["percentile"]
                if vix_pct >= 70:
                    result += f"**VIX** at the {vix_pct:.0f}th percentile of its 52W range — volatility is elevated relative to recent history, indicating above-average market anxiety.\n\n"
                elif vix_pct <= 30:
                    result += f"**VIX** at the {vix_pct:.0f}th percentile of its 52W range — volatility is suppressed, market pricing in minimal near-term risk (complacency risk).\n\n"
                else:
                    result += f"**VIX** at the {vix_pct:.0f}th percentile of its 52W range — volatility is in its mid-range, neither complacent nor panicked.\n\n"

            if sp_data:
                sp_pct = sp_data["percentile"]
                if sp_pct >= 75:
                    result += f"**S&P 500** at the {sp_pct:.0f}th percentile — trading near 52-week highs, reflecting strong recent momentum. Valuation risk increases at elevated levels.\n\n"
                elif sp_pct <= 25:
                    result += f"**S&P 500** at the {sp_pct:.0f}th percentile — trading near 52-week lows, potential mean-reversion opportunity but trend risk remains.\n\n"
                else:
                    result += f"**S&P 500** at the {sp_pct:.0f}th percentile — trading in the middle of its 52-week range, no extreme reading in either direction.\n\n"

            return result.strip()

        except Exception as e:
            return f"Error fetching historical context: {str(e)}"

    async def _arun(self) -> str:
        return self._run()


def get_market_tools() -> List[BaseTool]:
    """Get all market analysis tools including screeners"""
    return [
        GetMarketOverviewTool(),
        GetSectorRotationTool(),
        GetMarketNewsTool(),
        ClassifyMarketRegimeTool(),
        GetMacroContextTool(),
        GetSentimentScoreTool(),
        GetHistoricalContextTool(),
        # Stock Screeners
        ScreenStocksTool(),
        GetValueStocksTool(),
        GetGrowthStocksTool(),
        GetDividendStocksTool(),
    ]
