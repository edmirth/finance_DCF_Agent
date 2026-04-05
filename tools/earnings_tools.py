"""
Earnings Analysis Tools for Earnings Research Agent

Tools for fetching quarterly earnings, analyst estimates, earnings surprises,
guidance analysis, and peer comparison.
"""
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Type
import json
import os
import requests
import logging
from dotenv import load_dotenv
from shared.tavily_client import get_tavily_client, EARNINGS_DOMAINS
from shared.retry_utils import retry_with_backoff, RetryConfig

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FMP retry policy: matches CLAUDE.md spec (max 3, base 2s, max 60s)
_FMP_RETRY = RetryConfig(max_attempts=3, base_delay=2.0, max_delay=60.0)

# ---------------------------------------------------------------------------
# EarningsCallInsightsTool: session-level state
# ---------------------------------------------------------------------------

# Tracks which data-source tiers failed (rate-limited / unavailable) this
# process lifetime.  Once a tier is marked failed we skip it entirely so
# the remaining tiers don't wait for a timeout we know will repeat.
# Values: "fmp"
_failed_tiers: set[str] = set()

# In-process result cache keyed by (ticker, quarters).  Avoids redundant
# transcript fetches within the same analysis run (e.g. the earnings agent
# calling the tool twice for the same company).  No TTL — the process
# lifetime is short enough that stale data is not a concern.
_insights_cache: dict[tuple, str] = {}


@retry_with_backoff(_FMP_RETRY)
def _fmp_get(url: str, params: dict, timeout: int = 10) -> requests.Response:
    """Make an FMP API GET request, retrying on 429 and 5xx errors only.

    Raises HTTPError for 429/5xx so the retry decorator kicks in.
    Returns the response for all other status codes (caller handles 4xx).
    """
    response = requests.get(url, params=params, timeout=timeout)
    # Only raise for retryable errors — let callers handle 4xx manually
    if response.status_code == 429 or response.status_code >= 500:
        response.raise_for_status()
    return response


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


class EarningsCallInsightsInput(BaseModel):
    """Input schema for earnings call insights tool"""
    ticker: str = Field(description="Stock ticker symbol (e.g., 'AAPL')")
    query: Optional[str] = Field(
        default=None,
        description="Optional specific query to focus on (e.g., 'iPhone demand', 'AI strategy', 'margins', 'guidance'). If not provided, gives comprehensive summary."
    )
    quarters: int = Field(
        default=1,
        description="Number of recent quarters to analyze (1-8). Default is 1 (most recent)."
    )


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
            result = self._format_quarterly_earnings(quarterly_data, ticker, quarters)

            # Append chart block
            try:
                income_stmts = quarterly_data.get("income_statements", [])
                reversed_stmts = list(reversed(income_stmts))
                chart_data_list = []
                for stmt in reversed_stmts:
                    period = stmt.get("fiscal_period", "")
                    revenue = stmt.get("revenue") or 0
                    net_income = stmt.get("net_income") or 0
                    shares = stmt.get("weighted_average_shares") or 0
                    eps = round(net_income / shares, 2) if shares else 0
                    revenue_b = round(revenue / 1e9, 2)
                    chart_data_list.append({"period": period, "revenue_b": revenue_b, "eps": eps})
                if chart_data_list:
                    chart_id = f"quarterly_earnings_{ticker.upper()}"
                    chart_spec = {
                        "id": chart_id,
                        "chart_type": "bar_line",
                        "title": f"{ticker.upper()} Quarterly Revenue & EPS",
                        "data": chart_data_list,
                        "series": [
                            {"key": "revenue_b", "label": "Revenue ($B)", "type": "bar", "color": "#2563EB", "yAxis": "left"},
                            {"key": "eps", "label": "EPS ($)", "type": "line", "color": "#10B981", "yAxis": "right"}
                        ],
                        "y_format": "currency_b",
                        "y_right_format": "currency"
                    }
                    result += f"\n---CHART_DATA:{chart_id}---\n{json.dumps(chart_spec)}\n---END_CHART_DATA:{chart_id}---"
                    result += f"\n[CHART_INSTRUCTION: Place {{{{CHART:{chart_id}}}}} on its own line where you discuss revenue/EPS trends. Do NOT reproduce the CHART_DATA block.]"
            except Exception:
                pass

            return result

        except Exception as e:
            logger.error(f"Error in get_quarterly_earnings: {e}")
            return f"Error fetching quarterly earnings for {ticker}: {str(e)}"


    async def _arun(self, ticker: str, quarters: int = 8) -> str:
        return self._run(ticker, quarters)
    def _format_quarterly_earnings(self, data: Dict, ticker: str, quarters: int) -> str:
        """Format quarterly data into readable analysis"""
        income_statements = data.get("income_statements", [])
        cash_flow_statements = data.get("cash_flow_statements", [])

        if not income_statements:
            return f"No income statement data available for {ticker}"

        # Build earnings table
        output = [f"## Quarterly Earnings Data: {ticker} (Last {quarters} Quarters)\n"]
        output.append("")

        # Header
        output.append(f"{'Quarter':<12} {'Revenue ($M)':<15} {'YoY%':<10} {'Net Income':<15} {'EPS':<10} {'Op Margin%':<12}")
        output.append("")

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
        output.append("")

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
        output.append("")

        # Calculate average growth rates
        if len(income_statements) >= 5:
            recent_q = income_statements[0].get("revenue", 0) or 0
            four_q_ago = income_statements[4].get("revenue", 0) or 0

            if four_q_ago:
                yoy_avg = ((recent_q - four_q_ago) / four_q_ago) * 100
                output.append(f"Latest Quarter YoY Revenue Growth: {yoy_avg:.1f}%")

        # Margin trend (only when both endpoints have positive revenue)
        if len(income_statements) >= 2:
            recent_rev = income_statements[0].get("revenue", 0) or 0
            older_rev = income_statements[-1].get("revenue", 0) or 0
            if recent_rev > 0 and older_rev > 0:
                recent_margin = (income_statements[0].get("operating_income", 0) or 0) / recent_rev * 100
                older_margin = (income_statements[-1].get("operating_income", 0) or 0) / older_rev * 100
                margin_change = recent_margin - older_margin
                trend = "expanding" if margin_change > 0 else "contracting"
                output.append(f"Operating Margin Trend: {trend} ({margin_change:+.1f} percentage points)")

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
        """Fetch from FMP API or fallback to Tavily search"""
        try:
            fmp_key = os.getenv("FMP_API_KEY")

            if fmp_key:
                return self._fetch_from_fmp(ticker, fmp_key)
            else:
                logger.warning("FMP_API_KEY not found, using web search fallback")
                return self._search_analyst_estimates(ticker)

        except Exception as e:
            logger.error(f"Error in get_analyst_estimates: {e}")
            return f"Error fetching analyst estimates for {ticker}: {str(e)}"


    async def _arun(self, ticker: str) -> str:
        return self._run(ticker)

    def _fetch_from_fmp(self, ticker: str, api_key: str) -> str:
        """Fetch analyst estimates from FMP /stable/analyst-estimates endpoint"""
        try:
            base_url = "https://financialmodelingprep.com/stable/analyst-estimates"

            # Fetch quarterly estimates (forward quarters)
            quarterly_resp = _fmp_get(base_url, params={
                "symbol": ticker, "period": "quarter", "limit": 6, "apikey": api_key
            })
            if quarterly_resp.status_code != 200:
                logger.warning(f"FMP analyst estimates returned {quarterly_resp.status_code} for {ticker}, falling back")
                return self._search_analyst_estimates(ticker)
            quarterly_data = quarterly_resp.json()
            if not isinstance(quarterly_data, list):
                logger.warning(f"Unexpected FMP analyst estimates format for {ticker}, falling back")
                return self._search_analyst_estimates(ticker)

            # Fetch annual estimates (forward years)
            annual_resp = _fmp_get(base_url, params={
                "symbol": ticker, "period": "annual", "limit": 3, "apikey": api_key
            })
            if annual_resp.status_code != 200:
                logger.warning(f"FMP annual estimates returned {annual_resp.status_code} for {ticker}")
                annual_data = []
            else:
                annual_data = annual_resp.json()
                if not isinstance(annual_data, list):
                    annual_data = []

            if not quarterly_data and not annual_data:
                logger.warning(f"No FMP analyst estimates for {ticker}, using web search fallback")
                return self._search_analyst_estimates(ticker)

            return self._format_fmp_estimates(quarterly_data, annual_data, ticker)

        except requests.exceptions.RequestException as e:
            logger.error(f"FMP analyst estimates API error: {e}")
            return self._search_analyst_estimates(ticker)

    def _format_analyst_estimates(self, data: List[Dict], ticker: str) -> str:
        """Format FMP analyst estimates data (legacy format)"""
        output = [f"## Analyst Consensus Estimates: {ticker}\n"]
        output.append("")

        output.append("**Forward Quarterly Estimates:**")
        output.append("")
        output.append(f"{'Period':<15} {'Revenue Est ($M)':<20} {'EPS Est':<15} {'# Analysts':<12}")
        output.append("")

        for estimate in data[:4]:
            date = estimate.get("date", "Unknown")
            revenue_est = estimate.get("estimatedRevenueAvg", 0) or 0
            eps_est = estimate.get("estimatedEpsAvg", 0) or 0
            num_analysts = estimate.get("numberAnalystEstimatedRevenue", 0) or 0

            revenue_m = revenue_est / 1_000_000 if revenue_est else 0

            output.append(f"{date:<15} ${revenue_m:>18,.1f} ${eps_est:>13.2f} {num_analysts:>10}")

        if data:
            latest = data[0]
            output.append("")
            output.append("CONSENSUS SUMMARY:")
            output.append("")
            output.append(f"Next Quarter EPS: ${latest.get('estimatedEpsAvg', 0):.2f}")
            output.append(f"Next Quarter Revenue: ${(latest.get('estimatedRevenueAvg', 0) or 0) / 1_000_000:,.1f}M")
            output.append(f"Analysts Covering: {latest.get('numberAnalystEstimatedRevenue', 0)}")

        return "\n".join(output)

    def _format_fmp_estimates(self, quarterly: List[Dict], annual: List[Dict], ticker: str) -> str:
        """Format FMP /stable/analyst-estimates data (new field names)"""
        output = [f"## Analyst Consensus Estimates: {ticker}\n"]
        output.append("")

        # Quarterly estimates
        if quarterly:
            output.append("**Forward Quarterly Estimates:**")
            output.append("")
            output.append(f"{'Period':<15} {'Revenue Avg ($M)':<20} {'Rev High ($M)':<18} {'EPS Avg':<12} {'EPS High':<12} {'# Analysts':<10}")
            output.append("")

            for est in quarterly[:6]:
                date = est.get("date", "Unknown")
                rev_avg = est.get("revenueAvg", 0) or 0
                rev_high = est.get("revenueHigh", 0) or 0
                eps_avg = est.get("epsAvg", 0) or 0
                eps_high = est.get("epsHigh", 0) or 0
                num_analysts = est.get("numAnalystsRevenue", 0) or est.get("numAnalystsEps", 0) or 0

                output.append(
                    f"{date:<15} ${rev_avg / 1e6:>17,.1f} ${rev_high / 1e6:>15,.1f} ${eps_avg:>10.2f} ${eps_high:>10.2f} {num_analysts:>8}"
                )

        # Annual estimates
        if annual:
            output.append("")
            output.append("FORWARD ANNUAL ESTIMATES:")
            output.append("")
            output.append(f"{'Period':<15} {'Revenue Avg ($M)':<20} {'Rev High ($M)':<18} {'EPS Avg':<12} {'EPS High':<12} {'# Analysts':<10}")
            output.append("")

            for est in annual[:3]:
                date = est.get("date", "Unknown")
                rev_avg = est.get("revenueAvg", 0) or 0
                rev_high = est.get("revenueHigh", 0) or 0
                eps_avg = est.get("epsAvg", 0) or 0
                eps_high = est.get("epsHigh", 0) or 0
                num_analysts = est.get("numAnalystsRevenue", 0) or est.get("numAnalystsEps", 0) or 0

                output.append(
                    f"{date:<15} ${rev_avg / 1e6:>17,.1f} ${rev_high / 1e6:>15,.1f} ${eps_avg:>10.2f} ${eps_high:>10.2f} {num_analysts:>8}"
                )

        # Consensus summary from most recent quarter
        if quarterly:
            latest = quarterly[0]
            output.append("")
            output.append("CONSENSUS SUMMARY (Next Quarter):")
            output.append("")
            output.append(f"EPS Estimate:  ${latest.get('epsAvg', 0):.2f}  (Low: ${latest.get('epsLow', 0):.2f}  High: ${latest.get('epsHigh', 0):.2f})")
            rev_avg = (latest.get('revenueAvg', 0) or 0) / 1e6
            rev_low = (latest.get('revenueLow', 0) or 0) / 1e6
            rev_high = (latest.get('revenueHigh', 0) or 0) / 1e6
            output.append(f"Revenue Est:   ${rev_avg:,.1f}M  (Low: ${rev_low:,.1f}M  High: ${rev_high:,.1f}M)")
            num_rev = latest.get('numAnalystsRevenue', 0) or 0
            num_eps = latest.get('numAnalystsEps', 0) or 0
            output.append(f"Analysts:      {num_rev} (revenue) / {num_eps} (EPS)")

        result = "\n".join(output)

        # Append chart block
        try:
            chart_data_list = []
            for est in reversed(quarterly):
                date = est.get("date", "")
                eps_avg = est.get("epsAvg", 0) or 0
                eps_high = est.get("epsHigh", 0) or 0
                eps_low = est.get("epsLow", 0) or 0
                chart_data_list.append({"period": date, "eps_avg": eps_avg, "eps_high": eps_high, "eps_low": eps_low})
            if chart_data_list:
                chart_id = f"analyst_estimates_{ticker.upper()}"
                chart_spec = {
                    "id": chart_id,
                    "chart_type": "line",
                    "title": f"{ticker.upper()} Forward EPS Estimates",
                    "data": chart_data_list,
                    "series": [
                        {"key": "eps_avg", "label": "Consensus EPS", "type": "line", "color": "#2563EB"},
                        {"key": "eps_high", "label": "High Est.", "type": "line", "color": "#10B981"},
                        {"key": "eps_low", "label": "Low Est.", "type": "line", "color": "#F59E0B"}
                    ],
                    "y_format": "currency"
                }
                result += f"\n---CHART_DATA:{chart_id}---\n{json.dumps(chart_spec)}\n---END_CHART_DATA:{chart_id}---"
                result += f"\n[CHART_INSTRUCTION: Place {{{{CHART:{chart_id}}}}} on its own line where you discuss analyst consensus estimates. Do NOT reproduce the CHART_DATA block.]"
        except Exception:
            pass

        return result

    def _search_analyst_estimates(self, ticker: str) -> str:
        """Fallback: Use Tavily to search for estimates"""
        try:
            tavily = get_tavily_client()

            result = tavily.search_text(
                query=f"{ticker} analyst consensus estimates EPS revenue current quarter next quarter fiscal year",
                topic="finance",
                search_depth="advanced",
                max_results=5,
                include_answer="advanced",
                include_domains=EARNINGS_DOMAINS,
            )

            return f"ANALYST ESTIMATES: {ticker} (via web search)\n\n{result}"

        except Exception as e:
            logger.error(f"Tavily search error: {e}")
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
        """Fetch earnings surprises. Cascade: FMP → Tavily."""
        try:
            # --- Cascade 1: FMP ---
            fmp_key = os.getenv("FMP_API_KEY")
            if fmp_key:
                return self._fetch_from_fmp(ticker, fmp_key, quarters)

            # --- Cascade 2: Tavily web search ---
            logger.warning("No structured data sources available, using web search fallback")
            return self._search_earnings_surprises(ticker, quarters)

        except Exception as e:
            logger.error(f"Error in get_earnings_surprises: {e}")
            return f"Error fetching earnings surprises for {ticker}: {str(e)}"


    async def _arun(self, ticker: str, quarters: int = 8) -> str:
        return self._run(ticker, quarters)

    def _fetch_from_fmp(self, ticker: str, api_key: str, quarters: int) -> str:
        """Fetch historical earnings surprises from FMP /stable/earnings endpoint"""
        try:
            url = "https://financialmodelingprep.com/stable/earnings"
            params = {
                "symbol": ticker,
                "limit": quarters + 2,  # fetch extra to account for future entries
                "apikey": api_key
            }

            response = _fmp_get(url, params=params)
            if response.status_code != 200:
                logger.warning(f"FMP earnings returned {response.status_code} for {ticker}, falling back")
                return self._search_earnings_surprises(ticker, quarters)
            all_data = response.json()

            if not isinstance(all_data, list) or not all_data:
                logger.warning(f"No FMP earnings data for {ticker}, using web search fallback")
                return self._search_earnings_surprises(ticker, quarters)

            # Filter out future quarters (epsActual is null)
            historical = [e for e in all_data if e.get("epsActual") is not None]

            if not historical:
                logger.warning(f"No historical earnings data for {ticker}, using web search fallback")
                return self._search_earnings_surprises(ticker, quarters)

            result = self._format_earnings_surprises_from_calendar(historical[:quarters], ticker)

            # Append chart block
            try:
                chart_data_list = []
                for item in reversed(historical[:quarters]):
                    period = item.get("date", "")
                    eps_actual = item.get("epsActual") or 0
                    eps_estimated = item.get("epsEstimated") or 0
                    # Use same 1% threshold as the text summary for consistency
                    surprise_pct = ((eps_actual - eps_estimated) / abs(eps_estimated) * 100) if eps_estimated else 0
                    beat = surprise_pct > 1
                    chart_data_list.append({"period": period, "eps_actual": eps_actual, "eps_estimate": eps_estimated, "beat": beat})
                if chart_data_list:
                    chart_id = f"earnings_surprises_{ticker.upper()}"
                    chart_spec = {
                        "id": chart_id,
                        "chart_type": "beat_miss_bar",
                        "title": f"{ticker.upper()} EPS: Actual vs. Estimate",
                        "data": chart_data_list,
                        "series": [
                            {"key": "eps_estimate", "label": "Estimate", "type": "bar", "color": "#E5E7EB", "yAxis": "left"},
                            {"key": "eps_actual", "label": "Actual", "type": "bar", "color": "#2563EB", "yAxis": "left",
                             "colorByField": "beat", "colorIfTrue": "#10B981", "colorIfFalse": "#EF4444"}
                        ],
                        "y_format": "currency"
                    }
                    result += f"\n---CHART_DATA:{chart_id}---\n{json.dumps(chart_spec)}\n---END_CHART_DATA:{chart_id}---"
                    result += f"\n[CHART_INSTRUCTION: Place {{{{CHART:{chart_id}}}}} on its own line where you discuss earnings surprises (beats/misses). Do NOT reproduce the CHART_DATA block.]"
            except Exception:
                pass

            return result

        except requests.exceptions.RequestException as e:
            logger.error(f"FMP API error: {e}")
            return self._search_earnings_surprises(ticker, quarters)

    def _format_earnings_surprises_from_calendar(self, data: List[Dict], ticker: str) -> str:
        """Format earnings surprises from earnings calendar data"""
        output = [f"## Earnings Surprises History: {ticker}\n"]
        output.append("")
        output.append("Note: Limited historical data available from FMP. Showing available quarters.")
        output.append("")

        output.append(f"{'Date':<12} {'Actual EPS':<15} {'Est EPS':<15} {'Surprise':<15} {'Surprise %':<12}")
        output.append("")

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
            output.append("**Surprise Pattern:**")
            output.append(f"Beats: {beats}/{total} ({beats/total*100:.1f}%)")
            output.append(f"Meets: {meets}/{total} ({meets/total*100:.1f}%)")
            output.append(f"Misses: {misses}/{total} ({misses/total*100:.1f}%)")

            if beats >= total * 0.75:
                output.append("\nStrong track record: Consistently beats expectations")
            elif misses >= total * 0.5:
                output.append("\nNote: Weak track record — frequently misses expectations")

        # Note about limited data
        if total < 4:
            output.append("")
            output.append("Note: Limited historical data. Recommend using web search for complete history.")

        return "\n".join(output)

    def _format_earnings_surprises(self, data: List[Dict], ticker: str) -> str:
        """Format earnings surprises data"""
        output = [f"## Earnings Surprises: {ticker}\n"]
        output.append("")
        output.append(f"{'Date':<12} {'Actual EPS':<15} {'Est EPS':<15} {'Surprise':<15} {'Surprise %':<12}")
        output.append("")

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
            output.append("**Surprise Pattern:**")
            output.append(f"Beats: {beats}/{total} ({beats/total*100:.1f}%)")
            output.append(f"Meets: {meets}/{total} ({meets/total*100:.1f}%)")
            output.append(f"Misses: {misses}/{total} ({misses/total*100:.1f}%)")

            if beats >= total * 0.75:
                output.append("\nStrong track record: Consistently beats expectations")
            elif misses >= total * 0.5:
                output.append("\nNote: Weak track record — frequently misses expectations")

        return "\n".join(output)

    def _search_earnings_surprises(self, ticker: str, quarters: int) -> str:
        """Fallback: Search with Tavily"""
        try:
            tavily = get_tavily_client()

            result = tavily.search_text(
                query=f"{ticker} earnings surprises last {quarters} quarters actual EPS vs estimated EPS beat miss",
                topic="finance",
                search_depth="advanced",
                max_results=5,
                include_answer="advanced",
                include_domains=EARNINGS_DOMAINS,
            )

            return f"EARNINGS SURPRISES: {ticker} (via web search)\n\n{result}"

        except Exception as e:
            logger.error(f"Tavily search error: {e}")
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
            tavily = get_tavily_client()

            result = tavily.search_text(
                query=f"{ticker} most recent earnings call guidance: quarterly results, management guidance revenue EPS margins, guidance changes raised lowered, forward outlook growth drivers",
                topic="finance",
                search_depth="advanced",
                max_results=5,
                include_answer="advanced",
                include_domains=EARNINGS_DOMAINS,
            )

            output = [f"## Earnings Guidance Analysis: {ticker}\n"]
            output.append("")
            output.append(result)

            return "\n".join(output)

        except Exception as e:
            logger.error(f"Error analyzing guidance: {e}")
            return f"Error analyzing earnings guidance for {ticker}: {str(e)}"

    async def _arun(self, ticker: str) -> str:
        return self._run(ticker)


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
            tavily = get_tavily_client()

            if peers:
                peer_list = ", ".join(peers)
                query = f"{ticker} vs {peer_list} earnings comparison: revenue growth EPS growth operating margin trends competitive position"
            else:
                query = f"{ticker} industry competitors earnings comparison: revenue growth EPS growth margin trends competitive position which company performing best"

            result = tavily.search_text(
                query=query,
                topic="finance",
                search_depth="advanced",
                max_results=5,
                include_answer="advanced",
                include_domains=EARNINGS_DOMAINS,
            )

            output = [f"## Peer Earnings Comparison: {ticker}\n"]
            output.append("")
            output.append(result)

            return "\n".join(output)

        except Exception as e:
            logger.error(f"Error in peer comparison: {e}")
            return f"Error comparing peer earnings for {ticker}: {str(e)}"

    async def _arun(self, ticker: str, peers: Optional[List[str]] = None) -> str:
        return self._run(ticker, peers)


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
        """Fetch price targets from FMP stable API, with Tavily fallback"""
        try:
            fmp_key = os.getenv("FMP_API_KEY")

            if fmp_key:
                try:
                    url = "https://financialmodelingprep.com/stable/price-target-consensus"
                    params = {"symbol": ticker, "apikey": fmp_key}
                    response = _fmp_get(url, params=params)
                    response.raise_for_status()
                    data = response.json()
                    if data and isinstance(data, list) and len(data) > 0:
                        return self._format_price_targets(data[0], ticker)
                except Exception as e:
                    logger.warning(f"FMP price targets failed for {ticker}, falling back to Tavily: {e}")

            # Tavily fallback
            logger.info(f"Using Tavily fallback for {ticker} price targets")
            tavily = get_tavily_client()
            result = tavily.search_text(
                f"{ticker} stock analyst price target consensus 2025 2026",
                include_domains=EARNINGS_DOMAINS,
                max_results=5,
            )
            if result and "No results" not in result:
                return f"## Analyst Price Targets: {ticker} (via web search)\n\n{result}\n\nNote: Data sourced from web search. Verify with primary sources."
            return f"No price target data available for {ticker}"

        except Exception as e:
            logger.error(f"Error in get_price_targets: {e}")
            return f"Error fetching price targets for {ticker}: {str(e)}"


    async def _arun(self, ticker: str) -> str:
        return self._run(ticker)
    def _format_price_targets(self, data: Dict, ticker: str) -> str:
        """Format price target data"""
        output = [f"## Analyst Price Targets: {ticker}\n"]
        output.append("")

        target_high = data.get("targetHigh", 0)
        target_low = data.get("targetLow", 0)
        target_consensus = data.get("targetConsensus", 0)
        target_median = data.get("targetMedian", 0)

        output.append("PRICE TARGET SUMMARY:")
        output.append("")
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
        """Fetch analyst ratings from FMP stable API, with Tavily fallback"""
        try:
            fmp_key = os.getenv("FMP_API_KEY")

            if fmp_key:
                try:
                    url = "https://financialmodelingprep.com/stable/grades"
                    params = {"symbol": ticker, "limit": limit, "apikey": fmp_key}
                    response = _fmp_get(url, params=params)
                    response.raise_for_status()
                    data = response.json()
                    if data and isinstance(data, list) and len(data) > 0:
                        return self._format_analyst_ratings(data[:limit], ticker)
                except Exception as e:
                    logger.warning(f"FMP analyst ratings failed for {ticker}, falling back to Tavily: {e}")

            # Tavily fallback
            logger.info(f"Using Tavily fallback for {ticker} analyst ratings")
            tavily = get_tavily_client()
            result = tavily.search_text(
                f"{ticker} stock analyst ratings upgrades downgrades recent",
                include_domains=EARNINGS_DOMAINS,
                max_results=5,
            )
            if result and "No results" not in result:
                return f"## Recent Analyst Ratings: {ticker} (via web search)\n\n{result}\n\nNote: Data sourced from web search. Verify with primary sources."
            return f"No analyst ratings available for {ticker}"

        except Exception as e:
            logger.error(f"Error in get_analyst_ratings: {e}")
            return f"Error fetching analyst ratings for {ticker}: {str(e)}"


    async def _arun(self, ticker: str, limit: int = 15) -> str:
        return self._run(ticker, limit)
    def _format_analyst_ratings(self, data: List[Dict], ticker: str) -> str:
        """Format analyst ratings data"""
        output = [f"## Recent Analyst Ratings: {ticker}\n"]
        output.append("")

        output.append(f"{'Date':<12} {'Firm':<25} {'Previous':<15} {'New Grade':<15} {'Action':<10}")
        output.append("")

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
                action_symbol = "UP"
            elif action and "down" in action.lower():
                downgrades += 1
                action_symbol = "DOWN"
            else:
                maintains += 1
                action_symbol = "--"

            output.append(f"{date:<12} {firm:<25} {previous:<15} {new_grade:<15} {action_symbol} {action}")

        # Summary
        total = upgrades + downgrades + maintains
        if total > 0:
            output.append("")
            output.append("RATING SUMMARY:")
            output.append("")
            output.append(f"Upgrades:   {upgrades:>3} ({upgrades/total*100:>5.1f}%)")
            output.append(f"Maintains:  {maintains:>3} ({maintains/total*100:>5.1f}%)")
            output.append(f"Downgrades: {downgrades:>3} ({downgrades/total*100:>5.1f}%)")
            output.append("")

            # Sentiment analysis
            if upgrades > downgrades * 2:
                output.append("**Bullish Sentiment:** Recent ratings show strong positive momentum")
            elif downgrades > upgrades * 2:
                output.append("**Bearish Sentiment:** Recent ratings show negative momentum")
            elif upgrades > downgrades:
                output.append("**Moderately Bullish:** More upgrades than downgrades")
            elif downgrades > upgrades:
                output.append("**Moderately Bearish:** More downgrades than upgrades")
            else:
                output.append("**Neutral Sentiment:** Balanced rating activity")

        return "\n".join(output)


# ============================================================================
# Tool 8: Earnings Call Insights (NEW)
# ============================================================================

class EarningsCallInsightsTool(BaseTool):
    """Tool for analyzing earnings call transcripts and extracting key insights"""

    name: str = "get_earnings_call_insights"
    model: str = "claude-sonnet-4-5-20250929"
    description: str = """Analyzes earnings call transcripts to extract management insights, guidance, and sentiment.

    Use this tool when you need:
    - What management said on earnings calls (verbatim quotes)
    - Forward guidance or outlook (specific numbers and commentary)
    - Analyst questions and management responses
    - Management tone or confidence level
    - Specific topics discussed (e.g., "What did they say about AI?")

    This tool provides PRIMARY SOURCE information (management's own words) rather than
    third-party interpretations. Perfect for deep earnings analysis and management credibility assessment.

    Examples:
    - "What did Apple management say on the last earnings call?"
    - "Did Tesla raise guidance for Q4?"
    - "What concerns did analysts raise on NVIDIA's call?"
    - "What was Meta's tone on the recent earnings call?"
    - "What did Microsoft say about AI revenue over the last 2 quarters?"
    """
    args_schema: Type[BaseModel] = EarningsCallInsightsInput

    def _run(self, ticker: str, query: Optional[str] = None, quarters: int = 1) -> str:
        """Fetch and analyze earnings call transcript(s).

        Data source cascade: FMP → Tavily web search.
        Skips tiers that have already failed this session; caches results in-process.
        """
        try:
            # Validate inputs
            ticker = ticker.strip().upper()
            if not ticker or len(ticker) > 10:
                return f"Error: Invalid ticker format '{ticker}'. Please provide a valid ticker symbol."

            if quarters < 1 or quarters > 8:
                return f"Error: quarters must be between 1-8. Received: {quarters}"

            # --- In-process cache check ---
            cache_key = (ticker, quarters)
            if cache_key in _insights_cache:
                logger.info(f"EarningsCallInsightsTool: cache hit for {ticker} ({quarters}q)")
                return _insights_cache[cache_key]

            # Get company info for context
            from data.financial_data import FinancialDataFetcher
            fetcher = FinancialDataFetcher()
            try:
                stock_info = fetcher.get_stock_info(ticker)
                company_name = stock_info.get('company_name', ticker) if stock_info else ticker
            except Exception as e:
                logger.warning(f"Could not fetch stock info for {ticker}: {e}")
                company_name = ticker

            # --- Cascade 1: FMP (unlimited transcripts) — skip if already failed ---
            fmp_api_key = os.getenv("FMP_API_KEY")
            if fmp_api_key and "fmp" not in _failed_tiers:
                try:
                    if quarters == 1:
                        transcript_data = self._fetch_latest_transcript(ticker, fmp_api_key)
                    else:
                        transcript_data = self._fetch_batch_transcripts(ticker, quarters, fmp_api_key)

                    if transcript_data:
                        logger.info(f"Using FMP transcript data for {ticker}")
                        result = self._analyze_transcript_with_claude(
                            ticker=ticker, company_name=company_name,
                            transcript_data=transcript_data, query=query, quarters=quarters,
                        )
                        _insights_cache[cache_key] = result
                        return result
                except Exception as fmp_err:
                    logger.warning(f"FMP tier failed for {ticker}, marking as skipped: {fmp_err}")
                    _failed_tiers.add("fmp")

            # --- Cascade 2: Tavily web search (always available) ---
            logger.info(f"No transcript sources available for {ticker}, using web search fallback")
            result = self._analyze_via_web_search(ticker, company_name, query, quarters)
            _insights_cache[cache_key] = result
            return result

        except Exception as e:
            logger.error(f"Error in earnings insights tool: {e}", exc_info=True)
            return f"Error analyzing earnings call for {ticker}: {str(e)}"


    async def _arun(self, ticker: str, query: Optional[str] = None, quarters: int = 1) -> str:
        return self._run(ticker, query, quarters)
    def _get_fmp_earnings_dates(self, ticker: str, api_key: str, limit: int = 8) -> List[tuple]:
        """Get (year, quarter) tuples for recent earnings from FMP /stable/earnings.

        Derives the calendar quarter from the earnings reporting date.
        Returns list of (year, quarter) tuples, most recent first.
        """
        try:
            url = "https://financialmodelingprep.com/stable/earnings"
            params = {"symbol": ticker, "limit": limit * 2, "apikey": api_key}

            response = _fmp_get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if not data:
                return []

            results = []
            seen = set()
            for entry in data:
                # Skip future quarters (no actual EPS yet)
                if entry.get("epsActual") is None:
                    continue

                # Try fiscalDateEnding first (closer to the actual period the transcript
                # covers), then fall back to the reporting date. FMP's transcript API
                # indexes by fiscal year/quarter, so fiscalDateEnding gives a better
                # calendar-quarter signal for non-standard fiscal years.
                for date_field in ("fiscalDateEnding", "date"):
                    date_str = entry.get(date_field, "")
                    if not date_str:
                        continue
                    try:
                        parts = date_str.split("-")
                        year = int(parts[0])
                        month = int(parts[1])
                        quarter = (month - 1) // 3 + 1
                        pair = (year, quarter)
                        if pair not in seen:
                            seen.add(pair)
                            results.append(pair)
                    except (ValueError, IndexError):
                        continue

            return results[:limit]

        except Exception as e:
            logger.debug(f"Error fetching FMP earnings dates for {ticker}: {e}")
            return []

    def _fetch_latest_transcript(self, ticker: str, api_key: str) -> Optional[Dict]:
        """Fetch the most recent earnings call transcript from FMP.

        Looks up earnings dates first to derive the required year/quarter params,
        then calls /stable/earning-call-transcript with those params.
        """
        try:
            # Step 1: Get recent earnings dates to derive year/quarter
            earnings_dates = self._get_fmp_earnings_dates(ticker, api_key, limit=4)
            if not earnings_dates:
                logger.info(f"No FMP earnings dates found for {ticker}, cannot fetch transcript")
                return None

            # Step 2: Try each recent earnings date until we get a transcript
            url = "https://financialmodelingprep.com/stable/earning-call-transcript"
            for year, quarter in earnings_dates:
                params = {
                    "symbol": ticker,
                    "year": year,
                    "quarter": quarter,
                    "apikey": api_key
                }

                logger.info(f"Fetching transcript for {ticker} Q{quarter} {year} from FMP")
                response = _fmp_get(url, params=params, timeout=30)

                if response.status_code in [401, 402, 403]:
                    logger.info(f"FMP transcript access denied ({response.status_code}) for {ticker}")
                    return None

                if response.status_code == 404:
                    logger.debug(f"No transcript for {ticker} Q{quarter} {year}, trying earlier quarter")
                    continue

                response.raise_for_status()
                data = response.json()

                if isinstance(data, list) and len(data) > 0:
                    transcript = data[0]
                    content_length = len(transcript.get('content', ''))
                    if content_length > 0:
                        logger.info(f"Fetched transcript for {ticker}: Q{quarter} {year} ({content_length:,} chars)")
                        return transcript

            logger.info(f"No transcripts found for {ticker} across recent quarters")
            return None

        except requests.exceptions.HTTPError as e:
            logger.info(f"FMP transcript unavailable for {ticker} (HTTP {e.response.status_code if hasattr(e, 'response') else 'unknown'})")
            return None
        except Exception as e:
            logger.debug(f"Error fetching transcript for {ticker}: {e}")
            return None

    def _fetch_batch_transcripts(self, ticker: str, quarters: int, api_key: str) -> Optional[List[Dict]]:
        """Fetch multiple quarters of earnings transcripts from FMP.

        Looks up earnings dates first to derive year/quarter params for each,
        then fetches each transcript individually.
        """
        try:
            # Step 1: Get earnings dates
            earnings_dates = self._get_fmp_earnings_dates(ticker, api_key, limit=quarters + 2)
            if not earnings_dates:
                logger.info(f"No FMP earnings dates found for {ticker}, cannot fetch transcripts")
                return None

            # Step 2: Fetch transcript for each quarter
            url = "https://financialmodelingprep.com/stable/earning-call-transcript"
            transcripts = []

            for year, quarter in earnings_dates:
                if len(transcripts) >= quarters:
                    break

                params = {
                    "symbol": ticker,
                    "year": year,
                    "quarter": quarter,
                    "apikey": api_key
                }

                logger.info(f"Fetching transcript for {ticker} Q{quarter} {year}")
                response = _fmp_get(url, params=params, timeout=30)

                if response.status_code in [401, 402, 403]:
                    logger.info(f"FMP transcript access denied ({response.status_code}) for {ticker}")
                    return None

                if response.status_code == 404:
                    logger.debug(f"No transcript for {ticker} Q{quarter} {year}, skipping")
                    continue

                response.raise_for_status()
                data = response.json()

                if isinstance(data, list) and len(data) > 0:
                    transcript = data[0]
                    if len(transcript.get('content', '')) > 0:
                        transcripts.append(transcript)

            if transcripts:
                logger.info(f"Fetched {len(transcripts)} transcripts for {ticker}")
                quarters_info = [f"Q{t.get('quarter', '?')} {t.get('year', '?')}" for t in transcripts]
                logger.info(f"  Quarters: {', '.join(quarters_info)}")
                return transcripts
            else:
                logger.info(f"No transcripts found for {ticker} across recent quarters")
                return None

        except requests.exceptions.HTTPError as e:
            logger.info(f"FMP transcript unavailable for {ticker} (HTTP {e.response.status_code if hasattr(e, 'response') else 'unknown'})")
            return None
        except Exception as e:
            logger.debug(f"Error fetching batch transcripts for {ticker}: {e}")
            return None

    def _analyze_via_web_search(
        self,
        ticker: str,
        company_name: str,
        query: Optional[str],
        quarters: int
    ) -> str:
        """Fallback: Use Tavily to search for earnings call information when transcripts unavailable"""
        try:
            tavily = get_tavily_client()

            if query:
                search_query = f"{company_name} ({ticker}) earnings call commentary about {query}: management quotes, guidance, analyst questions, tone"
            else:
                period_text = "most recent earnings call" if quarters == 1 else f"last {quarters} earnings calls"
                search_query = f"{company_name} ({ticker}) {period_text} analysis: revenue EPS results, management commentary quotes, forward guidance, analyst Q&A themes, sentiment outlook"

            result = tavily.search_text(
                query=search_query,
                topic="finance",
                search_depth="advanced",
                max_results=7,
                include_answer="advanced",
                include_domains=EARNINGS_DOMAINS,
            )

            header = f"# Earnings Call Analysis: {company_name} ({ticker})\n"
            header += f"**Period:** {'Latest Quarter' if quarters == 1 else f'Last {quarters} Quarters'}\n"
            header += f"**Source:** Web search via Tavily\n\n"

            return header + result

        except Exception as e:
            logger.error(f"Error in Tavily search fallback: {e}")
            return f"Error: Unable to fetch earnings call information for {ticker}. Transcripts unavailable and web search failed: {str(e)}"

    def _analyze_transcript_with_claude(
        self,
        ticker: str,
        company_name: str,
        transcript_data: any,
        query: Optional[str],
        quarters: int
    ) -> str:
        """Use Claude directly to analyze transcript(s) — better quality than external APIs"""
        try:
            from langchain_anthropic import ChatAnthropic

            # Prepare transcript text
            if quarters == 1:
                transcript_text = transcript_data.get('content', '')
                quarter = transcript_data.get('quarter', 'Unknown')
                year = transcript_data.get('year', 'Unknown')
                date = transcript_data.get('date', 'Unknown')

                if len(transcript_text) > 100000:
                    logger.warning(f"Transcript too long ({len(transcript_text)} chars), truncating to 100K")
                    transcript_text = transcript_text[:100000] + "\n\n[Transcript truncated due to length...]"

                context = f"{company_name} ({ticker}) - {quarter} {year} Earnings Call ({date})"
            else:
                # Per-transcript limit: give a single transcript the same headroom
                # as the single-quarter path; split the budget across multiple ones.
                per_transcript_limit = 100000 if len(transcript_data) == 1 else 25000
                transcript_parts = []
                for t in transcript_data:
                    q = t.get('quarter', 'Unknown')
                    y = t.get('year', 'Unknown')
                    content = t.get('content', '')
                    transcript_parts.append(f"\n\n## {q} {y} Earnings Call\n\n{content[:per_transcript_limit]}")

                transcript_text = "\n".join(transcript_parts)
                context = f"{company_name} ({ticker}) - Last {quarters} Quarters"
                quarter = "Multiple"
                year = ""
                date = ""

            system_prompt = """You are an expert financial analyst specializing in earnings call analysis.

Extract actionable insights from earnings call transcripts for investors conducting due diligence.

ANALYSIS FRAMEWORK:

1. **FINANCIAL HIGHLIGHTS** - Key metrics, beat/miss vs consensus, YoY/QoQ trends
2. **MANAGEMENT COMMENTARY** - Verbatim quotes with attribution (CEO, CFO), strategic insights, tone
3. **FORWARD GUIDANCE** - Specific numbers, changes from previous guidance, confidence level
4. **ANALYST Q&A THEMES** - Topics, concerns raised, management responses
5. **TONE & SENTIMENT** - Confident/Cautious/Defensive/Mixed, red flags or positive signals
6. **MANAGEMENT ACCOUNTABILITY** - Promises made, guidance stated, compare to previous quarter

Use markdown formatting with headers, bullet points, **bold** for key metrics, > blockquotes for quotes.
Be comprehensive but concise - aim for 800-1200 words."""

            if query:
                user_prompt = f"""Analyze the earnings call transcript(s) for {context}.

**SPECIFIC FOCUS:** {query}

Provide analysis focused on "{query}" while covering key financial highlights and guidance.

TRANSCRIPT(S):
{transcript_text}"""
            else:
                user_prompt = f"""Analyze the earnings call transcript(s) for {context}.

Provide a comprehensive analysis following the framework in your instructions.

TRANSCRIPT(S):
{transcript_text}"""

            logger.info(f"Sending transcript to Claude for analysis (length: {len(transcript_text)} chars)")

            llm = ChatAnthropic(
                model=self.model,
                temperature=0.2,
                max_tokens=4000,
            )

            messages = [
                ("system", system_prompt),
                ("human", user_prompt),
            ]

            response = llm.invoke(messages)
            analysis = response.content

            # Add header with metadata
            if quarters == 1:
                header = f"# Earnings Call Analysis: {company_name} ({ticker})\n"
                header += f"**Quarter:** {quarter} {year}\n"
                header += f"**Call Date:** {date}\n\n"
            else:
                header = f"# Earnings Call Analysis: {company_name} ({ticker})\n"
                header += f"**Period:** Last {quarters} Quarters\n\n"

            return header + analysis

        except Exception as e:
            logger.error(f"Error in Claude transcript analysis: {e}", exc_info=True)
            return f"Error analyzing transcript: {str(e)}"


# ============================================================================
# Tool Registry Function
# ============================================================================

def get_earnings_tools() -> List[BaseTool]:
    """Return all earnings analysis tools"""
    return [
        GetQuarterlyEarningsTool(),
        GetAnalystEstimatesTool(),
        GetEarningsSurprisesTool(),
        EarningsCallInsightsTool(),      # NEW: Primary source transcript analysis
        ComparePeerEarningsTool(),
        GetPriceTargetTool(),
        GetAnalystRatingsTool()
    ]
