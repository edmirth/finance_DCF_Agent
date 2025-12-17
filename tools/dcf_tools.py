"""
LangChain Tools for DCF Analysis Agent
"""
from langchain.tools import BaseTool
from typing import Optional, Type
from pydantic import BaseModel, Field
from data.financial_data import FinancialDataFetcher
from calculators.dcf_calculator import DCFCalculator, DCFAssumptions
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
    """Input for DCF analysis tool"""
    ticker: str = Field(description="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)")

    # Growth assumptions
    revenue_growth_rate: Optional[float] = Field(
        default=None,
        description="Expected annual revenue growth rate (decimal, e.g., 0.10 for 10%). Use analyst consensus from web search. If not provided, will use historical CAGR."
    )
    terminal_growth_rate: Optional[float] = Field(
        default=None,
        description="Terminal perpetual growth rate (decimal, e.g., 0.025 for 2.5%). REQUIRED - must be provided by agent. Typical range: 2-3% for mature companies."
    )

    # Operating assumptions (calculated from financial data if not provided)
    ebit_margin: Optional[float] = Field(
        default=None,
        description="EBIT (Operating Income) margin as % of revenue. If not provided, calculated from historical data."
    )
    tax_rate: Optional[float] = Field(
        default=None,
        description="Corporate tax rate (decimal, e.g., 0.21 for 21%). If not provided, uses effective tax rate from financial statements."
    )

    # Capital intensity (calculated from financial data if not provided)
    capex_to_revenue: Optional[float] = Field(
        default=None,
        description="Capital expenditures as % of revenue. If not provided, calculated from historical CapEx."
    )
    depreciation_to_revenue: Optional[float] = Field(
        default=None,
        description="Depreciation & Amortization as % of revenue. If not provided, calculated from historical D&A."
    )
    nwc_to_revenue: Optional[float] = Field(
        default=None,
        description="Net Working Capital as % of revenue. If not provided, calculated from balance sheet."
    )

    # WACC components - sourced from web search when possible
    beta: Optional[float] = Field(
        default=None,
        description="Stock beta coefficient. IMPORTANT: Pass beta from web search if available. Otherwise uses default or financial data."
    )
    risk_free_rate: Optional[float] = Field(
        default=None,
        description="Risk-free rate (decimal, e.g., 0.04 for 4%). REQUIRED - must be provided from current 10-year Treasury yield via web search."
    )
    market_risk_premium: Optional[float] = Field(
        default=None,
        description="Market risk premium (decimal, e.g., 0.08 for 8%). REQUIRED - must be provided by agent. Typical range: 6-8%."
    )
    cost_of_debt: Optional[float] = Field(
        default=None,
        description="Cost of debt (decimal, e.g., 0.05 for 5%). If not provided, calculated from Interest Expense / Total Debt."
    )

    # Projection parameters
    projection_years: Optional[int] = Field(
        default=5,
        description="Number of years to project cash flows (typically 5-10 years)"
    )


class WebSearchInput(BaseModel):
    """Input for web search tool"""
    query: str = Field(description="Search query to find information on the web (e.g., 'Apple beta coefficient 2024', 'Tesla revenue growth forecast')")


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
    description: str = """Perform a complete DCF (Discounted Cash Flow) valuation analysis with Bull, Base, and Bear scenarios.
    This will calculate the intrinsic value of the stock and provide investment recommendations.

    IMPORTANT: You should pass custom assumptions based on your web search research:
    - beta: Pass the current beta coefficient you found (e.g., 1.22)
    - revenue_growth_rate: Use analyst consensus growth rates you found
    - risk_free_rate: Use current 10-year Treasury yield if you found it
    - fcf_margin: Estimate based on historical FCF/Revenue ratio
    - terminal_growth_rate: Typically 2-3% for mature companies
    - market_risk_premium: Typically 6-8%

    The more accurate your inputs from web research, the better the valuation."""
    args_schema: Type[BaseModel] = DCFAnalysisInput

    def _run(
        self,
        ticker: str,
        revenue_growth_rate: Optional[float] = None,
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
        projection_years: int = 5  # Methodology choice, not company-specific
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
                    parsed_params = json.loads(json_str)
                    logger.info(f"Parsed JSON parameters from ticker string: {list(parsed_params.keys())}")

                    # Extract ticker from parsed JSON
                    ticker_clean = parsed_params.get('ticker', '').upper()

                    # Override None parameters with parsed values if available
                    if revenue_growth_rate is None and 'revenue_growth_rate' in parsed_params:
                        revenue_growth_rate = parsed_params['revenue_growth_rate']
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
            # NO DEFAULTS - All values must be calculated from real data or explicitly provided

            # 1. Revenue growth rate
            if revenue_growth_rate is None:
                historical_revenue = metrics.get('historical_revenue', [])
                if len(historical_revenue) >= 2:
                    revenue_growth_rate = fetcher.calculate_historical_growth_rate(historical_revenue)
                    logger.info(f"Calculated revenue growth from historical data: {revenue_growth_rate:.2%}")
                else:
                    return f"Error: Insufficient historical revenue data for {ticker_clean}. Cannot calculate revenue growth rate. Need at least 2 years of data."

            # 2. EBIT margin
            if ebit_margin is None:
                latest_ebit = metrics.get('latest_ebit', 0)
                if latest_ebit > 0 and current_revenue > 0:
                    ebit_margin = latest_ebit / current_revenue
                    logger.info(f"Calculated EBIT margin: {ebit_margin:.2%}")
                else:
                    return f"Error: Cannot calculate EBIT margin for {ticker_clean}. Missing EBIT or revenue data."

            # 3. Tax rate
            if tax_rate is None:
                tax_rate = metrics.get('effective_tax_rate')
                if tax_rate is None or tax_rate <= 0:
                    return f"Error: Cannot determine tax rate for {ticker_clean}. Missing effective tax rate data."
                logger.info(f"Using effective tax rate: {tax_rate:.2%}")

            # 4. CapEx to revenue
            if capex_to_revenue is None:
                latest_capex = metrics.get('latest_capex', 0)
                if latest_capex > 0 and current_revenue > 0:
                    capex_to_revenue = latest_capex / current_revenue
                    logger.info(f"Calculated CapEx/Revenue: {capex_to_revenue:.2%}")
                else:
                    return f"Error: Cannot calculate CapEx/Revenue for {ticker_clean}. Missing CapEx or revenue data."

            # 5. Depreciation to revenue
            if depreciation_to_revenue is None:
                latest_da = metrics.get('latest_depreciation_amortization', 0)
                if latest_da > 0 and current_revenue > 0:
                    depreciation_to_revenue = latest_da / current_revenue
                    logger.info(f"Calculated D&A/Revenue: {depreciation_to_revenue:.2%}")
                else:
                    return f"Error: Cannot calculate D&A/Revenue for {ticker_clean}. Missing depreciation/amortization or revenue data."

            # 6. NWC to revenue
            if nwc_to_revenue is None:
                nwc = metrics.get('net_working_capital', 0)
                if current_revenue > 0 and nwc != 0:
                    nwc_to_revenue = abs(nwc) / current_revenue
                    logger.info(f"Calculated NWC/Revenue: {nwc_to_revenue:.2%}")
                else:
                    return f"Error: Cannot calculate NWC/Revenue for {ticker_clean}. Missing net working capital or revenue data."

            # 7. Beta
            if beta is not None:
                final_beta = beta
                logger.info(f"Using beta from web search/parameter: {final_beta}")
            else:
                final_beta = metrics.get('beta')
                if final_beta is None:
                    return f"Error: Cannot determine beta for {ticker_clean}. Beta not provided and not found in financial data."
                logger.info(f"Using beta from financial data: {final_beta}")

            # 8. Cost of debt
            if cost_of_debt is None:
                interest_expense = metrics.get('latest_interest_expense', 0)
                if total_debt > 0 and interest_expense > 0:
                    cost_of_debt = interest_expense / total_debt
                    logger.info(f"Calculated cost of debt: {cost_of_debt:.2%}")
                elif total_debt > 0 and interest_expense == 0:
                    # Company has debt but no interest expense in this period (e.g., zero-coupon bonds, capitalized interest)
                    cost_of_debt = 0.0
                    logger.info(f"Company has debt but no interest expense - using cost of debt: 0.00%")
                elif total_debt == 0:
                    # No debt - cost of debt is irrelevant but set to 0
                    cost_of_debt = 0.0
                    logger.info(f"Company has no debt - using cost of debt: 0.00%")
                else:
                    return f"Error: Cannot calculate cost of debt for {ticker_clean}. Missing interest expense or debt data."

            # 9. Debt to equity ratio (for WACC calculation)
            market_value_equity = current_price * shares_outstanding if (current_price > 0 and shares_outstanding > 0) else 0
            if market_value_equity > 0:
                if total_debt > 0:
                    debt_to_equity_ratio = total_debt / market_value_equity
                    logger.info(f"Calculated D/E ratio: {debt_to_equity_ratio:.3f}")
                else:
                    # Company has no debt - D/E ratio is 0
                    debt_to_equity_ratio = 0.0
                    logger.info(f"Company has no debt - using D/E ratio: 0.000")
            else:
                return f"Error: Cannot calculate debt/equity ratio for {ticker_clean}. Missing market value data."

            # 10. Terminal growth rate
            if terminal_growth_rate is None:
                return f"Error: Terminal growth rate must be provided for {ticker_clean}. Typical range is 2-3% for mature companies."

            # 11. Risk-free rate
            if risk_free_rate is None:
                return f"Error: Risk-free rate must be provided for {ticker_clean}. Use current 10-year Treasury yield from web search."

            # 12. Market risk premium
            if market_risk_premium is None:
                return f"Error: Market risk premium must be provided for {ticker_clean}. Typical range is 6-8%."

            # Create assumptions using calculated or provided parameters
            # IMPORTANT: ALL parameters are REQUIRED - no defaults in DCFAssumptions
            assumptions = DCFAssumptions(
                revenue_growth_rate=revenue_growth_rate,
                terminal_growth_rate=terminal_growth_rate,
                ebit_margin=ebit_margin,
                tax_rate=tax_rate,
                capex_to_revenue=capex_to_revenue,
                depreciation_to_revenue=depreciation_to_revenue,
                nwc_to_revenue=nwc_to_revenue,
                beta=final_beta,
                risk_free_rate=risk_free_rate,
                market_risk_premium=market_risk_premium,
                cost_of_debt=cost_of_debt,
                debt_to_equity_ratio=debt_to_equity_ratio,
                projection_years=projection_years
            )

            # Perform DCF with scenarios
            calculator = DCFCalculator()
            results = calculator.analyze_with_scenarios(
                ticker=ticker_clean,
                current_revenue=current_revenue,
                current_price=current_price,
                shares_outstanding=shares_outstanding,
                total_debt=total_debt,
                cash=cash,
                base_assumptions=assumptions
            )

            # Format results
            analysis = calculator.format_dcf_analysis(results)

            return analysis

        except Exception as e:
            logger.error(f"Error performing DCF analysis: {e}")
            ticker_clean = ticker.split(',')[0].split('\n')[0].strip().upper()
            return f"Error performing DCF analysis for {ticker_clean}: {str(e)}"

    async def _arun(
        self,
        ticker: str,
        revenue_growth_rate: Optional[float] = None,
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
            revenue_growth_rate,
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


def get_dcf_tools():
    """Return list of all DCF analysis tools"""
    return [
        GetStockInfoTool(),
        GetFinancialMetricsTool(),
        SearchWebTool(),
        PerformDCFAnalysisTool()
    ]
