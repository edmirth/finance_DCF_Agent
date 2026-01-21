"""
LangChain Tools for DCF Analysis Agent
"""
from langchain.tools import BaseTool
from typing import Optional, Type
from pydantic import BaseModel, Field
from data.financial_data import FinancialDataFetcher
from calculators.dcf_calculator import DCFCalculator, DCFAssumptions
from tools.equity_analyst_tools import CompetitorAnalysisTool
import json
import logging
import os
from openai import OpenAI

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


# Tool Implementations
class GetStockInfoTool(BaseTool):
    """Tool to get basic stock information"""
    name: str = "get_stock_info"
    description: str = "Get basic information about a stock including company name, sector, industry, market cap, and current price. Use this first to understand the company."
    args_schema: Type[BaseModel] = StockInfoInput

    def _run(self, ticker: str) -> str:
        """Fetch stock information"""
        fetcher = FinancialDataFetcher()
        info = fetcher.get_stock_info(ticker.upper())

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
        metrics = fetcher.get_key_metrics(ticker.upper())

        if not metrics:
            return f"Error: Could not fetch financial metrics for ticker {ticker}"

        # Calculate historical growth rates
        revenue_growth = 0.0
        fcf_growth = 0.0

        if "historical_revenue" in metrics:
            revenue_growth = fetcher.calculate_historical_growth_rate(
                metrics["historical_revenue"]
            )

        if "historical_fcf" in metrics:
            fcf_growth = fetcher.calculate_historical_growth_rate(
                metrics["historical_fcf"]
            )

        # Calculate operating ratios
        ebit_margin = (metrics.get('latest_ebit', 0) / metrics.get('latest_revenue', 1)) if metrics.get('latest_revenue', 0) > 0 else 0
        capex_to_revenue = (metrics.get('latest_capex', 0) / metrics.get('latest_revenue', 1)) if metrics.get('latest_revenue', 0) > 0 else 0
        da_to_revenue = (metrics.get('latest_depreciation_amortization', 0) / metrics.get('latest_revenue', 1)) if metrics.get('latest_revenue', 0) > 0 else 0
        nwc_to_revenue = (metrics.get('net_working_capital', 0) / metrics.get('latest_revenue', 1)) if metrics.get('latest_revenue', 0) > 0 else 0
        cost_of_debt = (metrics.get('latest_interest_expense', 0) / metrics.get('total_debt', 1)) if metrics.get('total_debt', 0) > 0 else 0.05

        result = f"""
Financial Metrics for {ticker.upper()}:

Current Financials:
- Latest Revenue: ${metrics.get('latest_revenue', 0):,.0f}
- Latest EBIT (Operating Income): ${metrics.get('latest_ebit', 0):,.0f}
- Latest Free Cash Flow: ${metrics.get('latest_fcf', 0):,.0f}
- Latest CapEx: ${metrics.get('latest_capex', 0):,.0f}
- Latest D&A: ${metrics.get('latest_depreciation_amortization', 0):,.0f}

Balance Sheet:
- Total Debt: ${metrics.get('total_debt', 0):,.0f}
- Cash & Equivalents: ${metrics.get('cash_and_equivalents', 0):,.0f}
- Net Working Capital: ${metrics.get('net_working_capital', 0):,.0f}
- Shares Outstanding: {metrics.get('shares_outstanding', 0):,.0f}

Tax & Debt Metrics:
- Effective Tax Rate: {metrics.get('effective_tax_rate', 0.21) * 100:.1f}%
- Interest Expense: ${metrics.get('latest_interest_expense', 0):,.0f}
- Implied Cost of Debt: {cost_of_debt * 100:.2f}%
- Beta: {metrics.get('beta', 1.0):.2f}

Operating Ratios (for DCF assumptions):
- EBIT Margin: {ebit_margin * 100:.1f}%
- CapEx/Revenue: {capex_to_revenue * 100:.1f}%
- D&A/Revenue: {da_to_revenue * 100:.1f}%
- NWC/Revenue: {nwc_to_revenue * 100:.1f}%
"""

        # Add historical financials section if data is available
        historical_section = "\nHistorical Financials (Last 5 Years, Most Recent First):\n"
        has_historical_data = False

        if metrics.get('historical_revenue'):
            has_historical_data = True
            revenue_values = metrics['historical_revenue'][:5]
            revenue_str = " → ".join([f"${r/1e9:.2f}B" for r in revenue_values])
            historical_section += f"- Revenue: {revenue_str}\n"

        if metrics.get('historical_net_income'):
            has_historical_data = True
            ni_values = metrics['historical_net_income'][:5]
            ni_str = " → ".join([f"${ni/1e9:.2f}B" if ni >= 0 else f"-${abs(ni)/1e9:.2f}B" for ni in ni_values])
            historical_section += f"- Net Income: {ni_str}\n"

        if metrics.get('historical_fcf'):
            has_historical_data = True
            fcf_values = metrics['historical_fcf'][:5]
            fcf_str = " → ".join([f"${fcf/1e9:.2f}B" if fcf >= 0 else f"-${abs(fcf)/1e9:.2f}B" for fcf in fcf_values])
            historical_section += f"- Free Cash Flow: {fcf_str}\n"

        if has_historical_data:
            result += historical_section

        result += f"""
Historical Growth Rates:
- Revenue CAGR: {revenue_growth * 100:.2f}%
- FCF CAGR: {fcf_growth * 100:.2f}%

These metrics should be used as inputs for DCF analysis assumptions.
"""
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
        projection_years: int = 5
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

            # Extract required values
            current_revenue = metrics.get('latest_revenue', 0)
            current_price = info.get('current_price', 0)
            shares_outstanding = metrics.get('shares_outstanding', 0)
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
                else:
                    # No debt or no interest - cost of debt is 0
                    cost_of_debt = 0.0
                    logger.info(f"Cost of debt set to 0.00% (no debt or interest)")

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
        projection_years: int = 5
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
            projection_years
        )


class GetMarketParametersTool(BaseTool):
    """Tool to fetch DCF market parameters via focused Perplexity queries"""
    name: str = "get_market_parameters"
    description: str = """Fetch current market parameters required for DCF valuation via focused Perplexity queries.

    Returns validated, numeric values for:
    - Beta coefficient for the stock
    - Current 10-year Treasury yield (risk-free rate)
    - Analyst consensus revenue growth rate (near-term, Years 1-2)
    - Industry average growth rate (long-term fade target, Years 3-5)

    Use this tool INSTEAD of search_web for DCF assumptions. It makes focused queries
    and validates the responses to ensure reliable numeric values.

    After calling this tool, pass the returned values directly to perform_dcf_analysis."""
    args_schema: Type[BaseModel] = MarketParametersInput

    def _query_perplexity(self, client, query: str, data_type: str) -> Optional[float]:
        """Make a focused query and parse numeric response with validation"""
        import re

        try:
            response = client.chat.completions.create(
                model="sonar-pro",
                messages=[
                    {
                        "role": "system",
                        "content": f"You are a financial data assistant. Return ONLY the numeric value for {data_type}. "
                                   "No explanations, no text, just the number. "
                                   "For percentages, return as decimal (e.g., 0.045 for 4.5%). "
                                   "For beta, return just the number (e.g., 1.25)."
                    },
                    {"role": "user", "content": query}
                ],
            )

            if not response.choices or len(response.choices) == 0:
                logger.warning(f"No response for {data_type} query")
                return None

            content = response.choices[0].message.content.strip()
            logger.info(f"Perplexity response for {data_type}: {content}")

            # Extract numeric value from response
            # Handle percentage formats (e.g., "4.5%", "4.5 percent")
            if '%' in content or 'percent' in content.lower():
                # Extract number and convert to decimal
                numbers = re.findall(r'[-+]?\d*\.?\d+', content)
                if numbers:
                    value = float(numbers[0]) / 100  # Convert percentage to decimal
                    return value

            # Handle decimal format (e.g., "0.045")
            numbers = re.findall(r'[-+]?\d*\.?\d+', content)
            if numbers:
                value = float(numbers[0])

                # Auto-convert if value looks like a percentage (> 1 for rates, > 5 for growth)
                if data_type in ['risk_free_rate', 'growth_rate', 'industry_growth']:
                    if value > 1:  # Likely a percentage that wasn't converted
                        value = value / 100
                        logger.info(f"Auto-converted {data_type} from {value*100}% to {value}")

                return value

            logger.warning(f"Could not parse numeric value from: {content}")
            return None

        except Exception as e:
            logger.error(f"Error querying Perplexity for {data_type}: {e}")
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
        """Fetch market parameters via focused Perplexity queries"""
        try:
            ticker_clean = ticker.upper().strip()

            api_key = os.getenv("PERPLEXITY_API_KEY")
            if not api_key:
                return """Error: PERPLEXITY_API_KEY not found in environment variables.

Please add it to your .env file to enable focused market parameter queries.
Without this, you'll need to manually search for beta, risk-free rate, and growth estimates."""

            client = OpenAI(api_key=api_key, base_url="https://api.perplexity.ai")

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

            # 1. Query for Beta
            beta_query = f"What is the current beta coefficient for {company_name} ({ticker_clean}) stock? Return only the number."
            beta = self._query_perplexity(client, beta_query, 'beta')
            beta = self._validate_value(beta, 'beta')
            if beta is not None:
                results['beta'] = round(beta, 2)
                results['sources'].append(f"Beta: Perplexity web search")
            else:
                # Fallback to financial data
                fetcher = FinancialDataFetcher()
                metrics = fetcher.get_key_metrics(ticker_clean)
                if metrics and metrics.get('beta'):
                    results['beta'] = round(metrics['beta'], 2)
                    results['sources'].append(f"Beta: Financial Datasets API")
                else:
                    results['warnings'].append("Beta: Could not retrieve. Using market average 1.0 as fallback.")
                    results['beta'] = 1.0

            # 2. Query for Risk-Free Rate (10-year Treasury yield)
            rfr_query = "What is the current 10-year US Treasury yield? Return only the number as a decimal (e.g., 0.045 for 4.5%)."
            risk_free_rate = self._query_perplexity(client, rfr_query, 'risk_free_rate')
            risk_free_rate = self._validate_value(risk_free_rate, 'risk_free_rate')
            if risk_free_rate is not None:
                results['risk_free_rate'] = round(risk_free_rate, 4)
                results['sources'].append(f"Risk-free rate: Perplexity web search (10Y Treasury)")
            else:
                results['warnings'].append("Risk-free rate: Could not retrieve. Using 4.5% as typical current value.")
                results['risk_free_rate'] = 0.045

            # 3. Query for Analyst Consensus Growth Rate (Near-term, Years 1-2)
            growth_query = f"What is the analyst consensus revenue growth rate forecast for {company_name} ({ticker_clean}) for the next 1-2 years (2025-2026)? Return only the number as a decimal (e.g., 0.10 for 10%)."
            near_term_growth = self._query_perplexity(client, growth_query, 'growth_rate')
            near_term_growth = self._validate_value(near_term_growth, 'growth_rate')
            if near_term_growth is not None:
                results['near_term_growth_rate'] = round(near_term_growth, 3)
                results['sources'].append(f"Near-term growth: Analyst consensus via Perplexity")
            else:
                results['warnings'].append("Near-term growth: Could not retrieve analyst consensus. You must search manually.")

            # 4. Query for Industry Growth Rate (Long-term fade target, Years 3-5)
            industry_name = industry if industry else "the company's industry"
            industry_query = f"What is the average annual growth rate for the {industry_name} industry? Return only the number as a decimal (e.g., 0.08 for 8%)."
            industry_growth = self._query_perplexity(client, industry_query, 'industry_growth')
            industry_growth = self._validate_value(industry_growth, 'industry_growth')
            if industry_growth is not None:
                results['industry_growth_rate'] = round(industry_growth, 3)
                results['sources'].append(f"Industry growth: Perplexity web search for {industry_name}")
            else:
                # Default to reasonable industry growth rate
                if results['near_term_growth_rate'] is not None:
                    # Use 50% of near-term, minimum 5%
                    results['industry_growth_rate'] = max(results['near_term_growth_rate'] * 0.5, 0.05)
                    results['sources'].append(f"Industry growth: Estimated as 50% of near-term growth (min 5%)")
                else:
                    results['industry_growth_rate'] = 0.05
                    results['warnings'].append("Industry growth: Using default 5%")

            # Format output
            output = []
            output.append("=" * 70)
            output.append(f"MARKET PARAMETERS FOR {ticker_clean}")
            output.append("=" * 70)
            output.append("")
            output.append(f"Company: {company_name}")
            output.append(f"Industry: {industry}")
            output.append("")
            output.append("-" * 70)
            output.append("DCF ASSUMPTION VALUES (Ready for perform_dcf_analysis):")
            output.append("-" * 70)
            output.append("")
            output.append(f"Beta:                    {results['beta']}")
            output.append(f"Risk-Free Rate:          {results['risk_free_rate']} ({results['risk_free_rate']*100:.2f}%)")
            output.append(f"Near-Term Growth Rate:   {results['near_term_growth_rate']} ({results['near_term_growth_rate']*100:.1f}%)" if results['near_term_growth_rate'] else "Near-Term Growth Rate:   NOT FOUND - search manually")
            output.append(f"Industry Growth Rate:    {results['industry_growth_rate']} ({results['industry_growth_rate']*100:.1f}%)" if results['industry_growth_rate'] else "Industry Growth Rate:    NOT FOUND")
            output.append("")
            output.append("-" * 70)
            output.append("DATA SOURCES:")
            output.append("-" * 70)
            for source in results['sources']:
                output.append(f"  - {source}")
            output.append("")

            if results['warnings']:
                output.append("-" * 70)
                output.append("WARNINGS:")
                output.append("-" * 70)
                for warning in results['warnings']:
                    output.append(f"  ⚠ {warning}")
                output.append("")

            output.append("-" * 70)
            output.append("USAGE EXAMPLE:")
            output.append("-" * 70)
            output.append("Pass these values to perform_dcf_analysis:")
            output.append(f"""{{
    "ticker": "{ticker_clean}",
    "beta": {results['beta']},
    "risk_free_rate": {results['risk_free_rate']},
    "near_term_growth_rate": {results['near_term_growth_rate'] if results['near_term_growth_rate'] else 'REQUIRED'},
    "long_term_growth_rate": {results['industry_growth_rate']},
    "terminal_growth_rate": 0.025,
    "market_risk_premium": 0.055
}}""")
            output.append("")
            output.append("Note: terminal_growth_rate (2.5%) and market_risk_premium (5.5% for quality")
            output.append("mega-cap, 6-7% for others) should be set based on company quality assessment.")
            output.append("=" * 70)

            return "\n".join(output)

        except Exception as e:
            logger.error(f"Error fetching market parameters for {ticker}: {e}")
            return f"Error fetching market parameters for {ticker}: {str(e)}"

    async def _arun(self, ticker: str, company_name: str = "", industry: str = "") -> str:
        """Async version"""
        return self._run(ticker, company_name, industry)


class SearchWebTool(BaseTool):
    """Tool to search the web using Perplexity Sonar API for current financial information"""
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
        """Search the web using Perplexity Sonar API"""
        try:
            api_key = os.getenv("PERPLEXITY_API_KEY")
            if not api_key:
                return "Error: PERPLEXITY_API_KEY not found in environment variables. Please add it to your .env file."

            # Initialize Perplexity client using OpenAI SDK
            client = OpenAI(
                api_key=api_key,
                base_url="https://api.perplexity.ai"
            )

            # Make search request
            response = client.chat.completions.create(
                model="sonar-pro",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a financial research assistant. Provide accurate, sourced information about financial metrics, company data, and market conditions. Include specific numbers and cite your sources."
                    },
                    {
                        "role": "user",
                        "content": query
                    }
                ],
            )

            # Extract the response
            if response.choices and len(response.choices) > 0:
                result = response.choices[0].message.content
                return f"Web Search Results:\n\n{result}"
            else:
                return "Error: No results returned from web search"

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
        lines.append("  Data sources: Financial Datasets API, Perplexity Sonar API, FMP API")
        lines.append("")
        lines.append("=" * 80)
        lines.append(f"Generated by Finance DCF Agent | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 80)

        return "\n".join(lines)

    async def _arun(self, **kwargs) -> str:
        """Async version"""
        return self._run(**kwargs)


def get_dcf_tools():
    """Return list of all DCF analysis tools including context, market parameters, and report formatting"""
    from tools.context_tools import GetCompanyContextTool
    return [
        GetCompanyContextTool(),      # Rich context first - business model, news, catalysts
        GetStockInfoTool(),
        GetFinancialMetricsTool(),
        GetMarketParametersTool(),    # NEW: Focused Perplexity queries for DCF assumptions
        CompetitorAnalysisTool(),     # Competitive analysis for market positioning
        SearchWebTool(),              # Keep for qualitative research (industry, news, etc.)
        PerformDCFAnalysisTool(),
        GetDCFComparisonTool(),       # FMP DCF cross-validation (use after performing your DCF)
        FormatDCFReportTool()         # NEW: Professional report formatting
    ]
