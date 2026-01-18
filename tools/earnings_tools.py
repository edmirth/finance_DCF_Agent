"""
Earnings Analysis Tools for Earnings Research Agent

Tools for fetching quarterly earnings, analyst estimates, earnings surprises,
guidance analysis, and peer comparison.
"""
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Type
import os
import requests
from openai import OpenAI
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# Input Schemas
# ============================================================================

class QuarterlyEarningsInput(BaseModel):
    """Input for quarterly earnings tool"""
    ticker: str = Field(description="Stock ticker symbol (e.g., AAPL, MSFT)")
    quarters: int = Field(default=8, description="Number of quarters to fetch (default: 8 = 2 years)")


class AnalystEstimatesInput(BaseModel):
    """Input for analyst estimates tool"""
    ticker: str = Field(description="Stock ticker symbol")


class EarningsSurprisesInput(BaseModel):
    """Input for earnings surprises tool"""
    ticker: str = Field(description="Stock ticker symbol")
    quarters: int = Field(default=8, description="Number of quarters to analyze")


class GuidanceAnalysisInput(BaseModel):
    """Input for guidance analysis tool"""
    ticker: str = Field(description="Stock ticker symbol")


class PeerComparisonInput(BaseModel):
    """Input for peer earnings comparison"""
    ticker: str = Field(description="Stock ticker symbol")
    peers: Optional[List[str]] = Field(default=None, description="List of peer tickers (optional, will auto-detect if not provided)")


class PriceTargetInput(BaseModel):
    """Input for price target tool"""
    ticker: str = Field(description="Stock ticker symbol")


class AnalystRatingsInput(BaseModel):
    """Input for analyst ratings tool"""
    ticker: str = Field(description="Stock ticker symbol")
    limit: int = Field(default=15, description="Number of recent ratings to fetch (default: 15)")


# ============================================================================
# Tool 1: Get Quarterly Earnings
# ============================================================================

class GetQuarterlyEarningsTool(BaseTool):
    """Fetches quarterly earnings data (revenue, EPS, margins, growth rates)"""

    name: str = "get_quarterly_earnings"
    description: str = """Fetches quarterly financial data for the last N quarters.

    Returns:
    - Quarterly revenue, net income, EPS
    - Gross margin, operating margin trends
    - Cash flow from operations
    - YoY and QoQ growth rates

    Use this to understand earnings trends and trajectory over the past 2 years."""
    args_schema: Type[BaseModel] = QuarterlyEarningsInput

    def _run(self, ticker: str, quarters: int = 8) -> str:
        """Fetch quarterly data from Financial Datasets API"""
        try:
            from data.financial_data import FinancialDataFetcher
            fetcher = FinancialDataFetcher()

            # Call the new quarterly method
            quarterly_data = fetcher.get_quarterly_financials(ticker, limit=quarters)

            if not quarterly_data:
                return f"Error: No quarterly data available for {ticker}"

            # Format the data for analysis
            return self._format_quarterly_earnings(quarterly_data, ticker, quarters)

        except Exception as e:
            logger.error(f"Error in get_quarterly_earnings: {e}")
            return f"Error fetching quarterly earnings for {ticker}: {str(e)}"

    def _format_quarterly_earnings(self, data: Dict, ticker: str, quarters: int) -> str:
        """Format quarterly data into readable analysis"""
        income_statements = data.get("income_statements", [])
        cash_flow_statements = data.get("cash_flow_statements", [])

        if not income_statements:
            return f"No income statement data available for {ticker}"

        # Build earnings table
        output = [f"QUARTERLY EARNINGS DATA: {ticker} (Last {quarters} Quarters)\n"]
        output.append("=" * 80)
        output.append("")

        # Header
        output.append(f"{'Quarter':<12} {'Revenue ($M)':<15} {'YoY%':<10} {'Net Income':<15} {'EPS':<10} {'Op Margin%':<12}")
        output.append("-" * 80)

        # Process each quarter
        for i, stmt in enumerate(income_statements[:quarters]):
            quarter = stmt.get("fiscal_period", "Unknown")
            revenue = stmt.get("revenue", 0) or 0
            net_income = stmt.get("net_income", 0) or 0
            operating_income = stmt.get("operating_income", 0) or 0
            shares = stmt.get("weighted_average_shares", 1) or 1

            # Calculate metrics
            revenue_m = revenue / 1_000_000
            net_income_m = net_income / 1_000_000
            eps = net_income / shares if shares else 0
            op_margin = (operating_income / revenue * 100) if revenue else 0

            # Calculate YoY growth (compare to same quarter last year if available)
            yoy_growth = 0
            if i + 4 < len(income_statements):  # Same quarter last year
                prev_revenue = income_statements[i + 4].get("revenue", 0) or 0
                if prev_revenue:
                    yoy_growth = ((revenue - prev_revenue) / prev_revenue) * 100

            output.append(f"{quarter:<12} ${revenue_m:>13,.1f} {yoy_growth:>8.1f}% ${net_income_m:>13,.1f} ${eps:>8.2f} {op_margin:>10.1f}%")

        # Add cash flow summary
        output.append("")
        output.append("CASH FLOW SUMMARY:")
        output.append("-" * 80)

        for i, cf_stmt in enumerate(cash_flow_statements[:quarters]):
            quarter = cf_stmt.get("fiscal_period", "Unknown")
            operating_cf = cf_stmt.get("operating_cash_flow", 0) or 0
            free_cf = cf_stmt.get("free_cash_flow", 0) or 0

            operating_cf_m = operating_cf / 1_000_000
            free_cf_m = free_cf / 1_000_000

            output.append(f"{quarter:<12} Operating CF: ${operating_cf_m:>10,.1f}M  |  Free CF: ${free_cf_m:>10,.1f}M")

        # Growth trend analysis
        output.append("")
        output.append("KEY INSIGHTS:")
        output.append("-" * 80)

        # Calculate average growth rates
        if len(income_statements) >= 5:
            recent_q = income_statements[0].get("revenue", 0) or 0
            four_q_ago = income_statements[4].get("revenue", 0) or 0

            if four_q_ago:
                yoy_avg = ((recent_q - four_q_ago) / four_q_ago) * 100
                output.append(f"✓ Average YoY Revenue Growth: {yoy_avg:.1f}%")

        # Margin trend
        if len(income_statements) >= 2:
            recent_margin = (income_statements[0].get("operating_income", 0) or 0) / (income_statements[0].get("revenue", 1) or 1) * 100
            older_margin = (income_statements[-1].get("operating_income", 0) or 0) / (income_statements[-1].get("revenue", 1) or 1) * 100
            margin_change = recent_margin - older_margin

            trend = "expanding" if margin_change > 0 else "contracting"
            output.append(f"✓ Operating Margin Trend: {trend} ({margin_change:+.1f} percentage points)")

        return "\n".join(output)


# ============================================================================
# Tool 2: Get Analyst Estimates
# ============================================================================

class GetAnalystEstimatesTool(BaseTool):
    """Fetches analyst consensus estimates from FMP API"""

    name: str = "get_analyst_estimates"
    description: str = """Fetches analyst consensus estimates for forward quarters and years.

    Returns:
    - Forward EPS estimates (current Q, next Q, current FY, next FY)
    - Revenue estimates
    - Number of analysts covering
    - Estimate revisions (upgrades/downgrades)

    Use this to understand market expectations and consensus forecasts."""
    args_schema: Type[BaseModel] = AnalystEstimatesInput

    def _run(self, ticker: str) -> str:
        """Fetch from FMP API or fallback to Perplexity"""
        try:
            fmp_key = os.getenv("FMP_API_KEY")

            if fmp_key:
                return self._fetch_from_fmp(ticker, fmp_key)
            else:
                logger.warning("FMP_API_KEY not found, using Perplexity fallback")
                return self._search_analyst_estimates(ticker)

        except Exception as e:
            logger.error(f"Error in get_analyst_estimates: {e}")
            return f"Error fetching analyst estimates for {ticker}: {str(e)}"

    def _fetch_from_fmp(self, ticker: str, api_key: str) -> str:
        """Fetch from Financial Modeling Prep API (DEPRECATED - FMP v3 API no longer available)"""
        # NOTE: FMP deprecated /api/v3/ endpoints as of Aug 31, 2025
        # Quarterly estimates require premium subscription on new /stable/ API
        # Falling back to Perplexity search
        logger.warning("FMP quarterly estimates require premium subscription, using Perplexity fallback")
        return self._search_analyst_estimates(ticker)

    def _format_analyst_estimates(self, data: List[Dict], ticker: str) -> str:
        """Format FMP analyst estimates data"""
        output = [f"ANALYST CONSENSUS ESTIMATES: {ticker}\n"]
        output.append("=" * 80)
        output.append("")

        # Forward estimates (next 4 quarters)
        output.append("FORWARD QUARTERLY ESTIMATES:")
        output.append("-" * 80)
        output.append(f"{'Period':<15} {'Revenue Est ($M)':<20} {'EPS Est':<15} {'# Analysts':<12}")
        output.append("-" * 80)

        for estimate in data[:4]:
            date = estimate.get("date", "Unknown")
            revenue_est = estimate.get("estimatedRevenueAvg", 0) or 0
            eps_est = estimate.get("estimatedEpsAvg", 0) or 0
            num_analysts = estimate.get("numberAnalystEstimatedRevenue", 0) or 0

            revenue_m = revenue_est / 1_000_000 if revenue_est else 0

            output.append(f"{date:<15} ${revenue_m:>18,.1f} ${eps_est:>13.2f} {num_analysts:>10}")

        # Key metrics
        if data:
            latest = data[0]
            output.append("")
            output.append("CONSENSUS SUMMARY:")
            output.append("-" * 80)
            output.append(f"Next Quarter EPS: ${latest.get('estimatedEpsAvg', 0):.2f}")
            output.append(f"Next Quarter Revenue: ${(latest.get('estimatedRevenueAvg', 0) or 0) / 1_000_000:,.1f}M")
            output.append(f"Analysts Covering: {latest.get('numberAnalystEstimatedRevenue', 0)}")

        return "\n".join(output)

    def _search_analyst_estimates(self, ticker: str) -> str:
        """Fallback: Use Perplexity to search for estimates"""
        try:
            api_key = os.getenv("PERPLEXITY_API_KEY")
            if not api_key:
                return f"Error: No FMP_API_KEY or PERPLEXITY_API_KEY found. Cannot fetch analyst estimates for {ticker}"

            client = OpenAI(api_key=api_key, base_url="https://api.perplexity.ai")

            query = f"""What are the latest analyst consensus estimates for {ticker}?
            Provide:
            1. Current quarter EPS estimate
            2. Next quarter EPS estimate
            3. Current fiscal year EPS estimate
            4. Next fiscal year EPS estimate
            5. Revenue estimates
            6. Number of analysts covering
            7. Recent estimate revisions (upgrades/downgrades)

            Use the most recent data available with sources."""

            response = client.chat.completions.create(
                model="sonar-pro",
                messages=[
                    {"role": "system", "content": "You are a financial data analyst. Provide specific numbers with sources and dates."},
                    {"role": "user", "content": query}
                ]
            )

            return f"ANALYST ESTIMATES: {ticker} (via web search)\n\n" + response.choices[0].message.content

        except Exception as e:
            logger.error(f"Perplexity search error: {e}")
            return f"Error searching for analyst estimates: {str(e)}"


# ============================================================================
# Tool 3: Get Earnings Surprises
# ============================================================================

class GetEarningsSurprisesTool(BaseTool):
    """Fetches earnings surprise history (actual vs estimate)"""

    name: str = "get_earnings_surprises"
    description: str = """Fetches earnings surprise data for past quarters.

    Returns:
    - Actual EPS vs Estimated EPS for past quarters
    - Surprise percentage (beat/miss/meet)
    - Beat/miss/meet pattern over time
    - Revenue surprises where available

    Use this to assess company's ability to meet or exceed expectations."""
    args_schema: Type[BaseModel] = EarningsSurprisesInput

    def _run(self, ticker: str, quarters: int = 8) -> str:
        """Fetch earnings surprises from FMP API"""
        try:
            fmp_key = os.getenv("FMP_API_KEY")

            if fmp_key:
                return self._fetch_from_fmp(ticker, fmp_key, quarters)
            else:
                logger.warning("FMP_API_KEY not found, using Perplexity fallback")
                return self._search_earnings_surprises(ticker, quarters)

        except Exception as e:
            logger.error(f"Error in get_earnings_surprises: {e}")
            return f"Error fetching earnings surprises for {ticker}: {str(e)}"

    def _fetch_from_fmp(self, ticker: str, api_key: str, quarters: int) -> str:
        """Fetch from Financial Modeling Prep API (NEW /stable/ endpoint)"""
        try:
            # NEW: Use earnings-calendar endpoint instead of deprecated earnings-surprises
            url = "https://financialmodelingprep.com/stable/earnings-calendar"
            params = {"apikey": api_key}

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            all_data = response.json()

            # Filter for this ticker
            ticker_data = [item for item in all_data if item.get('symbol') == ticker.upper()]

            if not ticker_data:
                logger.warning(f"Limited earnings calendar data for {ticker}, using Perplexity for historical data")
                return self._search_earnings_surprises(ticker, quarters)

            return self._format_earnings_surprises_from_calendar(ticker_data, ticker)

        except requests.exceptions.RequestException as e:
            logger.error(f"FMP API error: {e}")
            return self._search_earnings_surprises(ticker, quarters)

    def _format_earnings_surprises_from_calendar(self, data: List[Dict], ticker: str) -> str:
        """Format earnings surprises from earnings calendar data"""
        output = [f"EARNINGS SURPRISES HISTORY: {ticker}\n"]
        output.append("=" * 80)
        output.append("")
        output.append("Note: Limited historical data available from FMP. Showing available quarters.")
        output.append("")

        output.append(f"{'Date':<12} {'Actual EPS':<15} {'Est EPS':<15} {'Surprise':<15} {'Surprise %':<12}")
        output.append("-" * 80)

        beats = 0
        misses = 0
        meets = 0

        for item in data:
            date = item.get("date", "Unknown")
            actual = item.get("epsActual") or 0
            estimated = item.get("epsEstimated") or 0

            surprise_amt = actual - estimated
            surprise_pct = (surprise_amt / estimated * 100) if estimated != 0 else 0

            # Classify
            if surprise_pct > 1:
                beats += 1
                result = "BEAT"
            elif surprise_pct < -1:
                misses += 1
                result = "MISS"
            else:
                meets += 1
                result = "MEET"

            output.append(f"{date:<12} ${actual:>13.2f} ${estimated:>13.2f} ${surprise_amt:>13.2f} {surprise_pct:>10.1f}% {result}")

            # Also show revenue surprises if available
            rev_actual = item.get("revenueActual")
            rev_est = item.get("revenueEstimated")
            if rev_actual and rev_est:
                rev_surprise_pct = ((rev_actual - rev_est) / rev_est * 100) if rev_est else 0
                output.append(f"  Revenue:   ${rev_actual/1e9:>10.2f}B  ${rev_est/1e9:>10.2f}B  {rev_surprise_pct:>22.1f}%")

        # Summary stats
        total = beats + misses + meets
        if total > 0:
            output.append("")
            output.append("SURPRISE PATTERN:")
            output.append("-" * 80)
            output.append(f"Beats: {beats}/{total} ({beats/total*100:.1f}%)")
            output.append(f"Meets: {meets}/{total} ({meets/total*100:.1f}%)")
            output.append(f"Misses: {misses}/{total} ({misses/total*100:.1f}%)")

            if beats >= total * 0.75:
                output.append("\n✓ Strong track record: Consistently beats expectations")
            elif misses >= total * 0.5:
                output.append("\n⚠ Weak track record: Frequently misses expectations")

        # Note about limited data
        if total < 4:
            output.append("")
            output.append("⚠ Limited historical data. Recommend using Perplexity search for complete history.")

        return "\n".join(output)

    def _format_earnings_surprises(self, data: List[Dict], ticker: str) -> str:
        """Format earnings surprises data"""
        output = [f"EARNINGS SURPRISES HISTORY: {ticker}\n"]
        output.append("=" * 80)
        output.append("")

        output.append(f"{'Date':<12} {'Actual EPS':<15} {'Est EPS':<15} {'Surprise':<15} {'Surprise %':<12}")
        output.append("-" * 80)

        beats = 0
        misses = 0
        meets = 0

        for surprise in data:
            date = surprise.get("date", "Unknown")
            actual = surprise.get("actualEarningResult", 0) or 0
            estimated = surprise.get("estimatedEarning", 0) or 0

            surprise_amt = actual - estimated
            surprise_pct = (surprise_amt / estimated * 100) if estimated != 0 else 0

            # Classify
            if surprise_pct > 1:
                beats += 1
                result = "BEAT"
            elif surprise_pct < -1:
                misses += 1
                result = "MISS"
            else:
                meets += 1
                result = "MEET"

            output.append(f"{date:<12} ${actual:>13.2f} ${estimated:>13.2f} ${surprise_amt:>13.2f} {surprise_pct:>10.1f}% {result}")

        # Summary stats
        total = beats + misses + meets
        if total > 0:
            output.append("")
            output.append("SURPRISE PATTERN:")
            output.append("-" * 80)
            output.append(f"Beats: {beats}/{total} ({beats/total*100:.1f}%)")
            output.append(f"Meets: {meets}/{total} ({meets/total*100:.1f}%)")
            output.append(f"Misses: {misses}/{total} ({misses/total*100:.1f}%)")

            if beats >= total * 0.75:
                output.append("\n✓ Strong track record: Consistently beats expectations")
            elif misses >= total * 0.5:
                output.append("\n⚠ Weak track record: Frequently misses expectations")

        return "\n".join(output)

    def _search_earnings_surprises(self, ticker: str, quarters: int) -> str:
        """Fallback: Search with Perplexity"""
        try:
            api_key = os.getenv("PERPLEXITY_API_KEY")
            if not api_key:
                return f"Error: No FMP_API_KEY or PERPLEXITY_API_KEY found"

            client = OpenAI(api_key=api_key, base_url="https://api.perplexity.ai")

            query = f"""What are the earnings surprises for {ticker} over the last {quarters} quarters?
            For each quarter, provide:
            1. Earnings date
            2. Actual EPS
            3. Expected/Estimated EPS
            4. Whether it was a beat, miss, or meet

            Also provide the overall pattern (how many beats vs misses)."""

            response = client.chat.completions.create(
                model="sonar-pro",
                messages=[
                    {"role": "system", "content": "You are a financial analyst. Provide specific EPS numbers with dates."},
                    {"role": "user", "content": query}
                ]
            )

            return f"EARNINGS SURPRISES: {ticker} (via web search)\n\n" + response.choices[0].message.content

        except Exception as e:
            logger.error(f"Perplexity search error: {e}")
            return f"Error searching for earnings surprises: {str(e)}"


# ============================================================================
# Tool 4: Analyze Earnings Guidance
# ============================================================================

class AnalyzeEarningsGuidanceTool(BaseTool):
    """Analyzes management guidance from earnings calls"""

    name: str = "analyze_earnings_guidance"
    description: str = """Analyzes management guidance and commentary from recent earnings calls.

    Returns:
    - Latest guidance provided (revenue, EPS, margins)
    - Changes to guidance (raised, lowered, maintained)
    - Key commentary from earnings calls
    - Forward-looking statements and outlook

    Use this to understand management's outlook and confidence level."""
    args_schema: Type[BaseModel] = GuidanceAnalysisInput

    def _run(self, ticker: str) -> str:
        """Search for recent earnings call guidance"""
        try:
            api_key = os.getenv("PERPLEXITY_API_KEY")
            if not api_key:
                return f"Error: PERPLEXITY_API_KEY not found. Cannot analyze guidance for {ticker}"

            client = OpenAI(api_key=api_key, base_url="https://api.perplexity.ai")

            query = f"""Analyze the most recent earnings call and guidance for {ticker}:

            1. Latest quarterly results vs expectations
            2. Management guidance for next quarter and full year (revenue, EPS, margins)
            3. Any changes to previous guidance (raised, lowered, maintained)
            4. Key themes from management commentary
            5. Q&A highlights on outlook, strategy, and risks
            6. Forward-looking statements about growth drivers

            Focus on specific numbers and guidance changes. Use the most recent earnings call."""

            response = client.chat.completions.create(
                model="sonar-pro",
                messages=[
                    {"role": "system", "content": "You are an earnings call analyst. Extract specific guidance numbers and key strategic themes."},
                    {"role": "user", "content": query}
                ]
            )

            output = [f"EARNINGS GUIDANCE ANALYSIS: {ticker}\n"]
            output.append("=" * 80)
            output.append("")
            output.append(response.choices[0].message.content)

            return "\n".join(output)

        except Exception as e:
            logger.error(f"Error analyzing guidance: {e}")
            return f"Error analyzing earnings guidance for {ticker}: {str(e)}"


# ============================================================================
# Tool 5: Compare Peer Earnings
# ============================================================================

class ComparePeerEarningsTool(BaseTool):
    """Compares earnings trends vs industry peers"""

    name: str = "compare_peer_earnings"
    description: str = """Compares company's earnings trends vs industry peers.

    Returns:
    - Revenue growth vs peer average
    - EPS growth vs peer average
    - Margin trends vs peers
    - Market share implications
    - Relative performance assessment

    Use this to assess competitive position and relative performance."""
    args_schema: Type[BaseModel] = PeerComparisonInput

    def _run(self, ticker: str, peers: Optional[List[str]] = None) -> str:
        """Compare earnings with peers"""
        try:
            api_key = os.getenv("PERPLEXITY_API_KEY")
            if not api_key:
                return f"Error: PERPLEXITY_API_KEY not found"

            client = OpenAI(api_key=api_key, base_url="https://api.perplexity.ai")

            # Build query
            if peers:
                peer_list = ", ".join(peers)
                query = f"""Compare {ticker}'s recent earnings performance to its peers {peer_list}:

                For each company, provide:
                1. Latest quarter revenue growth (YoY)
                2. Latest quarter EPS growth (YoY)
                3. Operating margin trends
                4. Key differentiators

                Assess {ticker}'s relative competitive position."""
            else:
                query = f"""Identify {ticker}'s top 3-4 industry competitors and compare their recent earnings:

                1. Who are the main competitors?
                2. Latest quarter revenue growth comparison
                3. Latest quarter EPS growth comparison
                4. Margin trends comparison
                5. Which company is performing best/worst and why?

                Assess {ticker}'s relative competitive position."""

            response = client.chat.completions.create(
                model="sonar-pro",
                messages=[
                    {"role": "system", "content": "You are a competitive analyst. Provide specific metrics and data-driven comparisons."},
                    {"role": "user", "content": query}
                ]
            )

            output = [f"PEER EARNINGS COMPARISON: {ticker}\n"]
            output.append("=" * 80)
            output.append("")
            output.append(response.choices[0].message.content)

            return "\n".join(output)

        except Exception as e:
            logger.error(f"Error in peer comparison: {e}")
            return f"Error comparing peer earnings for {ticker}: {str(e)}"


# ============================================================================
# Tool 6: Get Price Targets (NEW)
# ============================================================================

class GetPriceTargetTool(BaseTool):
    """Fetches analyst price targets from FMP API"""

    name: str = "get_price_targets"
    description: str = """Fetches analyst price target consensus from FMP API.

    Returns:
    - Target High (highest analyst price target)
    - Target Low (lowest analyst price target)
    - Target Consensus (average of all targets)
    - Target Median (median price target)
    - Implied upside/downside from current price

    Use this to understand where analysts see the stock trading in 12 months."""
    args_schema: Type[BaseModel] = PriceTargetInput

    def _run(self, ticker: str) -> str:
        """Fetch price targets from FMP stable API"""
        try:
            fmp_key = os.getenv("FMP_API_KEY")

            if not fmp_key:
                return f"Error: FMP_API_KEY not found. Cannot fetch price targets for {ticker}"

            # Use new stable API endpoint
            url = "https://financialmodelingprep.com/stable/price-target-consensus"
            params = {
                "symbol": ticker,
                "apikey": fmp_key
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if not data or not isinstance(data, list) or len(data) == 0:
                return f"No price target data available for {ticker}"

            return self._format_price_targets(data[0], ticker)

        except requests.exceptions.RequestException as e:
            logger.error(f"FMP API error: {e}")
            return f"Error fetching price targets for {ticker}: {str(e)}"
        except Exception as e:
            logger.error(f"Error in get_price_targets: {e}")
            return f"Error fetching price targets for {ticker}: {str(e)}"

    def _format_price_targets(self, data: Dict, ticker: str) -> str:
        """Format price target data"""
        output = [f"ANALYST PRICE TARGETS: {ticker}\n"]
        output.append("=" * 80)
        output.append("")

        target_high = data.get("targetHigh", 0)
        target_low = data.get("targetLow", 0)
        target_consensus = data.get("targetConsensus", 0)
        target_median = data.get("targetMedian", 0)

        output.append("PRICE TARGET SUMMARY:")
        output.append("-" * 80)
        output.append(f"Target High:       ${target_high:>8.2f}")
        output.append(f"Target Median:     ${target_median:>8.2f}")
        output.append(f"Target Consensus:  ${target_consensus:>8.2f}")
        output.append(f"Target Low:        ${target_low:>8.2f}")
        output.append("")

        # Calculate range
        if target_high and target_low:
            target_range = target_high - target_low
            range_pct = (target_range / target_median * 100) if target_median else 0
            output.append(f"Target Range: ${target_range:.2f} ({range_pct:.1f}% of median)")

        # Note: We'd need current price to calculate implied upside
        # Since we don't have it here, we'll note it
        output.append("")
        output.append("NOTE: Compare these targets to current stock price to assess implied upside/downside.")
        output.append("Example: If stock is at $250 and consensus is $299, that's 19.6% upside.")

        return "\n".join(output)


# ============================================================================
# Tool 7: Get Analyst Ratings (NEW)
# ============================================================================

class GetAnalystRatingsTool(BaseTool):
    """Fetches recent analyst rating changes from FMP API"""

    name: str = "get_analyst_ratings"
    description: str = """Fetches recent analyst rating changes (upgrades/downgrades) from FMP API.

    Returns:
    - Recent rating changes from major firms
    - Upgrades, downgrades, and maintained ratings
    - Date and firm for each rating
    - Previous grade vs new grade
    - Overall sentiment trend

    Use this to understand recent analyst sentiment and rating momentum."""
    args_schema: Type[BaseModel] = AnalystRatingsInput

    def _run(self, ticker: str, limit: int = 15) -> str:
        """Fetch analyst ratings from FMP stable API"""
        try:
            fmp_key = os.getenv("FMP_API_KEY")

            if not fmp_key:
                return f"Error: FMP_API_KEY not found. Cannot fetch analyst ratings for {ticker}"

            # Use new stable API endpoint
            url = "https://financialmodelingprep.com/stable/grades"
            params = {
                "symbol": ticker,
                "limit": limit,
                "apikey": fmp_key
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if not data or not isinstance(data, list) or len(data) == 0:
                return f"No analyst ratings available for {ticker}"

            return self._format_analyst_ratings(data[:limit], ticker)

        except requests.exceptions.RequestException as e:
            logger.error(f"FMP API error: {e}")
            return f"Error fetching analyst ratings for {ticker}: {str(e)}"
        except Exception as e:
            logger.error(f"Error in get_analyst_ratings: {e}")
            return f"Error fetching analyst ratings for {ticker}: {str(e)}"

    def _format_analyst_ratings(self, data: List[Dict], ticker: str) -> str:
        """Format analyst ratings data"""
        output = [f"RECENT ANALYST RATINGS: {ticker}\n"]
        output.append("=" * 80)
        output.append("")

        output.append(f"{'Date':<12} {'Firm':<25} {'Previous':<15} {'New Grade':<15} {'Action':<10}")
        output.append("-" * 80)

        upgrades = 0
        downgrades = 0
        maintains = 0

        for rating in data:
            date = rating.get("date", "N/A")
            firm = rating.get("gradingCompany", "Unknown")[:24]
            previous = rating.get("previousGrade", "N/A") or "New"
            new_grade = rating.get("newGrade", "N/A")
            action = rating.get("action", "N/A")

            # Count actions
            if action and "up" in action.lower():
                upgrades += 1
                action_symbol = "⬆"
            elif action and "down" in action.lower():
                downgrades += 1
                action_symbol = "⬇"
            else:
                maintains += 1
                action_symbol = "→"

            output.append(f"{date:<12} {firm:<25} {previous:<15} {new_grade:<15} {action_symbol} {action}")

        # Summary
        total = upgrades + downgrades + maintains
        if total > 0:
            output.append("")
            output.append("RATING SUMMARY:")
            output.append("-" * 80)
            output.append(f"Upgrades:   {upgrades:>3} ({upgrades/total*100:>5.1f}%)")
            output.append(f"Maintains:  {maintains:>3} ({maintains/total*100:>5.1f}%)")
            output.append(f"Downgrades: {downgrades:>3} ({downgrades/total*100:>5.1f}%)")
            output.append("")

            # Sentiment analysis
            if upgrades > downgrades * 2:
                output.append("✓ BULLISH SENTIMENT: Recent ratings show strong positive momentum")
            elif downgrades > upgrades * 2:
                output.append("⚠ BEARISH SENTIMENT: Recent ratings show negative momentum")
            elif upgrades > downgrades:
                output.append("→ MODERATELY BULLISH: More upgrades than downgrades")
            elif downgrades > upgrades:
                output.append("→ MODERATELY BEARISH: More downgrades than upgrades")
            else:
                output.append("→ NEUTRAL SENTIMENT: Balanced rating activity")

        return "\n".join(output)


# ============================================================================
# Tool Registry Function
# ============================================================================

def get_earnings_tools() -> List[BaseTool]:
    """Return all earnings analysis tools"""
    return [
        GetQuarterlyEarningsTool(),
        GetAnalystEstimatesTool(),
        GetEarningsSurprisesTool(),
        AnalyzeEarningsGuidanceTool(),
        ComparePeerEarningsTool(),
        GetPriceTargetTool(),          # NEW
        GetAnalystRatingsTool()         # NEW
    ]
