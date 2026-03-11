"""
LangChain Tools for DCF Analysis Agent
"""
from langchain.tools import BaseTool
from typing import Optional, Type, List, Dict
from pydantic import BaseModel, Field
from data.financial_data import FinancialDataFetcher
from calculators.dcf_calculator import DCFCalculator, DCFAssumptions
from tools.equity_analyst_tools import CompetitorAnalysisTool
from shared.tavily_client import get_tavily_client
from data.fred_client import get_fred_client
import json
import logging
import os
import re

logger = logging.getLogger(__name__)


# Tool Input Schemas
class StockInfoInput(BaseModel):
    """Input for stock information tool"""
    ticker: str = Field(description="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)")


class FinancialMetricsInput(BaseModel):
    """Input for financial metrics tool"""
    ticker: str = Field(description="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)")


class DCFAnalysisInput(BaseModel):
    """Input for DCF analysis tool using professional forward-looking methodology"""
    ticker: str = Field(description="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)")

    # === GROWTH ASSUMPTIONS (Forward-Looking) ===
    # IMPORTANT: Use analyst consensus for near-term, NOT historical CAGR
    near_term_growth_rate: Optional[float] = Field(
        default=None,
        description="Near-term revenue growth (Years 1-2) from ANALYST CONSENSUS (e.g., 0.20 for 20%). REQUIRED - search web for 'ticker revenue growth estimate 2025 2026'. Do NOT use historical CAGR."
    )
    long_term_growth_rate: Optional[float] = Field(
        default=None,
        description="Long-term revenue growth (Years 3-5 fade target) based on INDUSTRY AVERAGE (e.g., 0.08 for 8%). Search for industry growth rates. Growth fades from near-term to this value."
    )
    terminal_growth_rate: Optional[float] = Field(
        default=None,
        description="Terminal perpetual growth rate (e.g., 0.025 for 2.5%). REQUIRED. Should be GDP growth + inflation. Typical range: 2-3%."
    )

    # === OPERATING ASSUMPTIONS ===
    ebit_margin: Optional[float] = Field(
        default=None,
        description="EBIT (Operating Income) margin as % of revenue. If not provided, calculated from historical data."
    )
    tax_rate: Optional[float] = Field(
        default=None,
        description="Effective tax rate (e.g., 0.21 for 21%). If not provided, uses rate from financial statements."
    )

    # === CAPITAL INTENSITY (for UFCF calculation) ===
    # UFCF = NOPAT + D&A - CapEx - ΔNWC
    capex_to_revenue: Optional[float] = Field(
        default=None,
        description="Capital expenditures as % of revenue (e.g., 0.05 for 5%). Calculated from historical data if not provided."
    )
    depreciation_to_revenue: Optional[float] = Field(
        default=None,
        description="Depreciation & Amortization as % of revenue (e.g., 0.04 for 4%). Calculated from historical data if not provided."
    )
    nwc_to_revenue: Optional[float] = Field(
        default=None,
        description="Net Working Capital as % of revenue, normalized (e.g., 0.10 for 10%). Used for ΔNWC calculation."
    )

    # === DISCOUNT RATE COMPONENTS ===
    beta: Optional[float] = Field(
        default=None,
        description="Stock beta coefficient. IMPORTANT: Search web for current beta. Do not use default."
    )
    risk_free_rate: Optional[float] = Field(
        default=None,
        description="Risk-free rate from current 10-year Treasury yield (e.g., 0.045 for 4.5%). REQUIRED - search web for current yield."
    )
    market_risk_premium: Optional[float] = Field(
        default=None,
        description="Market risk premium (e.g., 0.055 for 5.5%). REQUIRED. Use 5-5.5% for mega-cap quality stocks, 6-7% for others."
    )
    cost_of_debt: Optional[float] = Field(
        default=None,
        description="Pre-tax cost of debt (e.g., 0.05 for 5%). Calculated from Interest Expense / Total Debt if not provided."
    )

    # === PROJECTION PARAMETERS ===
    projection_years: Optional[int] = Field(
        default=5,
        description="Number of years to project (typically 5 years)"
    )

    # === OVERRIDE FIELDS (use when API data is missing or unreliable) ===
    current_price: Optional[float] = Field(
        default=None,
        description="Current stock price in USD. Pass this when you know the price from get_stock_info (e.g., 227.52). Used when API returns 0."
    )
    shares_outstanding: Optional[float] = Field(
        default=None,
        description="Shares outstanding in millions (e.g., 15441.0). Pass this from get_financial_metrics. Used when API returns 0."
    )


class WebSearchInput(BaseModel):
    """Input for web search tool"""
    query: str = Field(description="Search query to find information on the web (e.g., 'Apple beta coefficient 2024', 'Tesla revenue growth forecast')")


class MarketParametersInput(BaseModel):
    """Input for market parameters tool"""
    ticker: str = Field(description="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)")
    company_name: str = Field(default="", description="Company name (optional, improves search accuracy)")
    industry: str = Field(default="", description="Industry name (optional, for industry growth rate)")


class DCFComparisonInput(BaseModel):
    """Input for DCF comparison tool"""
    ticker: str = Field(description="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)")


class MultiplesValuationInput(BaseModel):
    """Input for multiples-based valuation tool"""
    ticker: str = Field(description="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)")
    peer_tickers: Optional[str] = Field(
        default="",
        description="Comma-separated list of peer company tickers for comparison (e.g., 'MSFT,GOOGL,META'). If empty, will use industry averages."
    )


# Tool Implementations
class GetStockInfoTool(BaseTool):
    """Tool to get basic stock information"""
    name: str = "get_stock_info"
    description: str = "Get basic information about a stock including company name, sector, industry, market cap, and current price. Use this first to understand the company."
    args_schema: Type[BaseModel] = StockInfoInput

    def _run(self, ticker: str) -> str:
        """Fetch stock information"""
        fetcher = FinancialDataFetcher()
        info = fetcher.get_stock_info(ticker.strip().upper())

        if not info:
            return f"Error: Could not fetch information for ticker {ticker}"

        result = f"""
Stock Information for {ticker.upper()}:
- Company: {info.get('company_name', 'N/A')}
- Sector: {info.get('sector', 'N/A')}
- Industry: {info.get('industry', 'N/A')}
- Market Cap: ${info.get('market_cap', 0):,.0f}
- Current Price: ${info.get('current_price', 0):.2f}
- Currency: {info.get('currency', 'USD')}
"""
        return result

    async def _arun(self, ticker: str) -> str:
        """Async version"""
        return self._run(ticker)


class GetFinancialMetricsTool(BaseTool):
    """Tool to get key financial metrics for DCF analysis"""
    name: str = "get_financial_metrics"
    description: str = "Get key financial metrics needed for DCF analysis including revenue, free cash flow, debt, cash, and historical growth rates. Use this to gather data before performing DCF."
    args_schema: Type[BaseModel] = FinancialMetricsInput

    def _run(self, ticker: str) -> str:
        """Fetch financial metrics"""
        fetcher = FinancialDataFetcher()
        metrics = fetcher.get_key_metrics(ticker.strip().upper())

        if not metrics:
            return f"Error: Could not fetch financial metrics for ticker {ticker}"

        # --- Margins: prefer API-provided values, fall back to manual calculation ---
        latest_rev = metrics.get('latest_revenue', 0) or 1
        has_rev = metrics.get('latest_revenue', 0) > 0

        gross_margin = metrics.get('gross_margin') or (
            metrics.get('latest_gross_profit', 0) / latest_rev if has_rev else None
        )
        operating_margin = metrics.get('operating_margin') or (
            metrics.get('latest_ebit', 0) / latest_rev if has_rev else 0
        )
        net_margin = metrics.get('net_margin') or (
            metrics.get('latest_net_income', 0) / latest_rev if has_rev else 0
        )
        fcf_margin = metrics.get('latest_fcf', 0) / latest_rev if has_rev else 0

        # --- DCF driver ratios: still derived from raw statements ---
        capex_to_revenue = metrics.get('latest_capex', 0) / latest_rev if has_rev else 0
        da_to_revenue = metrics.get('latest_depreciation_amortization', 0) / latest_rev if has_rev else 0
        nwc_to_revenue = metrics.get('net_working_capital', 0) / latest_rev if has_rev else 0
        cost_of_debt = (
            metrics.get('latest_interest_expense', 0) / metrics.get('total_debt', 1)
            if metrics.get('total_debt', 0) > 0 else 0.05
        )

        # --- Growth rates: prefer API, fall back to manual CAGR ---
        revenue_growth = metrics.get('revenue_growth_rate') or fetcher.calculate_historical_growth_rate(
            metrics.get('historical_revenue', [])
        )
        fcf_growth = metrics.get('fcf_growth_rate') or fetcher.calculate_historical_growth_rate(
            metrics.get('historical_fcf', [])
        )
        earnings_growth = metrics.get('earnings_growth_rate')

        def pct(v):
            return f"{v * 100:.1f}%" if v is not None else "N/A"

        def dollar(v, label=""):
            if v is None:
                return "N/A"
            if abs(v) >= 1e12:
                return f"${v/1e12:.2f}T"
            if abs(v) >= 1e9:
                return f"${v/1e9:.2f}B"
            if abs(v) >= 1e6:
                return f"${v/1e6:.0f}M"
            return f"${v:,.0f}"

        result = f"""Financial Metrics for {ticker.upper()}:

Current Financials (TTM):
- Revenue: {dollar(metrics.get('latest_revenue', 0))}
- Gross Profit: {dollar(metrics.get('latest_gross_profit', 0))} (Gross Margin: {pct(gross_margin)})
- EBIT (Operating Income): {dollar(metrics.get('latest_ebit', 0))} (EBIT Margin: {pct(operating_margin)})
- Net Income: {dollar(metrics.get('latest_net_income', 0))} (Net Margin: {pct(net_margin)})
- Free Cash Flow: {dollar(metrics.get('latest_fcf', 0))} (FCF Margin: {pct(fcf_margin)})
- CapEx: {dollar(metrics.get('latest_capex', 0))}
- D&A: {dollar(metrics.get('latest_depreciation_amortization', 0))}

Balance Sheet:
- Total Debt: {dollar(metrics.get('total_debt', 0))}
- Cash & Equivalents: {dollar(metrics.get('cash_and_equivalents', 0))}
- Net Debt: {dollar(metrics.get('total_debt', 0) - metrics.get('cash_and_equivalents', 0))}
- Shareholders Equity: {dollar(metrics.get('shareholders_equity', 0))}
- Net Working Capital: {dollar(metrics.get('net_working_capital', 0))}
- Shares Outstanding: {metrics.get('shares_outstanding', 0):,.0f}

Capital Structure & Rates:
- Effective Tax Rate: {pct(metrics.get('effective_tax_rate', 0.21))}
- Interest Expense: {dollar(metrics.get('latest_interest_expense', 0))}
- Implied Cost of Debt: {cost_of_debt * 100:.2f}%
- Beta: {metrics.get('beta', 1.0):.2f}

Profitability Margins (API):
- Gross Margin: {pct(gross_margin)}
- Operating (EBIT) Margin: {pct(operating_margin)}
- Net Margin: {pct(net_margin)}
- FCF Margin: {pct(fcf_margin)}

Return Metrics (API):
- Return on Equity (ROE): {pct(metrics.get('return_on_equity'))}
- Return on Assets (ROA): {pct(metrics.get('return_on_assets'))}
- Return on Invested Capital (ROIC): {pct(metrics.get('return_on_invested_capital'))}

Valuation Multiples (API):
- P/E Ratio: {f"{metrics['price_to_earnings']:.1f}x" if metrics.get('price_to_earnings') else "N/A"}
- Price / Book: {f"{metrics['price_to_book']:.2f}x" if metrics.get('price_to_book') else "N/A"}
- Price / Sales: {f"{metrics['price_to_sales']:.2f}x" if metrics.get('price_to_sales') else "N/A"}
- EV / EBITDA: {f"{metrics['ev_to_ebitda']:.1f}x" if metrics.get('ev_to_ebitda') else "N/A"}
- EV / Revenue: {f"{metrics['ev_to_revenue']:.2f}x" if metrics.get('ev_to_revenue') else "N/A"}
- PEG Ratio: {f"{metrics['peg_ratio']:.2f}" if metrics.get('peg_ratio') else "N/A"}
- FCF Yield: {pct(metrics.get('fcf_yield'))}
- Enterprise Value: {dollar(metrics.get('enterprise_value_api'))}

Per-Share Metrics (API):
- EPS: {f"${metrics['earnings_per_share']:.2f}" if metrics.get('earnings_per_share') else "N/A"}
- Book Value / Share: {f"${metrics['book_value_per_share']:.2f}" if metrics.get('book_value_per_share') else "N/A"}
- FCF / Share: {f"${metrics['fcf_per_share']:.2f}" if metrics.get('fcf_per_share') else "N/A"}

Leverage & Liquidity (API):
- Debt / Equity: {f"{metrics['debt_to_equity_ratio']:.2f}x" if metrics.get('debt_to_equity_ratio') else "N/A"}
- Debt / Assets: {f"{metrics['debt_to_assets_ratio']:.2f}x" if metrics.get('debt_to_assets_ratio') else "N/A"}
- Interest Coverage: {f"{metrics['interest_coverage_ratio']:.1f}x" if metrics.get('interest_coverage_ratio') else "N/A"}
- Current Ratio: {f"{metrics['current_ratio']:.2f}" if metrics.get('current_ratio') else "N/A"}
- Quick Ratio: {f"{metrics['quick_ratio']:.2f}" if metrics.get('quick_ratio') else "N/A"}

DCF Driver Ratios (from raw statements):
- CapEx / Revenue: {pct(capex_to_revenue)}
- D&A / Revenue: {pct(da_to_revenue)}
- NWC / Revenue: {pct(nwc_to_revenue)}
"""

        # Build year-by-year historical table
        years = metrics.get('historical_years', [])
        revenues = metrics.get('historical_revenue', [])
        gross_profits_hist = metrics.get('historical_gross_profit', [])
        net_incomes = metrics.get('historical_net_income', [])
        ebits = metrics.get('historical_ebit', [])
        fcfs = metrics.get('historical_fcf', [])

        if revenues and years:
            n = min(len(revenues), len(years), 5)
            result += "\nHistorical Financials — Year by Year (most recent first):\n"
            result += "| Fiscal Year | Revenue | Gross Profit | Gross Margin | EBIT | EBIT Margin | Net Income | Net Margin | FCF | FCF Margin |\n"
            result += "|-------------|---------|-------------|-------------|------|------------|-----------|------------|-----|------------|\n"
            for i in range(n):
                rev = revenues[i] if i < len(revenues) else 0
                gp = gross_profits_hist[i] if i < len(gross_profits_hist) else 0
                ebit = ebits[i] if i < len(ebits) else 0
                ni = net_incomes[i] if i < len(net_incomes) else 0
                fcf = fcfs[i] if i < len(fcfs) else 0
                yr = years[i] if i < len(years) else "N/A"

                gm_pct = f"{gp/rev*100:.1f}%" if rev > 0 and gp else "N/A"
                ebit_pct = f"{ebit/rev*100:.1f}%" if rev > 0 else "N/A"
                ni_pct = f"{ni/rev*100:.1f}%" if rev > 0 else "N/A"
                fcf_pct = f"{fcf/rev*100:.1f}%" if rev > 0 else "N/A"

                def fmt(v): return f"${v/1e9:.2f}B" if abs(v) >= 1e9 else f"${v/1e6:.0f}M"

                result += f"| {yr} | {fmt(rev)} | {fmt(gp) if gp else 'N/A'} | {gm_pct} | {fmt(ebit)} | {ebit_pct} | {fmt(ni)} | {ni_pct} | {fmt(fcf) if fcf else 'N/A'} | {fcf_pct} |\n"

        result += f"\nGrowth Rates (API where available, else 5Y CAGR):\n"
        result += f"- Revenue Growth: {pct(revenue_growth)}\n"
        result += f"- FCF Growth: {pct(fcf_growth)}\n"
        if earnings_growth is not None:
            result += f"- Earnings Growth: {pct(earnings_growth)}\n"
        if metrics.get('ebitda_growth_rate') is not None:
            result += f"- EBITDA Growth: {pct(metrics.get('ebitda_growth_rate'))}\n"

        try:
            _years = list(reversed(metrics.get('historical_years', [])))
            _rev = list(reversed(metrics.get('historical_revenue', [])))
            _fcf_list = list(reversed(metrics.get('historical_fcf', [])))
            _gp_list = list(reversed(metrics.get('historical_gross_profit', [])))

            # Chart 1: Revenue & FCF
            _chart_data = [
                {"period": str(_years[i]), "revenue_b": round(_rev[i] / 1e9, 2), "fcf_b": round(_fcf_list[i] / 1e9, 2)}
                for i in range(min(len(_years), len(_rev), len(_fcf_list)))
                if _rev[i] and _fcf_list[i]
            ]
            if _chart_data:
                chart_id = f"financial_metrics_{ticker.upper()}"
                chart_json = json.dumps({
                    "id": chart_id,
                    "chart_type": "bar_line",
                    "title": f"{ticker.upper()} Annual Revenue & FCF",
                    "data": _chart_data,
                    "series": [
                        {"key": "revenue_b", "label": "Revenue ($B)", "type": "bar", "color": "#2563EB", "yAxis": "left"},
                        {"key": "fcf_b", "label": "FCF ($B)", "type": "line", "color": "#10B981", "yAxis": "right"}
                    ],
                    "y_format": "currency_b",
                    "y_right_format": "currency_b"
                })
                result += f"\n---CHART_DATA:{chart_id}---\n{chart_json}\n---END_CHART_DATA:{chart_id}---\n[CHART_INSTRUCTION: Place {{{{CHART:{chart_id}}}}} on its own line where you discuss revenue and FCF history. Do NOT reproduce the CHART_DATA block.]"

            # Chart 2: Revenue vs Cost of Revenue vs Gross Profit
            _cost_chart_data = [
                {
                    "period": str(_years[i]),
                    "revenue_b": round(_rev[i] / 1e9, 2),
                    "cost_b": round((_rev[i] - _gp_list[i]) / 1e9, 2),
                    "gross_profit_b": round(_gp_list[i] / 1e9, 2),
                }
                for i in range(min(len(_years), len(_rev), len(_gp_list)))
                if _rev[i] and _gp_list[i]
            ]
            if _cost_chart_data:
                cost_chart_id = f"revenue_vs_cost_{ticker.upper()}"
                cost_chart_json = json.dumps({
                    "id": cost_chart_id,
                    "chart_type": "bar_line",
                    "title": f"{ticker.upper()} Revenue vs Cost of Revenue",
                    "data": _cost_chart_data,
                    "series": [
                        {"key": "revenue_b", "label": "Revenue ($B)", "type": "bar", "color": "#2563EB", "yAxis": "left"},
                        {"key": "cost_b", "label": "Cost of Revenue ($B)", "type": "bar", "color": "#EF4444", "yAxis": "left"},
                        {"key": "gross_profit_b", "label": "Gross Profit ($B)", "type": "line", "color": "#10B981", "yAxis": "right"},
                    ],
                    "y_format": "currency_b",
                    "y_right_format": "currency_b"
                })
                result += f"\n---CHART_DATA:{cost_chart_id}---\n{cost_chart_json}\n---END_CHART_DATA:{cost_chart_id}---\n[CHART_INSTRUCTION: Place {{{{CHART:{cost_chart_id}}}}} on its own line where you discuss revenue vs cost or gross profit. Do NOT reproduce the CHART_DATA block.]"
        except Exception:
            pass

        return result

    async def _arun(self, ticker: str) -> str:
        """Async version"""
        return self._run(ticker)


class PerformDCFAnalysisTool(BaseTool):
    """Tool to perform complete DCF analysis with scenarios"""
    name: str = "perform_dcf_analysis"
    description: str = """Perform a professional DCF (Discounted Cash Flow) valuation with Bull, Base, and Bear scenarios.

    METHODOLOGY:
    - Uses industry-standard UFCF formula: NOPAT + D&A - CapEx - ΔNWC
    - Forward-looking growth: Year 1-2 analyst consensus → Year 3-5 fade to industry avg → Terminal GDP growth
    - Normalized NWC as % of revenue (avoids balance sheet volatility)

    REQUIRED PARAMETERS (from web search):
    - near_term_growth_rate: Analyst consensus revenue growth for Years 1-2 (search for "ticker revenue estimate 2025")
    - long_term_growth_rate: Industry average growth rate for Years 3-5 fade target
    - terminal_growth_rate: GDP + inflation (typically 2.5%)
    - risk_free_rate: Current 10-year Treasury yield (search for "10 year treasury yield")
    - market_risk_premium: 5-5.5% for mega-cap quality, 6-7% for others
    - beta: Current stock beta (search for "ticker beta")

    CALCULATED FROM FINANCIALS (if not provided):
    - ebit_margin, tax_rate, capex_to_revenue, depreciation_to_revenue, nwc_to_revenue, cost_of_debt

    DO NOT use historical CAGR for growth projections - use forward-looking analyst estimates."""
    args_schema: Type[BaseModel] = DCFAnalysisInput

    def _run(
        self,
        ticker: str,
        near_term_growth_rate: Optional[float] = None,  # Years 1-2: Analyst consensus
        long_term_growth_rate: Optional[float] = None,  # Years 3-5: Industry average
        terminal_growth_rate: Optional[float] = None,   # Perpetuity: GDP growth
        ebit_margin: Optional[float] = None,
        tax_rate: Optional[float] = None,
        capex_to_revenue: Optional[float] = None,
        depreciation_to_revenue: Optional[float] = None,
        nwc_to_revenue: Optional[float] = None,
        beta: Optional[float] = None,
        risk_free_rate: Optional[float] = None,
        market_risk_premium: Optional[float] = None,
        cost_of_debt: Optional[float] = None,
        projection_years: int = 5,
        current_price: Optional[float] = None,
        shares_outstanding: Optional[float] = None,
    ) -> str:
        """Perform DCF analysis"""
        try:
            # Sanitize ticker input - extract only the ticker symbol
            # Also handle case where all parameters are passed as JSON string
            ticker_str = str(ticker).strip()
            import re
            import json

            # If parameters look like JSON, try to parse them
            parsed_params = {}
            if '{' in ticker_str:
                try:
                    # Remove markdown code blocks if present
                    json_str = re.sub(r'```json\s*|\s*```', '', ticker_str)
                    # Remove JavaScript-style comments (// comment)
                    json_str = re.sub(r'//[^\n]*', '', json_str)
                    # Remove trailing commas before closing braces/brackets
                    json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
                    parsed_params = json.loads(json_str)
                    logger.info(f"Parsed JSON parameters from ticker string: {list(parsed_params.keys())}")

                    # Extract ticker from parsed JSON
                    ticker_clean = parsed_params.get('ticker', '').upper()

                    # Override None parameters with parsed values if available
                    if near_term_growth_rate is None and 'near_term_growth_rate' in parsed_params:
                        near_term_growth_rate = parsed_params['near_term_growth_rate']
                    if long_term_growth_rate is None and 'long_term_growth_rate' in parsed_params:
                        long_term_growth_rate = parsed_params['long_term_growth_rate']
                    if terminal_growth_rate is None and 'terminal_growth_rate' in parsed_params:
                        terminal_growth_rate = parsed_params['terminal_growth_rate']
                    if ebit_margin is None and 'ebit_margin' in parsed_params:
                        ebit_margin = parsed_params['ebit_margin']
                    if tax_rate is None and 'tax_rate' in parsed_params:
                        tax_rate = parsed_params['tax_rate']
                    if capex_to_revenue is None and 'capex_to_revenue' in parsed_params:
                        capex_to_revenue = parsed_params['capex_to_revenue']
                    if depreciation_to_revenue is None and 'depreciation_to_revenue' in parsed_params:
                        depreciation_to_revenue = parsed_params['depreciation_to_revenue']
                    if nwc_to_revenue is None and 'nwc_to_revenue' in parsed_params:
                        nwc_to_revenue = parsed_params['nwc_to_revenue']
                    if beta is None and 'beta' in parsed_params:
                        beta = parsed_params['beta']
                    if risk_free_rate is None and 'risk_free_rate' in parsed_params:
                        risk_free_rate = parsed_params['risk_free_rate']
                    if market_risk_premium is None and 'market_risk_premium' in parsed_params:
                        market_risk_premium = parsed_params['market_risk_premium']
                    if cost_of_debt is None and 'cost_of_debt' in parsed_params:
                        cost_of_debt = parsed_params['cost_of_debt']
                    # Extract current_price and shares_outstanding from JSON if provided
                    # (fallback for old-style JSON input; schema fields take precedence)
                    if current_price is None:
                        current_price = parsed_params.get('current_price', None)
                    if shares_outstanding is None:
                        shares_outstanding = parsed_params.get('shares_outstanding', None)

                except json.JSONDecodeError:
                    # If JSON parsing fails, fall back to regex extraction
                    match = re.search(r'["\']?ticker["\']?\s*[:=]\s*["\']?([A-Z]+)["\']?', ticker_str, re.IGNORECASE)
                    if match:
                        ticker_clean = match.group(1).upper()
                    else:
                        match = re.search(r'\b([A-Z]{1,5})\b', ticker_str)
                        ticker_clean = match.group(1) if match else ticker_str
            else:
                ticker_clean = ticker_str.upper()

            # Final cleanup
            ticker_clean = ticker_clean.replace('"', '').replace("'", '').strip()
            ticker_clean = ticker_clean.split()[0] if ticker_clean.split() else ticker_clean

            logger.info(f"Sanitized ticker: '{ticker}' -> '{ticker_clean}'")

            # Fetch necessary data
            fetcher = FinancialDataFetcher()
            metrics = fetcher.get_key_metrics(ticker_clean)
            info = fetcher.get_stock_info(ticker_clean)

            if not metrics or not info:
                return f"Error: Could not fetch data for {ticker_clean}"

            # Extract required values — prefer explicitly-passed values over API data
            current_revenue = metrics.get('latest_revenue', 0)
            api_price = info.get('current_price', 0)
            if api_price > 0:
                current_price = api_price
            elif current_price is None or current_price <= 0:
                current_price = 0
            api_shares = metrics.get('shares_outstanding', 0)
            if api_shares > 0:
                shares_outstanding = api_shares
            elif shares_outstanding is None or shares_outstanding <= 0:
                shares_outstanding = 0
            total_debt = metrics.get('total_debt', 0)
            cash = metrics.get('cash_and_equivalents', 0)

            # Validate data
            if current_revenue <= 0 or shares_outstanding <= 0:
                return f"Error: Insufficient financial data for {ticker_clean}. Revenue or shares outstanding is missing."

            # Calculate parameters from financial data if not provided
            # Growth rates should come from analyst consensus (via web search), NOT historical CAGR

            # 1. Near-term growth rate (Years 1-2) - REQUIRED from analyst consensus
            if near_term_growth_rate is None:
                return f"""Error: near_term_growth_rate is REQUIRED for {ticker_clean}.

This should be the analyst consensus revenue growth rate for Years 1-2.
Search the web for "{ticker_clean} revenue growth estimate 2025 2026 analyst consensus" and provide this value.

DO NOT use historical CAGR - use forward-looking analyst estimates."""

            # 2. Long-term growth rate (Years 3-5 fade target) - defaults to industry average or half of near-term
            if long_term_growth_rate is None:
                # If not provided, use a reasonable fade target (half of near-term, min 5%)
                long_term_growth_rate = max(near_term_growth_rate * 0.5, 0.05)
                logger.info(f"Long-term growth not provided, using fade target: {long_term_growth_rate:.2%}")

            # 3. EBIT margin
            if ebit_margin is None:
                latest_ebit = metrics.get('latest_ebit', 0)
                if latest_ebit > 0 and current_revenue > 0:
                    ebit_margin = latest_ebit / current_revenue
                    logger.info(f"Calculated EBIT margin: {ebit_margin:.2%}")
                else:
                    return f"Error: Cannot calculate EBIT margin for {ticker_clean}. Missing EBIT or revenue data."

            # 4. Tax rate
            if tax_rate is None:
                tax_rate = metrics.get('effective_tax_rate')
                if tax_rate is None or tax_rate <= 0:
                    tax_rate = 0.21  # Default to US corporate rate
                    logger.info(f"Tax rate not available, using default: {tax_rate:.2%}")
                else:
                    logger.info(f"Using effective tax rate: {tax_rate:.2%}")

            # ================================================================
            # CAPITAL INTENSITY PARAMETERS (for UFCF calculation)
            # UFCF = NOPAT + D&A - CapEx - ΔNWC
            # ================================================================

            # 5. CapEx to revenue
            if capex_to_revenue is None:
                latest_capex = metrics.get('latest_capex', 0)
                if latest_capex > 0 and current_revenue > 0:
                    capex_to_revenue = latest_capex / current_revenue
                    logger.info(f"Calculated CapEx/Revenue: {capex_to_revenue:.2%}")
                else:
                    capex_to_revenue = 0.05  # Default 5%
                    logger.warning(f"CapEx not available for {ticker_clean}, using default: {capex_to_revenue:.2%}")

            # 6. Depreciation to revenue
            if depreciation_to_revenue is None:
                latest_da = metrics.get('latest_depreciation_amortization', 0)
                if latest_da > 0 and current_revenue > 0:
                    depreciation_to_revenue = latest_da / current_revenue
                    logger.info(f"Calculated D&A/Revenue: {depreciation_to_revenue:.2%}")
                else:
                    depreciation_to_revenue = 0.04  # Default 4%
                    logger.warning(f"D&A not available for {ticker_clean}, using default: {depreciation_to_revenue:.2%}")

            # 7. NWC to revenue (normalized)
            # NOTE: NWC can be negative (e.g., Apple collects cash before paying suppliers)
            # Cap extreme values to prevent unrealistic ΔNWC consuming all cash flow
            MAX_NWC_TO_REVENUE = 0.30  # 30% max - beyond this indicates unusual business model
            MIN_NWC_TO_REVENUE = -0.20  # -20% min - negative NWC is a cash source

            if nwc_to_revenue is None:
                nwc = metrics.get('net_working_capital', 0)
                if current_revenue > 0:
                    raw_nwc_ratio = nwc / current_revenue
                    # Cap extreme values
                    if raw_nwc_ratio > MAX_NWC_TO_REVENUE:
                        nwc_to_revenue = MAX_NWC_TO_REVENUE
                        logger.warning(
                            f"{ticker_clean}: NWC/Revenue ({raw_nwc_ratio:.1%}) capped at {MAX_NWC_TO_REVENUE:.0%}. "
                            f"Company has unusual working capital structure."
                        )
                    elif raw_nwc_ratio < MIN_NWC_TO_REVENUE:
                        nwc_to_revenue = MIN_NWC_TO_REVENUE
                        logger.warning(
                            f"{ticker_clean}: NWC/Revenue ({raw_nwc_ratio:.1%}) floored at {MIN_NWC_TO_REVENUE:.0%}."
                        )
                    else:
                        nwc_to_revenue = raw_nwc_ratio
                        logger.info(f"Calculated NWC/Revenue: {nwc_to_revenue:.2%}")
                else:
                    nwc_to_revenue = 0.10  # Default 10%
                    logger.warning(f"NWC not available for {ticker_clean}, using default: {nwc_to_revenue:.2%}")

            # 8. Beta
            if beta is not None:
                final_beta = beta
                logger.info(f"Using beta from web search/parameter: {final_beta}")
            else:
                final_beta = metrics.get('beta')
                if final_beta is None:
                    return f"Error: Beta is REQUIRED for {ticker_clean}. Search web for '{ticker_clean} beta coefficient'."
                logger.info(f"Using beta from financial data: {final_beta}")

            # 9. Cost of debt
            if cost_of_debt is None:
                interest_expense = metrics.get('latest_interest_expense', 0)
                if total_debt > 0 and interest_expense > 0:
                    cost_of_debt = interest_expense / total_debt
                    logger.info(f"Calculated cost of debt: {cost_of_debt:.2%}")
                elif total_debt > 0:
                    # Debt exists but interest expense not separately reported
                    # (e.g. some companies net interest income/expense in "Other income").
                    # Use a conservative investment-grade default.
                    cost_of_debt = 0.04
                    logger.info(
                        f"Cost of debt set to default 4.00% "
                        f"(debt=${total_debt/1e9:.1f}B present but interest_expense not reported)"
                    )
                else:
                    cost_of_debt = 0.0
                    logger.info(f"Cost of debt set to 0.00% (no debt)")

            # 10. Market value of equity (for WACC calculation)
            market_value_equity = current_price * shares_outstanding

            # 11. Terminal growth rate - REQUIRED
            if terminal_growth_rate is None:
                return f"Error: terminal_growth_rate is REQUIRED for {ticker_clean}. Typically 2-3% (GDP growth + inflation)."

            # 12. Risk-free rate - REQUIRED
            if risk_free_rate is None:
                return f"Error: risk_free_rate is REQUIRED for {ticker_clean}. Search web for 'current 10 year treasury yield'."

            # 13. Market risk premium - REQUIRED
            if market_risk_premium is None:
                return f"Error: market_risk_premium is REQUIRED for {ticker_clean}. Use 5-5.5% for mega-cap quality stocks, 6-7% for others."

            # ================================================================
            # VALIDATION LAYER: Prevent invalid DCF calculations
            # ================================================================

            # Calculate WACC to validate against terminal growth rate
            cost_of_equity = risk_free_rate + final_beta * market_risk_premium
            total_value = market_value_equity + total_debt
            if total_value > 0:
                equity_weight = market_value_equity / total_value
                debt_weight = total_debt / total_value
                calculated_wacc = (equity_weight * cost_of_equity) + (debt_weight * cost_of_debt * (1 - tax_rate))
            else:
                equity_weight = 1.0
                debt_weight = 0.0
                calculated_wacc = cost_of_equity

            # CRITICAL: WACC must exceed terminal growth rate (Gordon Growth Model constraint)
            if calculated_wacc <= terminal_growth_rate:
                return f"""Error: Invalid DCF parameters for {ticker_clean}.

WACC ({calculated_wacc:.2%}) must be greater than terminal growth rate ({terminal_growth_rate:.2%}).

Current WACC calculation:
- Risk-free rate: {risk_free_rate:.2%}
- Beta: {final_beta:.2f}
- Market risk premium: {market_risk_premium:.2%}
- Cost of equity: {cost_of_equity:.2%}
- Calculated WACC: {calculated_wacc:.2%}

To fix: Lower terminal growth rate or increase market risk premium."""

            # WARNINGS: Log but allow continuation
            warnings = []
            if near_term_growth_rate > 0.50:
                warnings.append(f"Very high near-term growth: {near_term_growth_rate:.1%}. Verify this reflects analyst consensus.")
            if ebit_margin <= 0:
                warnings.append(f"Negative EBIT margin: {ebit_margin:.1%}. Company unprofitable - DCF may be unreliable.")
            if final_beta < 0.5 or final_beta > 2.5:
                warnings.append(f"Unusual beta: {final_beta:.2f}. Verify this is correct.")

            if warnings:
                for warning in warnings:
                    logger.warning(f"{ticker_clean}: {warning}")

            # Create assumptions using the new forward-looking structure
            assumptions = DCFAssumptions(
                # Growth assumptions (forward-looking)
                near_term_growth_rate=near_term_growth_rate,
                long_term_growth_rate=long_term_growth_rate,
                terminal_growth_rate=terminal_growth_rate,
                # Operating assumptions
                ebit_margin=ebit_margin,
                tax_rate=tax_rate,
                # Capital intensity (for UFCF calculation)
                capex_to_revenue=capex_to_revenue,
                depreciation_to_revenue=depreciation_to_revenue,
                nwc_to_revenue=nwc_to_revenue,
                # Discount rate components
                risk_free_rate=risk_free_rate,
                market_risk_premium=market_risk_premium,
                beta=final_beta,
                cost_of_debt=cost_of_debt,
                # Projection parameters
                projection_years=projection_years,
            )

            # ================================================================
            # AUTO-SELECT LEVERED vs UNLEVERED DCF based on capital structure
            # ================================================================
            # Use Levered DCF (FCFE method) for highly leveraged companies
            # where debt significantly impacts equity value

            LEVERAGE_THRESHOLD = 1.0  # D/E ratio threshold

            debt_to_equity = total_debt / market_value_equity if market_value_equity > 0 else 0
            use_levered_dcf = debt_to_equity > LEVERAGE_THRESHOLD

            if use_levered_dcf:
                logger.info(
                    f"{ticker_clean}: D/E ratio {debt_to_equity:.2f} > {LEVERAGE_THRESHOLD}. "
                    f"Using Levered DCF (FCFE method, discount at Cost of Equity)."
                )

            # Perform DCF with scenarios
            calculator = DCFCalculator()

            if use_levered_dcf:
                # Get interest expense for FCFE calculation
                interest_expense = metrics.get('latest_interest_expense', 0)

                results = calculator.analyze_with_levered_scenarios(
                    ticker=ticker_clean,
                    current_revenue=current_revenue,
                    current_price=current_price,
                    shares_outstanding=shares_outstanding,
                    total_debt=total_debt,
                    cash=cash,
                    interest_expense=interest_expense,
                    base_assumptions=assumptions
                )

                # Add levered DCF methodology note to output
                methodology_note = f"""
================================================================================
METHODOLOGY: LEVERED DCF (FCFE Method)
================================================================================
D/E Ratio: {debt_to_equity:.2f} (> {LEVERAGE_THRESHOLD} threshold)

Why Levered DCF?
- High leverage means debt significantly impacts equity value
- FCFE (Free Cash Flow to Equity) accounts for debt service
- Discounted at Cost of Equity ({cost_of_equity:.2%}), not WACC

FCFE = UFCF - Interest(1-T) + Net Borrowing
================================================================================
"""
            else:
                results = calculator.analyze_with_scenarios(
                    ticker=ticker_clean,
                    current_revenue=current_revenue,
                    current_price=current_price,
                    shares_outstanding=shares_outstanding,
                    total_debt=total_debt,
                    cash=cash,
                    base_assumptions=assumptions
                )
                methodology_note = f"""
================================================================================
METHODOLOGY: UNLEVERED DCF (UFCF Method)
================================================================================
D/E Ratio: {debt_to_equity:.2f} (< {LEVERAGE_THRESHOLD} threshold)

UFCF = NOPAT + D&A - CapEx - ΔNWC
Discounted at WACC ({calculated_wacc:.2%})
================================================================================
"""

            # Format results
            analysis = methodology_note + calculator.format_dcf_analysis(results)

            return analysis

        except Exception as e:
            logger.error(f"Error performing DCF analysis: {e}")
            ticker_clean = ticker.split(',')[0].split('\n')[0].strip().upper()
            return f"Error performing DCF analysis for {ticker_clean}: {str(e)}"

    async def _arun(
        self,
        ticker: str,
        near_term_growth_rate: Optional[float] = None,
        long_term_growth_rate: Optional[float] = None,
        terminal_growth_rate: Optional[float] = None,
        ebit_margin: Optional[float] = None,
        tax_rate: Optional[float] = None,
        capex_to_revenue: Optional[float] = None,
        depreciation_to_revenue: Optional[float] = None,
        nwc_to_revenue: Optional[float] = None,
        beta: Optional[float] = None,
        risk_free_rate: Optional[float] = None,
        market_risk_premium: Optional[float] = None,
        cost_of_debt: Optional[float] = None,
        projection_years: int = 5,
        current_price: Optional[float] = None,
        shares_outstanding: Optional[float] = None,
    ) -> str:
        """Async version"""
        return self._run(
            ticker,
            near_term_growth_rate,
            long_term_growth_rate,
            terminal_growth_rate,
            ebit_margin,
            tax_rate,
            capex_to_revenue,
            depreciation_to_revenue,
            nwc_to_revenue,
            beta,
            risk_free_rate,
            market_risk_premium,
            cost_of_debt,
            projection_years,
            current_price,
            shares_outstanding,
        )


class GetMarketParametersTool(BaseTool):
    """Tool to fetch DCF market parameters via FRED API and Tavily search"""
    name: str = "get_market_parameters"
    description: str = """Fetch current market parameters required for DCF valuation.

    Returns validated, numeric values for:
    - Beta coefficient for the stock
    - Current 10-year Treasury yield (risk-free rate)
    - Analyst consensus revenue growth rate (near-term, Years 1-2)
    - Industry average growth rate (long-term fade target, Years 3-5)

    Use this tool INSTEAD of search_web for DCF assumptions. It uses FRED API for
    Treasury yields and Tavily search for other parameters, with numeric validation.

    After calling this tool, pass the returned values directly to perform_dcf_analysis."""
    args_schema: Type[BaseModel] = MarketParametersInput

    def _query_tavily_for_number(self, query: str, data_type: str) -> Optional[float]:
        """Make a focused Tavily search query and parse numeric response with validation"""
        try:
            tavily = get_tavily_client()
            result = tavily.search(
                query=query,
                topic="finance",
                search_depth="advanced",
                max_results=3,
                include_answer="advanced",
            )

            answer = result.get("answer", "")
            if not answer:
                logger.warning(f"No Tavily answer for {data_type} query")
                return None

            logger.info(f"Tavily answer for {data_type}: {answer[:200]}")

            # Extract numeric value using context-aware parsing.
            # IMPORTANT: Don't blindly take numbers[0] — it's often a year
            # or maturity period (e.g., "10" from "10-year Treasury").

            # Strategy 1: For percentage data, find numbers directly adjacent to %
            if '%' in answer or 'percent' in answer.lower():
                pct_matches = re.findall(r'(\d+\.?\d*)\s*(?:%|percent)', answer, re.IGNORECASE)
                for pct_str in pct_matches:
                    value = float(pct_str) / 100
                    validated = self._validate_value(value, data_type)
                    if validated is not None:
                        return validated
                # If no valid percentage found, fall through to general parsing

            # Strategy 2: For beta, find numbers after the keyword "beta"
            if data_type == 'beta':
                beta_match = re.search(r'beta\s*(?:of|is|:|\s)\s*([-+]?\d*\.?\d+)', answer, re.IGNORECASE)
                if beta_match:
                    value = float(beta_match.group(1))
                    validated = self._validate_value(value, data_type)
                    if validated is not None:
                        return validated

            # Strategy 3: General fallback — try all numbers, pick first valid one
            numbers = re.findall(r'[-+]?\d*\.?\d+', answer)
            for num_str in numbers:
                value = float(num_str)

                # Skip values that look like years (2020-2030)
                if 1900 <= value <= 2100:
                    continue

                # Auto-convert if value looks like a percentage (> 1 for rates)
                if data_type in ['risk_free_rate', 'growth_rate', 'industry_growth']:
                    if value > 1:
                        value = value / 100
                        logger.info(f"Auto-converted {data_type} from {value*100}% to {value}")

                validated = self._validate_value(value, data_type)
                if validated is not None:
                    return validated

            logger.warning(f"Could not parse numeric value from Tavily answer: {answer[:100]}")
            return None

        except Exception as e:
            logger.error(f"Error querying Tavily for {data_type}: {e}")
            return None

    def _validate_value(self, value: Optional[float], data_type: str) -> Optional[float]:
        """Validate value is within reasonable bounds for the data type"""
        if value is None:
            return None

        bounds = {
            'beta': (0.0, 5.0),
            'risk_free_rate': (0.0, 0.15),  # 0-15%
            'growth_rate': (-0.50, 1.00),   # -50% to +100%
            'industry_growth': (-0.20, 0.50)  # -20% to +50%
        }

        min_val, max_val = bounds.get(data_type, (-float('inf'), float('inf')))

        if value < min_val or value > max_val:
            logger.warning(f"{data_type} value {value} out of bounds [{min_val}, {max_val}]")
            return None

        return value

    def _run(self, ticker: str, company_name: str = "", industry: str = "") -> str:
        """Fetch market parameters via FRED API and Tavily search"""
        try:
            ticker_clean = ticker.upper().strip()

            # Get company name if not provided
            if not company_name:
                fetcher = FinancialDataFetcher()
                info = fetcher.get_stock_info(ticker_clean)
                company_name = info.get('company_name', ticker_clean) if info else ticker_clean
                industry = info.get('industry', industry) if info else industry

            results = {
                'ticker': ticker_clean,
                'company_name': company_name,
                'industry': industry,
                'beta': None,
                'risk_free_rate': None,
                'near_term_growth_rate': None,
                'industry_growth_rate': None,
                'sources': [],
                'warnings': []
            }

            # 1. Beta: Try Financial Datasets API first, then Tavily search fallback
            # Note: Financial Datasets API returns beta=1.0 as default (not real data),
            # so we only trust non-default values from it
            fetcher = FinancialDataFetcher()
            metrics = fetcher.get_key_metrics(ticker_clean)
            api_beta = metrics.get('beta') if metrics else None
            if api_beta and api_beta != 1.0:
                results['beta'] = round(api_beta, 2)
                results['sources'].append(f"Beta: Financial Datasets API")
            else:
                beta_query = f"What is the current beta coefficient for {company_name} ({ticker_clean}) stock?"
                beta = self._query_tavily_for_number(beta_query, 'beta')
                beta = self._validate_value(beta, 'beta')
                if beta is not None:
                    results['beta'] = round(beta, 2)
                    results['sources'].append(f"Beta: Tavily web search")
                else:
                    results['warnings'].append("Beta: Could not retrieve. Using market average 1.0 as fallback.")
                    results['beta'] = 1.0

            # 2. Risk-Free Rate: FRED API first, then Tavily fallback
            fred = get_fred_client()
            risk_free_rate = fred.get_treasury_yield("DGS10")
            if risk_free_rate is not None:
                risk_free_rate = self._validate_value(risk_free_rate, 'risk_free_rate')
                if risk_free_rate is not None:
                    results['risk_free_rate'] = round(risk_free_rate, 4)
                    results['sources'].append(f"Risk-free rate: FRED API (DGS10 10Y Treasury)")
            if results['risk_free_rate'] is None:
                # Tavily fallback
                rfr_query = "current 10-year US Treasury yield percentage"
                rfr = self._query_tavily_for_number(rfr_query, 'risk_free_rate')
                rfr = self._validate_value(rfr, 'risk_free_rate')
                if rfr is not None:
                    results['risk_free_rate'] = round(rfr, 4)
                    results['sources'].append(f"Risk-free rate: Tavily web search (10Y Treasury)")
                else:
                    results['warnings'].append("Risk-free rate: Could not retrieve. Using 4.5% as typical current value.")
                    results['risk_free_rate'] = 0.045

            # 3. Analyst Consensus Growth Rate (Near-term, Years 1-2)
            growth_query = f"{company_name} ({ticker_clean}) analyst consensus revenue growth rate forecast next 1-2 years"
            near_term_growth = self._query_tavily_for_number(growth_query, 'growth_rate')
            near_term_growth = self._validate_value(near_term_growth, 'growth_rate')
            if near_term_growth is not None:
                results['near_term_growth_rate'] = round(near_term_growth, 3)
                results['sources'].append(f"Near-term growth: Analyst consensus via Tavily")
            else:
                results['warnings'].append("Near-term growth: Could not retrieve analyst consensus. You must search manually.")

            # 4. Industry Growth Rate (Long-term fade target, Years 3-5)
            industry_name = industry if industry else "the company's industry"
            industry_query = f"{industry_name} industry average annual growth rate"
            industry_growth = self._query_tavily_for_number(industry_query, 'industry_growth')
            industry_growth = self._validate_value(industry_growth, 'industry_growth')
            if industry_growth is not None:
                results['industry_growth_rate'] = round(industry_growth, 3)
                results['sources'].append(f"Industry growth: Tavily web search for {industry_name}")
            else:
                if results['near_term_growth_rate'] is not None:
                    results['industry_growth_rate'] = max(results['near_term_growth_rate'] * 0.5, 0.05)
                    results['sources'].append(f"Industry growth: Estimated as 50% of near-term growth (min 5%)")
                else:
                    results['industry_growth_rate'] = 0.05
                    results['warnings'].append("Industry growth: Using default 5%")

            # Format output — clean markdown (no ASCII art)
            output = []
            output.append(f"### Market Parameters: {company_name} ({ticker_clean})")
            output.append(f"**Industry:** {industry}")
            output.append("")
            output.append("#### DCF Assumption Values")
            output.append("")
            output.append("| Parameter | Value | Source |")
            output.append("|-----------|-------|--------|")
            output.append(f"| Beta | {results['beta']} | {next((s for s in results['sources'] if 'Beta' in s), 'N/A')} |")
            rfr = results['risk_free_rate']
            output.append(f"| Risk-Free Rate | {rfr} ({rfr*100:.2f}%) | {next((s for s in results['sources'] if 'Risk-free' in s), 'N/A')} |")
            ntg = results['near_term_growth_rate']
            output.append(f"| Near-Term Growth Rate (Yr 1-2) | {ntg} ({ntg*100:.1f}%) | Analyst consensus |" if ntg else "| Near-Term Growth Rate (Yr 1-2) | NOT FOUND — search manually | — |")
            ig = results['industry_growth_rate']
            output.append(f"| Industry Growth Rate (Yr 3-5) | {ig} ({ig*100:.1f}%) | Industry avg |" if ig else "| Industry Growth Rate (Yr 3-5) | NOT FOUND | — |")
            output.append(f"| Terminal Growth Rate | 0.025 (2.5%) | GDP + inflation assumption |")
            output.append(f"| Market Risk Premium | 0.055 (5.5%) | Quality mega-cap default |")
            output.append("")

            if results['warnings']:
                output.append("**Warnings:**")
                for warning in results['warnings']:
                    output.append(f"- ⚠ {warning}")
                output.append("")

            output.append(f"```json")
            output.append(f'{{')
            output.append(f'    "ticker": "{ticker_clean}",')
            output.append(f'    "beta": {results["beta"]},')
            output.append(f'    "risk_free_rate": {results["risk_free_rate"]},')
            output.append(f'    "near_term_growth_rate": {results["near_term_growth_rate"] if results["near_term_growth_rate"] else "REQUIRED"},')
            output.append(f'    "long_term_growth_rate": {results["industry_growth_rate"]},')
            output.append(f'    "terminal_growth_rate": 0.025,')
            output.append(f'    "market_risk_premium": 0.055')
            output.append(f'}}')
            output.append(f"```")

            return "\n".join(output)

        except Exception as e:
            logger.error(f"Error fetching market parameters for {ticker}: {e}")
            return f"Error fetching market parameters for {ticker}: {str(e)}"

    async def _arun(self, ticker: str, company_name: str = "", industry: str = "") -> str:
        """Async version"""
        return self._run(ticker, company_name, industry)


class SearchWebTool(BaseTool):
    """Tool to search the web using Tavily for current financial information"""
    name: str = "search_web"
    description: str = """Search the web for current financial information, analyst estimates, beta values, industry trends, and market data.
    Use this tool to find:
    - Current beta coefficients from financial websites
    - Analyst consensus on revenue/earnings growth rates
    - Industry-specific WACC or discount rate assumptions
    - Recent company news, earnings reports, or guidance
    - Competitive analysis and market conditions
    - Current risk-free rates and market risk premiums

    This helps make more accurate DCF assumptions based on current market data."""
    args_schema: Type[BaseModel] = WebSearchInput

    def _run(self, query: str) -> str:
        """Search the web using Tavily with retry logic"""
        try:
            tavily = get_tavily_client()
            result = tavily.search_text(
                query=query,
                topic="finance",
                search_depth="advanced",
                max_results=5,
                include_answer="advanced",
            )
            return f"Web Search Results:\n\n{result}"

        except Exception as e:
            logger.error(f"Error searching web: {e}")
            return f"Error searching web: {str(e)}"

    async def _arun(self, query: str) -> str:
        """Async version"""
        return self._run(query)


class GetDCFComparisonTool(BaseTool):
    """Tool to compare your DCF valuation with FMP's DCF as cross-validation"""
    name: str = "get_dcf_comparison"
    description: str = """Compare your calculated DCF valuation with Financial Modeling Prep's DCF valuation.

    Use this tool AFTER performing your DCF analysis to:
    1. Validate your valuation against an independent source
    2. See FMP's standard and levered DCF values
    3. Identify significant divergence that may warrant investigation

    Returns:
    - FMP Standard DCF (unlevered)
    - FMP Levered DCF (post-debt, FCFE-based)
    - Divergence percentage if you provide your calculated value

    Note: FMP uses undocumented methodology. Your UFCF-based DCF is more rigorous,
    but FMP provides useful cross-validation."""
    args_schema: Type[BaseModel] = DCFComparisonInput

    def _run(self, ticker: str) -> str:
        """Fetch FMP DCF values for comparison"""
        try:
            ticker_clean = ticker.upper().strip()
            fetcher = FinancialDataFetcher()

            # Check if FMP API is available
            if not fetcher.fmp_api_key:
                return f"""FMP DCF Comparison unavailable - FMP_API_KEY not configured.

To enable FMP comparison, add FMP_API_KEY to your .env file.
Your custom UFCF-based DCF is still the primary valuation method."""

            # Fetch FMP DCF values
            fmp_dcf = fetcher.get_fmp_dcf(ticker_clean)
            fmp_levered_dcf = fetcher.get_fmp_levered_dcf(ticker_clean)

            # Get current stock info for context
            info = fetcher.get_stock_info(ticker_clean)
            current_price = info.get('current_price', 0) if info else 0

            # Build comparison output
            output = []
            output.append("=" * 70)
            output.append(f"FMP DCF COMPARISON FOR {ticker_clean}")
            output.append("=" * 70)
            output.append("")

            output.append(f"Current Stock Price: ${current_price:.2f}")
            output.append("")

            # Standard DCF
            if fmp_dcf.get('dcf_value'):
                dcf_val = fmp_dcf['dcf_value']
                dcf_upside = ((dcf_val - current_price) / current_price * 100) if current_price > 0 else 0
                output.append(f"FMP Standard DCF:     ${dcf_val:.2f} per share")
                output.append(f"  Upside vs Price:    {dcf_upside:+.1f}%")
                output.append(f"  Date:               {fmp_dcf.get('date', 'N/A')}")
            else:
                output.append(f"FMP Standard DCF:     Not available")
                if 'error' in fmp_dcf:
                    output.append(f"  Error: {fmp_dcf['error']}")

            output.append("")

            # Levered DCF
            if fmp_levered_dcf.get('levered_dcf_value'):
                levered_val = fmp_levered_dcf['levered_dcf_value']
                levered_upside = ((levered_val - current_price) / current_price * 100) if current_price > 0 else 0
                output.append(f"FMP Levered DCF:      ${levered_val:.2f} per share (post-debt)")
                output.append(f"  Upside vs Price:    {levered_upside:+.1f}%")
                output.append(f"  Date:               {fmp_levered_dcf.get('date', 'N/A')}")
            else:
                output.append(f"FMP Levered DCF:      Not available")
                if 'error' in fmp_levered_dcf:
                    output.append(f"  Error: {fmp_levered_dcf['error']}")

            output.append("")
            output.append("-" * 70)
            output.append("METHODOLOGY NOTE:")
            output.append("")
            output.append("Your custom DCF uses explicit UFCF formula with forward-looking growth")
            output.append("projections. FMP uses undocumented methodology.")
            output.append("")
            output.append("Use FMP values as a sanity check, not as the primary valuation.")
            output.append("If divergence exceeds 20%, investigate assumption differences.")
            output.append("-" * 70)

            return "\n".join(output)

        except Exception as e:
            logger.error(f"Error fetching FMP DCF comparison: {e}")
            return f"Error fetching FMP DCF comparison for {ticker}: {str(e)}"

    async def _arun(self, ticker: str) -> str:
        """Async version"""
        return self._run(ticker)


class PerformMultiplesValuationTool(BaseTool):
    """Tool to perform multiples-based valuation as alternative/complement to DCF"""
    name: str = "perform_multiples_valuation"
    description: str = """Perform a multiples-based valuation using P/E, EV/EBITDA, P/S, and P/B ratios.

    WHEN TO USE MULTIPLES vs DCF:
    - Multiples are better for: mature companies, banks/financials, REITs, cyclical businesses
    - DCF is better for: high-growth companies, companies with predictable cash flows
    - Use BOTH for cross-validation (triangulation approach)

    METHODOLOGY:
    1. Calculates the company's current trading multiples
    2. Fetches peer/industry average multiples via web search
    3. Calculates implied fair values from each multiple
    4. Returns a weighted average fair value estimate

    MULTIPLES EXPLAINED:
    - P/E (Price/Earnings): Best for profitable, stable companies. Implied Value = EPS × Peer P/E
    - EV/EBITDA: Preferred for capital-intensive industries. Implied EV = EBITDA × Peer Multiple
    - P/S (Price/Sales): Useful for unprofitable companies. Implied Value = Revenue/Share × Peer P/S
    - P/B (Price/Book): Best for financials and asset-heavy firms. Implied Value = Book Value × Peer P/B

    INPUT:
    - ticker: Stock to value
    - peer_tickers (optional): Comma-separated peer tickers (e.g., 'MSFT,GOOGL,META')

    Use this tool alongside perform_dcf_analysis for a comprehensive valuation."""
    args_schema: Type[BaseModel] = MultiplesValuationInput

    def _fetch_peer_multiples_via_search(self, ticker: str, industry: str, peer_tickers: List[str]) -> Dict:
        """Fetch peer/industry multiples using Tavily search"""

        try:
            tavily = get_tavily_client()

            if peer_tickers:
                peer_list = ", ".join(peer_tickers)
                query = f"current P/E EV/EBITDA P/S P/B valuation multiples for {peer_list} peer average"
            else:
                query = f"average P/E EV/EBITDA P/S P/B valuation multiples for {industry} industry"

            result = tavily.search(
                query=query,
                topic="finance",
                search_depth="advanced",
                max_results=5,
                include_answer="advanced",
            )

            content = result.get("answer", "")
            if not content:
                return self._get_default_industry_multiples(industry)

            logger.info(f"Tavily multiples response: {content[:500]}...")

            # Parse the response to extract multiples
            multiples = {
                'peer_pe': None,
                'peer_ev_ebitda': None,
                'peer_ps': None,
                'peer_pb': None,
                'source': 'Tavily (peer/industry averages)',
                'raw_response': content[:1000]
            }

            # Extract P/E
            pe_patterns = [
                r'(?:P/E|PE|Price.to.Earnings)(?:\s*ratio)?[:\s]+(\d+\.?\d*)',
                r'(\d+\.?\d*)x?\s*(?:P/E|PE)',
            ]
            for pattern in pe_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    multiples['peer_pe'] = float(match.group(1))
                    break

            # Extract EV/EBITDA
            ev_patterns = [
                r'EV/EBITDA[:\s]+(\d+\.?\d*)',
                r'(\d+\.?\d*)x?\s*EV/EBITDA',
            ]
            for pattern in ev_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    multiples['peer_ev_ebitda'] = float(match.group(1))
                    break

            # Extract P/S
            ps_patterns = [
                r'(?:P/S|Price.to.Sales)[:\s]+(\d+\.?\d*)',
                r'(\d+\.?\d*)x?\s*(?:P/S|Price.to.Sales)',
            ]
            for pattern in ps_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    multiples['peer_ps'] = float(match.group(1))
                    break

            # Extract P/B
            pb_patterns = [
                r'(?:P/B|Price.to.Book)[:\s]+(\d+\.?\d*)',
                r'(\d+\.?\d*)x?\s*(?:P/B|Price.to.Book)',
            ]
            for pattern in pb_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    multiples['peer_pb'] = float(match.group(1))
                    break

            # Fill in defaults for any missing multiples
            defaults = self._get_default_industry_multiples(industry)
            for key in ['peer_pe', 'peer_ev_ebitda', 'peer_ps', 'peer_pb']:
                if multiples[key] is None:
                    multiples[key] = defaults[key]
                    multiples['source'] += f" (using default for {key})"

            return multiples

        except Exception as e:
            logger.error(f"Error fetching peer multiples: {e}")
            return self._get_default_industry_multiples(industry)

    def _get_default_industry_multiples(self, industry: str) -> Dict:
        """Get default multiples based on industry"""
        # Industry-specific defaults (approximate S&P 500 sector averages)
        industry_defaults = {
            'Technology': {'peer_pe': 25.0, 'peer_ev_ebitda': 15.0, 'peer_ps': 5.0, 'peer_pb': 6.0},
            'Software': {'peer_pe': 30.0, 'peer_ev_ebitda': 20.0, 'peer_ps': 8.0, 'peer_pb': 8.0},
            'Healthcare': {'peer_pe': 20.0, 'peer_ev_ebitda': 12.0, 'peer_ps': 3.0, 'peer_pb': 4.0},
            'Financial': {'peer_pe': 12.0, 'peer_ev_ebitda': 8.0, 'peer_ps': 2.5, 'peer_pb': 1.2},
            'Consumer': {'peer_pe': 18.0, 'peer_ev_ebitda': 10.0, 'peer_ps': 1.5, 'peer_pb': 3.0},
            'Industrial': {'peer_pe': 18.0, 'peer_ev_ebitda': 10.0, 'peer_ps': 1.5, 'peer_pb': 3.0},
            'Energy': {'peer_pe': 10.0, 'peer_ev_ebitda': 5.0, 'peer_ps': 1.0, 'peer_pb': 1.5},
            'Retail': {'peer_pe': 20.0, 'peer_ev_ebitda': 8.0, 'peer_ps': 0.8, 'peer_pb': 4.0},
            'Auto': {'peer_pe': 8.0, 'peer_ev_ebitda': 4.0, 'peer_ps': 0.5, 'peer_pb': 1.0},
            'default': {'peer_pe': 18.0, 'peer_ev_ebitda': 10.0, 'peer_ps': 2.0, 'peer_pb': 2.5},
        }

        # Try to match industry
        industry_lower = industry.lower() if industry else ''
        for key, values in industry_defaults.items():
            if key.lower() in industry_lower:
                return {**values, 'source': f'Default {key} industry averages'}

        return {**industry_defaults['default'], 'source': 'Default market averages'}

    def _run(self, ticker: str, peer_tickers: str = "") -> str:
        """Perform multiples-based valuation"""
        try:
            ticker_clean = ticker.upper().strip()

            # Parse peer tickers
            peers = [p.strip().upper() for p in peer_tickers.split(',') if p.strip()] if peer_tickers else []

            # Fetch company data
            fetcher = FinancialDataFetcher()
            info = fetcher.get_stock_info(ticker_clean)
            metrics = fetcher.get_key_metrics(ticker_clean)

            if not info or not metrics:
                return f"Error: Could not fetch data for {ticker_clean}"

            # Extract key values
            current_price = info.get('current_price', 0)
            market_cap = info.get('market_cap', 0)
            company_name = info.get('company_name', ticker_clean)
            industry = info.get('industry', 'Unknown')
            sector = info.get('sector', 'Unknown')

            shares_outstanding = metrics.get('shares_outstanding', 0)
            latest_revenue = metrics.get('latest_revenue', 0)
            latest_ebit = metrics.get('latest_ebit', 0)
            latest_net_income = metrics.get('latest_net_income', 0)
            total_debt = metrics.get('total_debt', 0)
            cash = metrics.get('cash_and_equivalents', 0)

            # Calculate EBITDA (EBIT + D&A) — can be positive even when EBIT is negative
            latest_da = metrics.get('latest_depreciation_amortization', 0)
            ebitda = latest_ebit + latest_da

            # Calculate Enterprise Value
            enterprise_value = market_cap + total_debt - cash

            # Validate we have enough data
            if current_price <= 0 or shares_outstanding <= 0:
                return f"Error: Insufficient data for {ticker_clean}. Missing price or shares outstanding."

            # Calculate company's current multiples
            eps = latest_net_income / shares_outstanding if shares_outstanding > 0 else 0
            revenue_per_share = latest_revenue / shares_outstanding if shares_outstanding > 0 else 0

            # Book value per share from actual shareholders equity
            shareholders_equity = metrics.get('shareholders_equity', 0)
            book_value_per_share = shareholders_equity / shares_outstanding if shareholders_equity > 0 and shares_outstanding > 0 else 0

            current_multiples = {
                'pe': current_price / eps if eps > 0 else None,
                'ev_ebitda': enterprise_value / ebitda if ebitda > 0 else None,
                'ps': current_price / revenue_per_share if revenue_per_share > 0 else None,
                'pb': current_price / book_value_per_share if book_value_per_share > 0 else None,
            }

            # Fetch peer/industry multiples
            peer_multiples = self._fetch_peer_multiples_via_search(ticker_clean, industry, peers)

            # Calculate implied fair values
            implied_values = {}
            weighted_sum = 0
            total_weight = 0

            # P/E based valuation (weight: 30% if profitable, 0% if not)
            if eps > 0 and peer_multiples.get('peer_pe'):
                implied_pe_value = eps * peer_multiples['peer_pe']
                implied_values['P/E'] = {
                    'implied_value': implied_pe_value,
                    'company_multiple': current_multiples['pe'],
                    'peer_multiple': peer_multiples['peer_pe'],
                    'weight': 0.30,
                    'upside': ((implied_pe_value - current_price) / current_price * 100) if current_price > 0 else 0
                }
                weighted_sum += implied_pe_value * 0.30
                total_weight += 0.30
            else:
                implied_values['P/E'] = {'error': 'Negative earnings - P/E not applicable', 'weight': 0}

            # EV/EBITDA based valuation (weight: 35% if positive EBITDA, 0% if not)
            if ebitda > 0 and peer_multiples.get('peer_ev_ebitda'):
                implied_ev = ebitda * peer_multiples['peer_ev_ebitda']
                implied_equity_value = implied_ev - total_debt + cash
                implied_ev_ebitda_value = implied_equity_value / shares_outstanding if shares_outstanding > 0 else 0
                implied_values['EV/EBITDA'] = {
                    'implied_value': implied_ev_ebitda_value,
                    'implied_ev': implied_ev,
                    'company_multiple': current_multiples['ev_ebitda'],
                    'peer_multiple': peer_multiples['peer_ev_ebitda'],
                    'weight': 0.35,
                    'upside': ((implied_ev_ebitda_value - current_price) / current_price * 100) if current_price > 0 else 0
                }
                weighted_sum += implied_ev_ebitda_value * 0.35
                total_weight += 0.35
            else:
                implied_values['EV/EBITDA'] = {'error': 'Negative EBITDA - EV/EBITDA not applicable', 'weight': 0}

            # P/S based valuation (weight: 25% - useful for unprofitable growth companies)
            if revenue_per_share > 0 and peer_multiples.get('peer_ps'):
                implied_ps_value = revenue_per_share * peer_multiples['peer_ps']
                implied_values['P/S'] = {
                    'implied_value': implied_ps_value,
                    'company_multiple': current_multiples['ps'],
                    'peer_multiple': peer_multiples['peer_ps'],
                    'weight': 0.25,
                    'upside': ((implied_ps_value - current_price) / current_price * 100) if current_price > 0 else 0
                }
                weighted_sum += implied_ps_value * 0.25
                total_weight += 0.25
            else:
                implied_values['P/S'] = {'error': 'No revenue data - P/S not applicable', 'weight': 0}

            # P/B based valuation (weight: 10% - more relevant for financials)
            if book_value_per_share > 0 and peer_multiples.get('peer_pb'):
                implied_pb_value = book_value_per_share * peer_multiples['peer_pb']
                implied_values['P/B'] = {
                    'implied_value': implied_pb_value,
                    'company_multiple': current_multiples['pb'],
                    'peer_multiple': peer_multiples['peer_pb'],
                    'weight': 0.10,
                    'upside': ((implied_pb_value - current_price) / current_price * 100) if current_price > 0 else 0
                }
                weighted_sum += implied_pb_value * 0.10
                total_weight += 0.10
            else:
                implied_values['P/B'] = {'error': 'No book value data - P/B not applicable', 'weight': 0}

            # Calculate weighted average fair value
            if total_weight > 0:
                weighted_avg_value = weighted_sum / total_weight
                overall_upside = ((weighted_avg_value - current_price) / current_price * 100) if current_price > 0 else 0
            else:
                weighted_avg_value = 0
                overall_upside = 0

            # Determine rating based on multiples
            if overall_upside > 15:
                rating = "BUY (Undervalued)"
            elif overall_upside < -15:
                rating = "SELL (Overvalued)"
            else:
                rating = "HOLD (Fairly Valued)"

            # Format output — clean markdown (no ASCII art)
            output = []
            output.append(f"### Multiples Valuation: {company_name} ({ticker_clean})")
            output.append("")
            output.append(f"**Sector:** {sector} | **Industry:** {industry} | "
                          f"**Current Price:** ${current_price:.2f} | "
                          f"**Market Cap:** ${market_cap/1e9:.2f}B | "
                          f"**EV:** ${enterprise_value/1e9:.2f}B")
            output.append("")

            # Investment summary
            output.append("#### Summary")
            output.append("")
            output.append(f"| Metric | Value |")
            output.append(f"|--------|-------|")
            output.append(f"| Implied Fair Value (Weighted Avg) | **${weighted_avg_value:.2f}** |")
            output.append(f"| Current Price | ${current_price:.2f} |")
            output.append(f"| Upside / Downside | **{overall_upside:+.1f}%** |")
            output.append(f"| Multiples-Based Rating | {rating} |")
            output.append("")

            # Multiples comparison table (markdown)
            output.append("#### Multiples Analysis")
            output.append("")
            output.append("| Multiple | Company | Peer Avg | Implied Value | Upside | Weight |")
            output.append("|---------|---------|----------|--------------|--------|--------|")

            for multiple_name, data in implied_values.items():
                if 'error' in data:
                    output.append(f"| {multiple_name} | N/A | N/A | N/A | N/A | 0% |")
                else:
                    company_mult = f"{data['company_multiple']:.1f}x" if data['company_multiple'] else 'N/A'
                    peer_mult = f"{data['peer_multiple']:.1f}x"
                    implied = f"${data['implied_value']:.2f}"
                    upside = f"{data['upside']:+.1f}%"
                    weight = f"{data['weight']*100:.0f}%"
                    output.append(f"| {multiple_name} | {company_mult} | {peer_mult} | {implied} | {upside} | {weight} |")

            output.append(f"| **Weighted Average** | | | **${weighted_avg_value:.2f}** | **{overall_upside:+.1f}%** | 100% |")
            output.append("")

            # Key financials
            output.append("#### Key Financials Used")
            output.append("")
            output.append("| Metric | Value |")
            output.append("|--------|-------|")
            output.append(f"| EPS (TTM) | ${eps:.2f} |")
            output.append(f"| Revenue (TTM) | ${latest_revenue/1e9:.2f}B |")
            output.append(f"| EBITDA (TTM) | ${ebitda/1e9:.2f}B |")
            output.append(f"| Total Debt | ${total_debt/1e9:.2f}B |")
            output.append(f"| Cash | ${cash/1e9:.2f}B |")
            output.append(f"| Shares Outstanding | {shares_outstanding/1e9:.2f}B |")
            output.append("")

            # Data source
            if peers:
                output.append(f"**Peer Companies:** {', '.join(peers)}")
            output.append(f"**Multiples Source:** {peer_multiples.get('source', 'Unknown')}")
            output.append("")
            output.append("**Methodology:** Weights — P/E (30%), EV/EBITDA (35%), P/S (25%), P/B (10%). "
                          "Implied values derived by applying peer-median multiples to company financials.")

            return "\n".join(output)

        except Exception as e:
            logger.error(f"Error performing multiples valuation: {e}")
            return f"Error performing multiples valuation for {ticker}: {str(e)}"

    async def _arun(self, ticker: str, peer_tickers: str = "") -> str:
        """Async version"""
        return self._run(ticker, peer_tickers)


class DCFReportInput(BaseModel):
    """Input for DCF report formatting tool - simplified with minimal required fields"""
    ticker: str = Field(description="Stock ticker symbol")
    # All other fields are optional with sensible defaults
    company_name: str = Field(default="", description="Company name (will be fetched if not provided)")
    sector: str = Field(default="", description="Company sector")
    industry: str = Field(default="", description="Company industry")
    current_price: float = Field(default=0, description="Current stock price")
    base_intrinsic_value: float = Field(default=0, description="Base case intrinsic value per share")
    bull_intrinsic_value: float = Field(default=0, description="Bull case intrinsic value per share")
    bear_intrinsic_value: float = Field(default=0, description="Bear case intrinsic value per share")
    base_upside: float = Field(default=0, description="Base case upside/downside percentage")
    bull_upside: float = Field(default=0, description="Bull case upside/downside percentage")
    bear_upside: float = Field(default=0, description="Bear case upside/downside percentage")
    rating: str = Field(default="HOLD", description="Investment rating (BUY, HOLD, or SELL)")
    conviction: str = Field(default="Medium", description="Conviction level (High, Medium, Low)")
    # Assumptions - all optional with defaults
    near_term_growth_rate: float = Field(default=0.05, description="Near-term growth rate (Years 1-2)")
    long_term_growth_rate: float = Field(default=0.04, description="Long-term growth rate (Years 3-5)")
    terminal_growth_rate: float = Field(default=0.025, description="Terminal growth rate")
    beta: float = Field(default=1.0, description="Beta coefficient")
    risk_free_rate: float = Field(default=0.045, description="Risk-free rate")
    market_risk_premium: float = Field(default=0.055, description="Market risk premium")
    wacc: float = Field(default=0.10, description="Weighted average cost of capital")
    ebit_margin: float = Field(default=0.15, description="EBIT margin")
    tax_rate: float = Field(default=0.21, description="Tax rate")
    # Financials - all optional
    market_cap: float = Field(default=0, description="Market capitalization")
    enterprise_value: float = Field(default=0, description="Enterprise value (from DCF)")
    equity_value: float = Field(default=0, description="Equity value (from DCF)")
    total_debt: float = Field(default=0, description="Total debt")
    cash: float = Field(default=0, description="Cash and equivalents")
    shares_outstanding: float = Field(default=0, description="Shares outstanding")
    # Analysis content - all optional
    growth_analysis: str = Field(default="", description="Growth analysis narrative")
    risk_analysis: str = Field(default="", description="Risk analysis narrative")
    investment_thesis: str = Field(default="", description="Investment thesis summary")
    company_overview: str = Field(default="", description="Company business overview")
    # Optional warnings
    warnings: str = Field(default="", description="Any warnings or caveats")


class FormatDCFReportTool(BaseTool):
    """Tool to format DCF results into a professional structured report"""
    name: str = "format_dcf_report"
    description: str = """Format DCF analysis results into a professional, institutional-grade report.

    Use this tool AFTER perform_dcf_analysis to generate the final output report.

    The report includes:
    - Executive summary with investment rating
    - Scenario analysis table (Bull/Base/Bear side-by-side)
    - DCF assumptions breakdown
    - Valuation waterfall
    - Growth and risk analysis
    - Investment thesis
    - Disclaimer

    Input: All DCF results, assumptions, and analysis narratives
    Output: Professionally formatted report matching institutional standards"""
    args_schema: Type[BaseModel] = DCFReportInput

    def _run(
        self,
        ticker: str,
        company_name: str = "",
        sector: str = "",
        industry: str = "",
        current_price: float = 0,
        base_intrinsic_value: float = 0,
        bull_intrinsic_value: float = 0,
        bear_intrinsic_value: float = 0,
        base_upside: float = 0,
        bull_upside: float = 0,
        bear_upside: float = 0,
        rating: str = "HOLD",
        conviction: str = "Medium",
        near_term_growth_rate: float = 0.05,
        long_term_growth_rate: float = 0.04,
        terminal_growth_rate: float = 0.025,
        beta: float = 1.0,
        risk_free_rate: float = 0.045,
        market_risk_premium: float = 0.055,
        wacc: float = 0.10,
        ebit_margin: float = 0.15,
        tax_rate: float = 0.21,
        market_cap: float = 0,
        enterprise_value: float = 0,
        equity_value: float = 0,
        total_debt: float = 0,
        cash: float = 0,
        shares_outstanding: float = 0,
        growth_analysis: str = "",
        risk_analysis: str = "",
        investment_thesis: str = "",
        company_overview: str = "",
        warnings: str = ""
    ) -> str:
        """Generate professionally formatted DCF report"""
        from datetime import datetime

        # Auto-fetch missing data if ticker is provided
        ticker_clean = ticker.upper().strip()
        if not company_name or current_price == 0:
            fetcher = FinancialDataFetcher()
            info = fetcher.get_stock_info(ticker_clean)
            if info:
                if not company_name:
                    company_name = info.get('company_name', ticker_clean)
                if not sector:
                    sector = info.get('sector', '')
                if not industry:
                    industry = info.get('industry', '')
                if current_price == 0:
                    current_price = info.get('current_price', 0)
                if market_cap == 0:
                    market_cap = info.get('market_cap', 0)

        # Calculate upside if values provided but upside not
        if base_intrinsic_value > 0 and current_price > 0 and base_upside == 0:
            base_upside = ((base_intrinsic_value - current_price) / current_price) * 100
        if bull_intrinsic_value > 0 and current_price > 0 and bull_upside == 0:
            bull_upside = ((bull_intrinsic_value - current_price) / current_price) * 100
        if bear_intrinsic_value > 0 and current_price > 0 and bear_upside == 0:
            bear_upside = ((bear_intrinsic_value - current_price) / current_price) * 100

        # Auto-determine rating based on base_upside if not explicitly set
        if rating == "HOLD" and base_upside != 0:
            if base_upside > 15:
                rating = "BUY"
            elif base_upside < -15:
                rating = "SELL"

        # Normalize values that might be passed as percentages instead of decimals
        # If values seem like percentages (> 1), convert to decimal
        if near_term_growth_rate > 1:
            near_term_growth_rate = near_term_growth_rate / 100
        if long_term_growth_rate > 1:
            long_term_growth_rate = long_term_growth_rate / 100
        if terminal_growth_rate > 1:
            terminal_growth_rate = terminal_growth_rate / 100
        if risk_free_rate > 1:
            risk_free_rate = risk_free_rate / 100
        if market_risk_premium > 1:
            market_risk_premium = market_risk_premium / 100
        if wacc > 1:
            wacc = wacc / 100
        if ebit_margin > 1:
            ebit_margin = ebit_margin / 100
        if tax_rate > 1:
            tax_rate = tax_rate / 100

        # Format large numbers
        def fmt_num(n, decimals=0):
            if abs(n) >= 1e12:
                return f"${n/1e12:,.{decimals}f}T"
            elif abs(n) >= 1e9:
                return f"${n/1e9:,.{decimals}f}B"
            elif abs(n) >= 1e6:
                return f"${n/1e6:,.{decimals}f}M"
            else:
                return f"${n:,.{decimals}f}"

        # Determine rating color/emoji for text display
        rating_display = {
            'BUY': '🟢 BUY',
            'HOLD': '🟡 HOLD',
            'SELL': '🔴 SELL'
        }.get(rating.upper(), rating)

        # Build report
        lines = []

        # Header
        lines.append("=" * 80)
        lines.append(f"{'DCF VALUATION REPORT':^80}")
        lines.append("=" * 80)
        lines.append("")
        lines.append(f"Company:         {company_name} ({ticker})")
        lines.append(f"Sector:          {sector}")
        lines.append(f"Industry:        {industry}")
        lines.append(f"Report Date:     {datetime.now().strftime('%B %d, %Y')}")
        lines.append("")

        # Investment Rating Summary
        lines.append("-" * 80)
        lines.append("INVESTMENT SUMMARY")
        lines.append("-" * 80)
        lines.append("")
        lines.append(f"  Rating:              {rating_display}")
        lines.append(f"  Conviction:          {conviction}")
        lines.append(f"  Current Price:       ${current_price:.2f}")
        lines.append(f"  Target Price (Base): ${base_intrinsic_value:.2f}")
        lines.append(f"  Upside/Downside:     {base_upside:+.1f}%")
        lines.append("")

        # Scenario Analysis Table
        lines.append("-" * 80)
        lines.append("SCENARIO ANALYSIS")
        lines.append("-" * 80)
        lines.append("")
        lines.append(f"{'Scenario':<15} {'Intrinsic Value':>18} {'vs Current Price':>18} {'Probability':>12}")
        lines.append("-" * 80)
        lines.append(f"{'Bull Case':<15} ${bull_intrinsic_value:>16,.2f} {bull_upside:>17.1f}% {'25%':>12}")
        lines.append(f"{'Base Case':<15} ${base_intrinsic_value:>16,.2f} {base_upside:>17.1f}% {'50%':>12}")
        lines.append(f"{'Bear Case':<15} ${bear_intrinsic_value:>16,.2f} {bear_upside:>17.1f}% {'25%':>12}")
        lines.append("-" * 80)

        # Probability-weighted value
        prob_weighted = bull_intrinsic_value * 0.25 + base_intrinsic_value * 0.50 + bear_intrinsic_value * 0.25
        prob_weighted_upside = ((prob_weighted - current_price) / current_price * 100) if current_price > 0 else 0
        lines.append(f"{'Prob-Weighted':<15} ${prob_weighted:>16,.2f} {prob_weighted_upside:>17.1f}%")
        lines.append("")

        # DCF Assumptions
        lines.append("-" * 80)
        lines.append("DCF ASSUMPTIONS")
        lines.append("-" * 80)
        lines.append("")
        lines.append("Growth Assumptions:")
        lines.append(f"  Near-Term Growth (Yr 1-2):    {near_term_growth_rate*100:.1f}%  (Analyst consensus)")
        lines.append(f"  Long-Term Growth (Yr 3-5):    {long_term_growth_rate*100:.1f}%  (Industry average fade)")
        lines.append(f"  Terminal Growth:              {terminal_growth_rate*100:.1f}%  (GDP + inflation)")
        lines.append("")
        lines.append("Discount Rate (WACC):")
        lines.append(f"  Risk-Free Rate:               {risk_free_rate*100:.2f}% (10Y Treasury)")
        lines.append(f"  Beta:                         {beta:.2f}")
        lines.append(f"  Market Risk Premium:          {market_risk_premium*100:.1f}%")
        lines.append(f"  WACC:                         {wacc*100:.2f}%")
        lines.append("")
        lines.append("Operating Assumptions:")
        lines.append(f"  EBIT Margin:                  {ebit_margin*100:.1f}%")
        lines.append(f"  Tax Rate:                     {tax_rate*100:.1f}%")
        lines.append("")

        # Valuation Waterfall (if data available)
        if enterprise_value > 0 and equity_value > 0:
            lines.append("-" * 80)
            lines.append("VALUATION WATERFALL (Base Case)")
            lines.append("-" * 80)
            lines.append("")
            lines.append(f"  Enterprise Value:           {fmt_num(enterprise_value, 1)}")
            lines.append(f"  Less: Total Debt:           ({fmt_num(total_debt, 1)})")
            lines.append(f"  Plus: Cash:                 {fmt_num(cash, 1)}")
            lines.append(f"  Equity Value:               {fmt_num(equity_value, 1)}")
            lines.append(f"  Shares Outstanding:         {shares_outstanding/1e9:.2f}B" if shares_outstanding > 0 else "  Shares Outstanding:         N/A")
            lines.append(f"  Intrinsic Value/Share:      ${base_intrinsic_value:.2f}")
            lines.append("")

        # Growth Analysis
        if growth_analysis:
            lines.append("-" * 80)
            lines.append("GROWTH ANALYSIS")
            lines.append("-" * 80)
            lines.append("")
            for line in growth_analysis.split('\n'):
                lines.append(f"  {line}")
            lines.append("")

        # Risk Analysis
        if risk_analysis:
            lines.append("-" * 80)
            lines.append("RISK ANALYSIS")
            lines.append("-" * 80)
            lines.append("")
            for line in risk_analysis.split('\n'):
                lines.append(f"  {line}")
            lines.append("")

        # Investment Thesis
        if investment_thesis:
            lines.append("-" * 80)
            lines.append("INVESTMENT THESIS")
            lines.append("-" * 80)
            lines.append("")
            for line in investment_thesis.split('\n'):
                lines.append(f"  {line}")
            lines.append("")

        # Company Overview
        if company_overview:
            lines.append("-" * 80)
            lines.append("COMPANY OVERVIEW")
            lines.append("-" * 80)
            lines.append("")
            for line in company_overview.split('\n'):
                lines.append(f"  {line}")
            lines.append("")

        # Warnings
        if warnings:
            lines.append("-" * 80)
            lines.append("WARNINGS & CAVEATS")
            lines.append("-" * 80)
            lines.append("")
            for line in warnings.split('\n'):
                if line.strip():
                    lines.append(f"  ⚠ {line}")
            lines.append("")

        # Disclaimer
        lines.append("-" * 80)
        lines.append("DISCLAIMER")
        lines.append("-" * 80)
        lines.append("")
        lines.append("  This report is generated by an AI-powered DCF analysis system.")
        lines.append("  The analysis is based on publicly available data and analyst estimates.")
        lines.append("  ")
        lines.append("  Key limitations:")
        lines.append("  - DCF valuations are highly sensitive to growth and discount rate assumptions")
        lines.append("  - Past performance does not guarantee future results")
        lines.append("  - This is not investment advice; consult a financial professional")
        lines.append("  ")
        lines.append("  Data sources: Financial Datasets API, FRED API, Tavily, FMP API")
        lines.append("")
        lines.append("=" * 80)
        lines.append(f"Generated by Finance DCF Agent | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 80)

        return "\n".join(lines)

    async def _arun(self, **kwargs) -> str:
        """Async version"""
        return self._run(**kwargs)


def get_dcf_tools():
    """Return list of all DCF analysis tools including context, market parameters, multiples, and report formatting"""
    from tools.context_tools import GetCompanyContextTool
    return [
        GetCompanyContextTool(),           # Rich context first - business model, news, catalysts
        GetStockInfoTool(),
        GetFinancialMetricsTool(),
        GetMarketParametersTool(),         # FRED + Tavily queries for DCF assumptions
        SearchWebTool(),                   # Keep for qualitative research (industry, news, etc.)
        PerformDCFAnalysisTool(),          # DCF valuation
        PerformMultiplesValuationTool(),   # NEW: Multiples-based valuation (P/E, EV/EBITDA, P/S, P/B)
        GetDCFComparisonTool(),            # FMP DCF cross-validation (use after performing your DCF)
        FormatDCFReportTool()              # Professional report formatting
    ]
