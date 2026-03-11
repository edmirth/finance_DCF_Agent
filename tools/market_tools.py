"""
Market Analysis Tools

Tools for analyzing market conditions, sentiment, and regime
"""

import os
from typing import Optional, List, Dict, Any
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
from data.market_data import MarketDataFetcher
from shared.tavily_client import get_tavily_client


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
            fetcher = MarketDataFetcher()

            # Get all market data
            indices = fetcher.get_indices()
            breadth = fetcher.get_market_breadth()
            vix_data = fetcher.get_volatility_index()
            regime = fetcher.calculate_market_regime()

            # Check if any data is placeholder (no real API key)
            is_placeholder = indices.get("_placeholder", False) or vix_data.get("_placeholder", False)

            # Build comprehensive overview
            result = ""
            if is_placeholder:
                result += "**WARNING: FMP_API_KEY not configured. All market data below is STATIC PLACEHOLDER data and does NOT reflect current market conditions. Do not use for investment decisions.**\n\n"
            result += "📊 **MARKET OVERVIEW**\n\n"

            # Indices
            result += "**Major Indices:**\n"
            for symbol, data in indices.items():
                if symbol.startswith("_"):
                    continue
                direction = "🟢" if data["change_pct"] > 0 else "🔴"
                result += f"  {direction} **{data['name']}**: {data['price']:.2f} ({data['change_pct']:+.2f}%)\n"

            # Market regime
            result += f"\n**Market Regime:** "
            if regime["regime"] == "BULL":
                result += "🐂 **BULLISH**"
            elif regime["regime"] == "BEAR":
                result += "🐻 **BEARISH**"
            else:
                result += "😐 **NEUTRAL**"

            result += f" | **Risk Mode:** {regime['risk_mode']}\n"
            result += f"**Confidence:** {regime['confidence']}%\n"
            result += f"\n_{regime['summary']}_\n"

            # Breadth
            nyse_ad = breadth["nyse_advance_decline"]
            breadth_label = " (estimated)" if breadth.get("_estimated") else ""
            result += f"\n**Market Breadth{breadth_label}:**\n"
            result += f"  NYSE: {nyse_ad['advancing']} advancing vs {nyse_ad['declining']} declining (ratio: {nyse_ad['ratio']:.2f})\n"

            highs_lows = breadth["new_highs_lows"]
            result += f"  New 52w Highs/Lows: {highs_lows['new_52w_highs']}/{highs_lows['new_52w_lows']} (ratio: {highs_lows['ratio']:.2f})\n"

            # Volatility
            vix = vix_data["VIX"]
            result += f"\n**Volatility:**\n"
            result += f"  VIX: {vix['value']:.2f} ({vix['level']}) - {vix['change_pct']:+.2f}%\n"

            vvix = vix_data.get("VVIX", {})
            if vvix.get("value") is not None and not vvix.get("_unavailable"):
                result += f"  VVIX: {vvix['value']:.2f} (volatility of VIX)\n"

            pcr = vix_data.get("put_call_ratio", {})
            if pcr.get("_unavailable"):
                result += "  Put/Call Ratio: Not available\n"
            else:
                result += f"  Put/Call Ratio: {pcr['ratio']:.2f} ({pcr['interpretation']})\n"

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
            fetcher = MarketDataFetcher()
            sectors = fetcher.get_sector_performance()

            # Validate timeframe
            valid_timeframes = ["1D", "5D", "1M", "3M", "YTD"]
            if timeframe not in valid_timeframes:
                timeframe = "1M"

            is_placeholder = sectors.get("_placeholder", False)

            result = ""
            if is_placeholder:
                result += "**WARNING: FMP_API_KEY not configured. Sector data below is STATIC PLACEHOLDER data and does NOT reflect current market conditions.**\n\n"
            result += f"📈 **SECTOR ROTATION ANALYSIS** ({timeframe})\n\n"

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

            # Top performers
            result += "**Top Performing Sectors:**\n"
            for i, (symbol, name, perf) in enumerate(sector_list[:3], 1):
                result += f"  {i}. **{name}** ({symbol}): {perf:+.1f}%\n"

            # Bottom performers
            result += "\n**Lagging Sectors:**\n"
            for i, (symbol, name, perf) in enumerate(sector_list[-3:], 1):
                result += f"  {i}. **{name}** ({symbol}): {perf:+.1f}%\n"

            # All sectors
            result += "\n**All Sectors:**\n"
            for symbol, name, perf in sector_list:
                direction = "🟢" if perf > 0 else "🔴" if perf < 0 else "⚪"
                result += f"  {direction} {name:20s} {perf:+6.1f}%\n"

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

            return f"📰 **MARKET NEWS**\n\n{result}"

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
            fetcher = MarketDataFetcher()
            regime = fetcher.calculate_market_regime()

            result = "🎯 **MARKET REGIME CLASSIFICATION**\n\n"

            # Main classification
            if regime["regime"] == "BULL":
                emoji = "🐂"
                color = "🟢"
            elif regime["regime"] == "BEAR":
                emoji = "🐻"
                color = "🔴"
            else:
                emoji = "😐"
                color = "🟡"

            result += f"{emoji} **{regime['regime']} MARKET** {color}\n"
            result += f"**Risk Mode:** {regime['risk_mode']}\n"
            result += f"**Confidence:** {regime['confidence']}%\n\n"

            # Signals
            result += "**Supporting Signals:**\n"
            for signal_name, signal_value in regime['signals'].items():
                result += f"  • {signal_name.replace('_', ' ').title()}: {signal_value}\n"

            # Recommendation
            result += f"\n**Investment Guidance:**\n"
            result += f"  {regime['summary']}\n"

            return result.strip()

        except Exception as e:
            return f"Error classifying market regime: {str(e)}"

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
        description="Filter by industry (e.g., 'Electric Vehicles', 'Semiconductors', 'Pharmaceuticals')"
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
    - Industry (e.g., 'Electric Vehicles', 'Semiconductors', 'Pharmaceuticals')

    Use this when the user asks:
    - "Find stocks with revenue above $X"
    - "Screen for profitable companies with P/E under Y"
    - "Show me stocks with low debt"
    - "Find Electric Vehicle stocks"
    - "Screen for tech companies with revenue over $1B"
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
        limit: int = 20
    ) -> str:
        """Screen stocks with custom criteria"""
        try:
            from data.financial_data import FinancialDataFetcher

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

            # Industry filtering requires at least one financial filter since API doesn't support industry-only queries
            if not filters and industry:
                # Add a very broad filter to get results, then filter by industry
                filters.append({"field": "revenue", "operator": "gte", "value": 0})

            if not filters:
                return "❌ No screening criteria provided. Please specify at least one filter (revenue_min, net_income_min, pe_ratio_max, industry, etc.)"

            # Execute screening with higher limit if filtering by industry (need more results to filter)
            fetcher = FinancialDataFetcher()
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
                error_msg = "❌ No stocks matched your screening criteria.\n\n"
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
            output = f"📊 **STOCK SCREENER RESULTS** ({len(results)} stocks found)\n\n"
            output += "**Screening Criteria:**\n"
            if industry:
                output += f"  • Industry: {industry}\n"
            if revenue_min:
                output += f"  • Revenue ≥ ${revenue_min/1e9:.1f}B\n"
            if revenue_max:
                output += f"  • Revenue ≤ ${revenue_max/1e9:.1f}B\n"
            if net_income_min:
                output += f"  • Net Income ≥ ${net_income_min/1e9:.1f}B\n"
            if pe_ratio_max:
                output += f"  • P/E Ratio ≤ {pe_ratio_max}\n"
            if total_debt_max:
                output += f"  • Total Debt ≤ ${total_debt_max/1e9:.1f}B\n"

            output += "\n**Results:**\n\n"
            output += "| Ticker | Industry | Revenue | Net Income | P/E | Debt |\n"
            output += "|--------|----------|---------|------------|-----|------|\n"

            for stock in results[:limit]:
                ticker = stock.get("ticker", "N/A")
                stock_industry = stock.get("industry", "N/A")
                revenue = stock.get("revenue", 0) or 0
                net_income = stock.get("net_income", 0) or 0
                pe_ratio = stock.get("pe_ratio", 0) or 0
                debt = stock.get("total_debt", 0) or 0

                # Truncate long industry names
                if len(stock_industry) > 25:
                    stock_industry = stock_industry[:22] + "..."

                output += f"| **{ticker}** | {stock_industry} | ${revenue/1e9:.1f}B | ${net_income/1e9:.1f}B | {pe_ratio:.1f} | ${debt/1e9:.1f}B |\n"

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
            from data.financial_data import FinancialDataFetcher

            # Pre-configured value filters
            filters = [
                {"field": "pe_ratio", "operator": "lte", "value": 15},
                {"field": "net_income", "operator": "gt", "value": 0},
                {"field": "revenue", "operator": "gte", "value": 1_000_000_000}
            ]

            fetcher = FinancialDataFetcher()
            # Sort by P/E ratio (ascending) to get best value stocks first
            results = fetcher.screen_stocks(filters, limit=limit, sort_by='pe_ratio')

            if not results:
                return "❌ No value stocks found matching criteria (P/E < 15, profitable, revenue > $1B)"

            output = f"💎 **VALUE STOCKS** ({len(results)} found, sorted by P/E ratio)\n\n"
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

    Use when the user asks:
    - "Find growth stocks"
    - "Show me high-growth companies"
    - "What stocks are growing fast?"
    """
    args_schema: type[BaseModel] = GetGrowthStocksInput

    def _run(self, limit: int = 15) -> str:
        """Find growth stocks"""
        try:
            from data.financial_data import FinancialDataFetcher

            # Pre-configured growth filters
            filters = [
                {"field": "revenue", "operator": "gte", "value": 500_000_000},
                {"field": "net_income", "operator": "gt", "value": 0}
            ]

            fetcher = FinancialDataFetcher()
            # Sort by revenue (descending) to get largest growth companies first
            results = fetcher.screen_stocks(filters, limit=limit, sort_by='revenue')

            if not results:
                return "❌ No growth stocks found matching criteria (revenue > $500M, profitable)"

            output = f"🚀 **GROWTH STOCKS** ({len(results)} found, sorted by revenue)\n\n"
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
            from data.financial_data import FinancialDataFetcher

            # Pre-configured dividend filters
            filters = [
                {"field": "dividends_per_common_share", "operator": "gt", "value": 0},
                {"field": "net_income", "operator": "gt", "value": 0},
                {"field": "revenue", "operator": "gte", "value": 1_000_000_000}
            ]

            fetcher = FinancialDataFetcher()
            # Use diverse sampling for dividend stocks (no specific sort priority)
            results = fetcher.screen_stocks(filters, limit=limit)

            if not results:
                return "❌ No dividend stocks found matching criteria (DPS > 0, profitable, revenue > $1B)"

            output = f"💰 **DIVIDEND STOCKS** ({len(results)} found)\n\n"
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


def get_market_tools() -> List[BaseTool]:
    """Get all market analysis tools including screeners"""
    return [
        GetMarketOverviewTool(),
        GetSectorRotationTool(),
        GetMarketNewsTool(),
        ClassifyMarketRegimeTool(),
        # Stock Screeners
        ScreenStocksTool(),
        GetValueStocksTool(),
        GetGrowthStocksTool(),
        GetDividendStocksTool(),
    ]
