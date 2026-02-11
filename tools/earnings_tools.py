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
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

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
        """Fetch analyst estimates from FMP /stable/analyst-estimates endpoint"""
        try:
            base_url = "https://financialmodelingprep.com/stable/analyst-estimates"

            # Fetch quarterly estimates (forward quarters)
            quarterly_resp = requests.get(base_url, params={
                "symbol": ticker, "period": "quarter", "limit": 6, "apikey": api_key
            }, timeout=10)
            quarterly_resp.raise_for_status()
            quarterly_data = quarterly_resp.json()

            # Fetch annual estimates (forward years)
            annual_resp = requests.get(base_url, params={
                "symbol": ticker, "period": "annual", "limit": 3, "apikey": api_key
            }, timeout=10)
            annual_resp.raise_for_status()
            annual_data = annual_resp.json()

            if not quarterly_data and not annual_data:
                logger.warning(f"No FMP analyst estimates for {ticker}, using Perplexity fallback")
                return self._search_analyst_estimates(ticker)

            return self._format_fmp_estimates(quarterly_data, annual_data, ticker)

        except requests.exceptions.RequestException as e:
            logger.error(f"FMP analyst estimates API error: {e}")
            return self._search_analyst_estimates(ticker)

    def _format_analyst_estimates(self, data: List[Dict], ticker: str) -> str:
        """Format FMP analyst estimates data (legacy format)"""
        output = [f"ANALYST CONSENSUS ESTIMATES: {ticker}\n"]
        output.append("=" * 80)
        output.append("")

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

        if data:
            latest = data[0]
            output.append("")
            output.append("CONSENSUS SUMMARY:")
            output.append("-" * 80)
            output.append(f"Next Quarter EPS: ${latest.get('estimatedEpsAvg', 0):.2f}")
            output.append(f"Next Quarter Revenue: ${(latest.get('estimatedRevenueAvg', 0) or 0) / 1_000_000:,.1f}M")
            output.append(f"Analysts Covering: {latest.get('numberAnalystEstimatedRevenue', 0)}")

        return "\n".join(output)

    def _format_fmp_estimates(self, quarterly: List[Dict], annual: List[Dict], ticker: str) -> str:
        """Format FMP /stable/analyst-estimates data (new field names)"""
        output = [f"ANALYST CONSENSUS ESTIMATES: {ticker}\n"]
        output.append("=" * 80)
        output.append("")

        # Quarterly estimates
        if quarterly:
            output.append("FORWARD QUARTERLY ESTIMATES:")
            output.append("-" * 90)
            output.append(f"{'Period':<15} {'Revenue Avg ($M)':<20} {'Rev High ($M)':<18} {'EPS Avg':<12} {'EPS High':<12} {'# Analysts':<10}")
            output.append("-" * 90)

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
            output.append("-" * 90)
            output.append(f"{'Period':<15} {'Revenue Avg ($M)':<20} {'Rev High ($M)':<18} {'EPS Avg':<12} {'EPS High':<12} {'# Analysts':<10}")
            output.append("-" * 90)

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
            output.append("-" * 80)
            output.append(f"EPS Estimate:  ${latest.get('epsAvg', 0):.2f}  (Low: ${latest.get('epsLow', 0):.2f}  High: ${latest.get('epsHigh', 0):.2f})")
            rev_avg = (latest.get('revenueAvg', 0) or 0) / 1e6
            rev_low = (latest.get('revenueLow', 0) or 0) / 1e6
            rev_high = (latest.get('revenueHigh', 0) or 0) / 1e6
            output.append(f"Revenue Est:   ${rev_avg:,.1f}M  (Low: ${rev_low:,.1f}M  High: ${rev_high:,.1f}M)")
            num_rev = latest.get('numAnalystsRevenue', 0) or 0
            num_eps = latest.get('numAnalystsEps', 0) or 0
            output.append(f"Analysts:      {num_rev} (revenue) / {num_eps} (EPS)")

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
        """Fetch earnings surprises. Cascade: Alpha Vantage → FMP → Perplexity."""
        try:
            # --- Cascade 1: Alpha Vantage (free, full history in 1 call) ---
            av_result = self._fetch_surprises_from_alpha_vantage(ticker, quarters)
            if av_result:
                return av_result

            # --- Cascade 2: FMP ---
            fmp_key = os.getenv("FMP_API_KEY")
            if fmp_key:
                return self._fetch_from_fmp(ticker, fmp_key, quarters)

            # --- Cascade 3: Perplexity ---
            logger.warning("No structured data sources available, using Perplexity fallback")
            return self._search_earnings_surprises(ticker, quarters)

        except Exception as e:
            logger.error(f"Error in get_earnings_surprises: {e}")
            return f"Error fetching earnings surprises for {ticker}: {str(e)}"

    def _fetch_surprises_from_alpha_vantage(self, ticker: str, quarters: int) -> Optional[str]:
        """Fetch earnings surprises from Alpha Vantage EARNINGS endpoint.

        Returns formatted string, or None to fall through to next source.
        """
        try:
            from data.alpha_vantage import AlphaVantageClient, AlphaVantageRateLimitError

            client = AlphaVantageClient()
            if not client.api_key:
                logger.info("ALPHA_VANTAGE_API_KEY not set, skipping Alpha Vantage for surprises")
                return None

            earnings_data = client.get_earnings(ticker)
            if not earnings_data:
                return None

            quarterly = earnings_data.get("quarterlyEarnings", [])
            if not quarterly:
                return None

            return self._format_av_earnings_surprises(quarterly[:quarters], ticker)

        except Exception as e:
            logger.info(f"Alpha Vantage earnings surprise fetch failed for {ticker}: {e}")
            return None

    def _format_av_earnings_surprises(self, data: List[Dict], ticker: str) -> str:
        """Format Alpha Vantage quarterlyEarnings into surprise table.

        AV fields: fiscalDateEnding, reportedDate, reportedEPS, estimatedEPS,
                    surprise, surprisePercentage
        """
        output = [f"EARNINGS SURPRISES HISTORY: {ticker} (via Alpha Vantage)\n"]
        output.append("=" * 80)
        output.append("")
        output.append(f"{'Date':<12} {'Actual EPS':<15} {'Est EPS':<15} {'Surprise':<15} {'Surprise %':<12}")
        output.append("-" * 80)

        beats = 0
        misses = 0
        meets = 0

        for entry in data:
            date_str = entry.get("reportedDate", entry.get("fiscalDateEnding", "Unknown"))
            reported_eps = entry.get("reportedEPS", "None")
            estimated_eps = entry.get("estimatedEPS", "None")
            surprise = entry.get("surprise", "None")
            surprise_pct = entry.get("surprisePercentage", "None")

            # Parse numeric values (AV returns strings)
            try:
                actual = float(reported_eps) if reported_eps != "None" else 0
            except (ValueError, TypeError):
                actual = 0
            try:
                estimated = float(estimated_eps) if estimated_eps != "None" else 0
            except (ValueError, TypeError):
                estimated = 0
            try:
                surprise_val = float(surprise) if surprise != "None" else actual - estimated
            except (ValueError, TypeError):
                surprise_val = actual - estimated
            try:
                surprise_pct_val = float(surprise_pct) if surprise_pct != "None" else (
                    (surprise_val / estimated * 100) if estimated != 0 else 0
                )
            except (ValueError, TypeError):
                surprise_pct_val = (surprise_val / estimated * 100) if estimated != 0 else 0

            # Classify
            if surprise_pct_val > 1:
                beats += 1
                result = "BEAT"
            elif surprise_pct_val < -1:
                misses += 1
                result = "MISS"
            else:
                meets += 1
                result = "MEET"

            output.append(
                f"{date_str:<12} ${actual:>13.2f} ${estimated:>13.2f} ${surprise_val:>13.2f} {surprise_pct_val:>10.1f}% {result}"
            )

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

    def _fetch_from_fmp(self, ticker: str, api_key: str, quarters: int) -> str:
        """Fetch historical earnings surprises from FMP /stable/earnings endpoint"""
        try:
            url = "https://financialmodelingprep.com/stable/earnings"
            params = {
                "symbol": ticker,
                "limit": quarters + 2,  # fetch extra to account for future entries
                "apikey": api_key
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            all_data = response.json()

            if not all_data:
                logger.warning(f"No FMP earnings data for {ticker}, using Perplexity fallback")
                return self._search_earnings_surprises(ticker, quarters)

            # Filter out future quarters (epsActual is null)
            historical = [e for e in all_data if e.get("epsActual") is not None]

            if not historical:
                logger.warning(f"No historical earnings data for {ticker}, using Perplexity fallback")
                return self._search_earnings_surprises(ticker, quarters)

            return self._format_earnings_surprises_from_calendar(historical[:quarters], ticker)

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
# Tool 8: Earnings Call Insights (NEW)
# ============================================================================

class EarningsCallInsightsTool(BaseTool):
    """Tool for analyzing earnings call transcripts and extracting key insights"""

    name: str = "get_earnings_call_insights"
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

        Data source cascade: FMP (unlimited) → Alpha Vantage (25/day free) → Perplexity web search.
        """
        try:
            # Validate inputs
            ticker = ticker.strip().upper()
            if not ticker or len(ticker) > 5:
                return f"Error: Invalid ticker format '{ticker}'. Please use 1-5 uppercase letters."

            if quarters < 1 or quarters > 8:
                return f"Error: quarters must be between 1-8. Received: {quarters}"

            # Get company info for context
            from data.financial_data import FinancialDataFetcher
            fetcher = FinancialDataFetcher()
            try:
                stock_info = fetcher.get_stock_info(ticker)
                company_name = stock_info.get('company_name', ticker) if stock_info else ticker
            except Exception as e:
                logger.warning(f"Could not fetch stock info for {ticker}: {e}")
                company_name = ticker

            # --- Cascade 1: FMP (Ultimate — unlimited transcripts) ---
            fmp_api_key = os.getenv("FMP_API_KEY")
            if fmp_api_key:
                if quarters == 1:
                    transcript_data = self._fetch_latest_transcript(ticker, fmp_api_key)
                else:
                    transcript_data = self._fetch_batch_transcripts(ticker, quarters, fmp_api_key)

                if transcript_data:
                    logger.info(f"Using FMP transcript data for {ticker}")
                    return self._analyze_with_perplexity(
                        ticker=ticker, company_name=company_name,
                        transcript_data=transcript_data, query=query, quarters=quarters,
                    )

            # --- Cascade 2: Alpha Vantage (free, 25 req/day) ---
            transcript_data = self._fetch_from_alpha_vantage(ticker, quarters)
            if transcript_data:
                logger.info(f"Using Alpha Vantage transcript data for {ticker}")
                return self._analyze_with_perplexity(
                    ticker=ticker, company_name=company_name,
                    transcript_data=transcript_data, query=query, quarters=quarters,
                )

            # --- Cascade 3: Perplexity web search (always available) ---
            logger.info(f"No transcript sources available for {ticker}, using Perplexity search fallback")
            return self._analyze_via_perplexity_search(ticker, company_name, query, quarters)

        except Exception as e:
            logger.error(f"Error in earnings insights tool: {e}", exc_info=True)
            return f"Error analyzing earnings call for {ticker}: {str(e)}"

    def _fetch_from_alpha_vantage(self, ticker: str, quarters: int) -> Optional[any]:
        """Try to fetch transcript(s) from Alpha Vantage.

        Returns transcript data in FMP-compatible format (single dict or list of dicts),
        or None if unavailable.
        """
        try:
            from data.alpha_vantage import AlphaVantageClient, AlphaVantageRateLimitError

            client = AlphaVantageClient()
            if not client.api_key:
                logger.info("ALPHA_VANTAGE_API_KEY not set, skipping Alpha Vantage")
                return None

            if quarters == 1:
                # Get latest transcript
                available = client.get_available_quarters(ticker)
                if not available:
                    logger.info(f"No Alpha Vantage earnings quarters found for {ticker}")
                    return None

                av_data = client.get_earnings_transcript(ticker, available[0])
                if not av_data:
                    return None

                return self._convert_av_transcript(av_data)
            else:
                # Batch transcripts
                av_transcripts = client.get_batch_transcripts(ticker, quarters)
                if not av_transcripts:
                    return None

                converted = [self._convert_av_transcript(t) for t in av_transcripts]
                converted = [c for c in converted if c is not None]
                return converted if converted else None

        except Exception as e:
            # Import may fail or client may raise — always fall through gracefully
            logger.info(f"Alpha Vantage transcript fetch failed for {ticker}: {e}")
            return None

    @staticmethod
    def _convert_av_transcript(av_data: Dict) -> Optional[Dict]:
        """Convert Alpha Vantage transcript format to FMP-compatible dict.

        AV format: {symbol, quarter, year, transcript: [{speaker, text, role}, ...]}
        FMP format: {content, quarter, year, date}

        The _analyze_with_perplexity method expects FMP format with a 'content' string.
        """
        if not av_data:
            return None

        segments = av_data.get("transcript", [])
        if not segments:
            return None

        # Build content string from segments
        content_parts = []
        for seg in segments:
            speaker = seg.get("speaker", "Unknown")
            role = seg.get("role", "")
            text = seg.get("text", "")
            if role:
                content_parts.append(f"{speaker} ({role}): {text}")
            else:
                content_parts.append(f"{speaker}: {text}")

        content = "\n\n".join(content_parts)

        quarter_num = av_data.get("quarter", "")
        year = av_data.get("year", "")

        return {
            "content": content,
            "quarter": f"Q{quarter_num}" if quarter_num else "Unknown",
            "year": str(year) if year else "Unknown",
            "date": f"{year}-Q{quarter_num}" if year and quarter_num else "Unknown",
        }

    def _get_fmp_earnings_dates(self, ticker: str, api_key: str, limit: int = 8) -> List[tuple]:
        """Get (year, quarter) tuples for recent earnings from FMP /stable/earnings.

        Derives the calendar quarter from the earnings reporting date.
        Returns list of (year, quarter) tuples, most recent first.
        """
        try:
            url = "https://financialmodelingprep.com/stable/earnings"
            params = {"symbol": ticker, "limit": limit * 2, "apikey": api_key}

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if not data:
                return []

            results = []
            for entry in data:
                # Skip future quarters (no actual EPS yet)
                if entry.get("epsActual") is None:
                    continue

                date_str = entry.get("date", "")
                if not date_str:
                    continue

                # Parse date to derive calendar quarter
                # The quarter param for transcripts = calendar quarter of reporting date
                try:
                    parts = date_str.split("-")
                    year = int(parts[0])
                    month = int(parts[1])
                    quarter = (month - 1) // 3 + 1
                    results.append((year, quarter))
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
                response = requests.get(url, params=params, timeout=30)

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
                response = requests.get(url, params=params, timeout=30)

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

    def _analyze_via_perplexity_search(
        self,
        ticker: str,
        company_name: str,
        query: Optional[str],
        quarters: int
    ) -> str:
        """Fallback: Use Perplexity to search for earnings call information when transcripts unavailable"""
        try:
            perplexity_key = os.getenv("PERPLEXITY_API_KEY")
            if not perplexity_key:
                return f"Error: No earnings call transcripts available for {ticker} and PERPLEXITY_API_KEY not found."

            client = OpenAI(api_key=perplexity_key, base_url="https://api.perplexity.ai")

            # Build search query based on whether user has specific question
            if query:
                search_query = f"""Analyze {company_name} ({ticker}) earnings call commentary specifically about: {query}

                Provide:
                1. What management said about this topic (with quotes if available)
                2. Relevant metrics or numbers mentioned
                3. Forward guidance related to this topic
                4. Analyst questions and management responses
                5. Overall tone and confidence level

                Use the most recent earnings call(s)."""
            else:
                period_text = "most recent earnings call" if quarters == 1 else f"last {quarters} earnings calls"
                search_query = f"""Provide a comprehensive analysis of {company_name} ({ticker}) {period_text}:

                1. FINANCIAL HIGHLIGHTS
                   - Revenue, EPS, margins vs expectations
                   - YoY and QoQ growth trends

                2. MANAGEMENT COMMENTARY
                   - Key quotes from CEO, CFO (with attribution)
                   - Strategic priorities and initiatives
                   - Business performance drivers

                3. FORWARD GUIDANCE
                   - Specific guidance for next quarter/year
                   - Changes from previous guidance
                   - Growth outlook and expectations

                4. ANALYST Q&A THEMES
                   - Main topics analysts focused on
                   - Key concerns raised
                   - Management responses and tone

                5. SENTIMENT ANALYSIS
                   - Management confidence level
                   - Red flags or positive signals
                   - Comparison to previous calls

                6. MANAGEMENT ACCOUNTABILITY
                   - Key promises management made on previous calls
                   - Which were delivered and which were missed?
                   - Forecasting accuracy (do they beat/miss their own guidance?)
                   - Any red flags (hedging, metric changes, executive departures)

                Include specific numbers, quotes with attribution, and dates."""

            response = client.chat.completions.create(
                model="sonar-pro",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert earnings call analyst. Extract specific insights, management quotes, guidance numbers, and sentiment from earnings calls. Be comprehensive but concise. Use markdown formatting."
                    },
                    {"role": "user", "content": search_query}
                ]
            )

            header = f"# Earnings Call Analysis: {company_name} ({ticker})\n"
            header += f"**Period:** {'Latest Quarter' if quarters == 1 else f'Last {quarters} Quarters'}\n"
            header += f"**Source:** Web search via Perplexity\n\n"
            header += "ℹ️ *Note: This analysis is based on web sources (earnings call summaries, news, analyst reports). "
            header += "FMP transcript access requires a premium subscription. "
            header += "Analysis quality remains high using authoritative financial sources.*\n\n"

            return header + response.choices[0].message.content

        except Exception as e:
            logger.error(f"Error in Perplexity search fallback: {e}")
            return f"Error: Unable to fetch earnings call information for {ticker}. FMP transcripts unavailable and Perplexity search failed: {str(e)}"

    def _analyze_with_perplexity(
        self,
        ticker: str,
        company_name: str,
        transcript_data: any,
        query: Optional[str],
        quarters: int
    ) -> str:
        """Use Perplexity to intelligently analyze transcript(s)"""
        try:
            # Get Perplexity API key
            perplexity_key = os.getenv("PERPLEXITY_API_KEY")
            if not perplexity_key:
                return "Error: PERPLEXITY_API_KEY not found in environment."

            # Prepare transcript text
            if quarters == 1:
                # Single transcript
                transcript_text = transcript_data.get('content', '')
                quarter = transcript_data.get('quarter', 'Unknown')
                year = transcript_data.get('year', 'Unknown')
                date = transcript_data.get('date', 'Unknown')

                # Truncate if too long
                if len(transcript_text) > 100000:
                    logger.warning(f"Transcript too long ({len(transcript_text)} chars), truncating to 100K")
                    transcript_text = transcript_text[:100000] + "\n\n[Transcript truncated due to length...]"

                context = f"{company_name} ({ticker}) - {quarter} {year} Earnings Call ({date})"
            else:
                # Multiple transcripts
                transcript_parts = []
                for t in transcript_data:
                    quarter = t.get('quarter', 'Unknown')
                    year = t.get('year', 'Unknown')
                    content = t.get('content', '')
                    transcript_parts.append(f"\n\n{'='*80}\n{quarter} {year} EARNINGS CALL\n{'='*80}\n\n{content[:25000]}")

                transcript_text = "\n".join(transcript_parts)
                context = f"{company_name} ({ticker}) - Last {quarters} Quarters"

            # Build Perplexity analysis prompt
            system_prompt = """You are an expert financial analyst specializing in earnings call analysis.

Your task is to extract actionable insights from earnings call transcripts for investors conducting due diligence.

ANALYSIS FRAMEWORK:

1. **FINANCIAL HIGHLIGHTS**
   - Key metrics: Revenue, EPS, margins, cash flow
   - Beat/miss vs consensus estimates
   - Year-over-year and quarter-over-quarter trends
   - Notable changes from previous quarters

2. **MANAGEMENT COMMENTARY** (CRITICAL - USE VERBATIM QUOTES)
   - Extract exact quotes from CEO, CFO, and executives
   - Include speaker attribution (e.g., "Tim Cook, CEO:")
   - Focus on strategic insights, not just number recitation
   - Capture tone and confidence level

3. **FORWARD GUIDANCE**
   - Specific numbers for next quarter/year (revenue, EPS, margins)
   - Qualitative outlook (growth drivers, headwinds)
   - Changes from previous guidance (raised, lowered, maintained)
   - Management's confidence level in guidance

4. **ANALYST Q&A THEMES**
   - What topics did analysts focus on?
   - Key questions and management responses (summarize, don't quote entire Q&A)
   - Concerns raised and how management addressed them
   - New information revealed in Q&A vs prepared remarks

5. **TONE & SENTIMENT ANALYSIS**
   - Overall tone: Confident, Cautious, Defensive, Mixed
   - Body language indicators (hedging language, enthusiasm, defensiveness)
   - Compare tone to previous calls
   - Red flags or positive signals

6. **MANAGEMENT ACCOUNTABILITY**
   - Specific promises or commitments made (with quotes and attribution)
   - Forward guidance numbers stated (revenue range, EPS target, margin goals)
   - Strategic initiatives announced (product launches, market entries, cost cuts)
   - Compare to PREVIOUS quarter's promises: delivered or missed?
   - Red flags: hedging, metric changes, executive departures, GAAP vs non-GAAP gaps

OUTPUT FORMAT:
- Use clear markdown sections with headers
- Use bullet points for readability
- Use **bold** for key metrics and important points
- Use > blockquotes for verbatim management quotes
- Use emojis sparingly for visual clarity (📈📉✅⚠️)
- Be comprehensive but concise - aim for 800-1200 words

IMPORTANT RULES:
1. ALWAYS include verbatim quotes with attribution
2. Be objective - report what was said, not your opinion
3. Quantify whenever possible (use specific numbers)
4. Flag any red flags or concerning statements
5. If query is provided, focus analysis on that topic while still covering key points"""

            # Build user prompt
            if query:
                user_prompt = f"""Analyze the earnings call transcript(s) below for {context}.

**SPECIFIC FOCUS:** {query}

While your primary focus should be on "{query}", also provide:
- Brief financial highlights
- Key management quotes related to this topic
- Forward guidance if relevant
- Overall takeaways

TRANSCRIPT(S):
{transcript_text}

Provide a focused analysis that answers the user's specific question while maintaining context."""
            else:
                user_prompt = f"""Analyze the earnings call transcript(s) below for {context}.

Provide a comprehensive analysis following the framework in your instructions.

TRANSCRIPT(S):
{transcript_text}

Provide a thorough earnings call analysis that an investor would use for due diligence."""

            # Call Perplexity API
            headers = {
                "Authorization": f"Bearer {perplexity_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": "sonar-pro",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "max_tokens": 4000,
                "temperature": 0.2,
                "return_citations": False,
                "return_related_questions": False
            }

            logger.info(f"Sending transcript to Perplexity for analysis (length: {len(transcript_text)} chars)")
            response = requests.post(
                "https://api.perplexity.ai/chat/completions",
                headers=headers,
                json=payload,
                timeout=60
            )

            if response.status_code == 200:
                result = response.json()
                analysis = result['choices'][0]['message']['content']

                # Add header with metadata
                if quarters == 1:
                    header = f"# Earnings Call Analysis: {company_name} ({ticker})\n"
                    header += f"**Quarter:** {quarter} {year}\n"
                    header += f"**Call Date:** {date}\n\n"
                else:
                    header = f"# Earnings Call Analysis: {company_name} ({ticker})\n"
                    header += f"**Period:** Last {quarters} Quarters\n\n"

                return header + analysis
            else:
                logger.error(f"Perplexity API error: {response.status_code} - {response.text}")
                return f"Error: Failed to analyze transcript with Perplexity (HTTP {response.status_code})"

        except Exception as e:
            logger.error(f"Error in Perplexity analysis: {e}", exc_info=True)
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
