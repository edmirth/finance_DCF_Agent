"""
Tools for the Financial Research Assistant agent.

These tools enable interactive, conversational financial analysis with:
- Quick data lookups for specific metrics
- Financial calculations and ratio analysis
- Recent news and report explanations
- Company comparisons
- Market comparisons
"""

import os
import logging
import requests
from typing import Optional, List, Dict, Any
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
from data.financial_data import FinancialDataFetcher

# Set up logging
logger = logging.getLogger(__name__)


class QuickDataInput(BaseModel):
    """Input for quick financial data lookup"""
    ticker: str = Field(description="Stock ticker symbol (e.g., 'AAPL')")
    metrics: str = Field(
        description="Comma-separated list of metrics to retrieve. Options: 'revenue', 'net_income', 'fcf', 'cash', 'debt', 'shares', 'market_cap', 'pe_ratio', 'price', 'margins', 'growth', 'all'"
    )


class QuickFinancialDataTool(BaseTool):
    """Tool for quickly retrieving specific financial metrics"""

    name: str = "get_quick_data"
    description: str = """Quickly retrieves specific financial metrics for a company.
    Use this when the user asks about specific data points like revenue, earnings, cash, debt, etc.

    Available metrics:
    - revenue: Total revenue (annual)
    - net_income: Net income/earnings
    - fcf: Free cash flow
    - cash: Cash and equivalents
    - debt: Total debt
    - shares: Shares outstanding
    - market_cap: Market capitalization
    - pe_ratio: Price-to-earnings ratio
    - price: Current stock price
    - margins: Profit margins (gross, operating, net)
    - growth: Historical growth rates (revenue, FCF)
    - all: All available metrics

    Example: ticker='AAPL', metrics='revenue,fcf,pe_ratio'
    """
    args_schema: type[BaseModel] = QuickDataInput

    def _run(self, ticker: str, metrics: str) -> str:
        """Retrieve requested financial metrics"""
        try:
            # Input validation
            ticker = ticker.strip().upper()
            if not ticker or len(ticker) > 5:
                return f"Error: Invalid ticker format '{ticker}'. Please use 1-5 uppercase letters (e.g., 'AAPL')."

            requested_metrics = [m.strip().lower() for m in metrics.split(',')]
            valid_metrics = {'revenue', 'net_income', 'fcf', 'cash', 'debt', 'shares', 'market_cap', 'pe_ratio', 'price', 'margins', 'growth', 'all'}
            invalid = set(requested_metrics) - valid_metrics
            if invalid:
                return f"Error: Unknown metrics {invalid}. Available: {', '.join(valid_metrics)}"

            # Get data with better error handling
            fetcher = FinancialDataFetcher()

            try:
                stock_info = fetcher.get_stock_info(ticker)
            except ValueError as e:
                return f"Error: API authentication failed. Please check FINANCIAL_DATASETS_API_KEY in environment."
            except Exception as e:
                if "404" in str(e) or "not found" in str(e).lower():
                    return f"Error: Ticker '{ticker}' not found. Please verify the symbol is correct."
                return f"Error: Failed to fetch stock info for {ticker}. The API may be experiencing issues."

            try:
                key_metrics = fetcher.get_key_metrics(ticker)
            except Exception as e:
                return f"Error: Failed to fetch financial metrics for {ticker}. Some data may be unavailable for this company."

            if not stock_info or 'company_name' not in stock_info:
                return f"Error: No data available for ticker '{ticker}'. This may be a delisted or invalid ticker."

            if not key_metrics:
                return f"Error: Financial metrics unavailable for {ticker}. This company may lack complete financial data."

            # Build response
            result = f"📊 **{stock_info.get('name', ticker)} ({ticker})**\n\n"

            # Helper to format large numbers
            def format_number(val):
                if val is None:
                    return "N/A"
                if abs(val) >= 1e9:
                    return f"${val/1e9:.2f}B"
                elif abs(val) >= 1e6:
                    return f"${val/1e6:.2f}M"
                else:
                    return f"${val:,.0f}"

            # Process each requested metric
            show_all = 'all' in requested_metrics

            if show_all or 'price' in requested_metrics:
                result += f"**Current Price:** ${key_metrics.get('current_price', 'N/A')}\n"

            if show_all or 'market_cap' in requested_metrics:
                result += f"**Market Cap:** {format_number(stock_info.get('market_cap'))}\n"

            if show_all or 'revenue' in requested_metrics:
                result += f"**Revenue (TTM):** {format_number(key_metrics.get('latest_revenue'))}\n"

            if show_all or 'net_income' in requested_metrics:
                net_income = key_metrics.get('latest_net_income', 0)
                if net_income:
                    result += f"**Net Income:** {format_number(net_income)}\n"
                else:
                    result += f"**Net Income:** N/A\n"

            if show_all or 'fcf' in requested_metrics:
                result += f"**Free Cash Flow:** {format_number(key_metrics.get('latest_fcf'))}\n"

            if show_all or 'cash' in requested_metrics:
                result += f"**Cash & Equivalents:** {format_number(key_metrics.get('cash_and_equivalents'))}\n"

            if show_all or 'debt' in requested_metrics:
                result += f"**Total Debt:** {format_number(key_metrics.get('total_debt'))}\n"

            if show_all or 'shares' in requested_metrics:
                shares = key_metrics.get('shares_outstanding')
                if shares:
                    result += f"**Shares Outstanding:** {shares/1e9:.2f}B\n"

            if show_all or 'pe_ratio' in requested_metrics:
                price = stock_info.get('current_price', 0)
                net_income = key_metrics.get('latest_net_income', 0)
                shares = key_metrics.get('shares_outstanding', 1)
                if price > 0 and net_income > 0 and shares > 0:
                    eps = net_income / shares
                    pe = price / eps
                    result += f"**P/E Ratio:** {pe:.2f}x\n"
                else:
                    result += f"**P/E Ratio:** N/A\n"

            if show_all or 'margins' in requested_metrics:
                revenue = key_metrics.get('latest_revenue', 0)
                net_income = key_metrics.get('latest_net_income', 0)
                fcf = key_metrics.get('latest_fcf', 0)
                if revenue > 0:
                    if net_income:
                        net_margin = (net_income / revenue) * 100
                        result += f"**Net Profit Margin:** {net_margin:.1f}%\n"
                    fcf_margin = (fcf / revenue) * 100
                    result += f"**FCF Margin:** {fcf_margin:.1f}%\n"

                # Historical margins (last 5 years)
                hist_revenue = key_metrics.get('historical_revenue', [])
                hist_net_income = key_metrics.get('historical_net_income', [])
                if len(hist_revenue) == len(hist_net_income) and len(hist_revenue) > 0:
                    result += f"\n**Historical Net Profit Margins (5Y):**\n"
                    for i, (rev, ni) in enumerate(zip(hist_revenue, hist_net_income)):
                        if rev > 0:
                            margin = (ni / rev) * 100
                            year_label = f"Year {i+1}" if i > 0 else "Latest"
                            result += f"  {year_label}: {margin:.1f}%\n"

            if show_all or 'growth' in requested_metrics:
                # Calculate growth rates from historical data
                hist_revenue = key_metrics.get('historical_revenue', [])
                hist_fcf = key_metrics.get('historical_fcf', [])

                if len(hist_revenue) >= 2:
                    rev_cagr = ((hist_revenue[0] / hist_revenue[-1]) ** (1 / (len(hist_revenue) - 1)) - 1) * 100
                    result += f"**Revenue CAGR ({len(hist_revenue)-1}Y):** {rev_cagr:.1f}%\n"

                if len(hist_fcf) >= 2 and hist_fcf[-1] > 0:
                    fcf_cagr = ((hist_fcf[0] / hist_fcf[-1]) ** (1 / (len(hist_fcf) - 1)) - 1) * 100
                    result += f"**FCF CAGR ({len(hist_fcf)-1}Y):** {fcf_cagr:.1f}%\n"

            return result.strip()

        except Exception as e:
            return f"Error retrieving quick data for {ticker}: {str(e)}"

    async def _arun(self, ticker: str, metrics: str) -> str:
        return self._run(ticker, metrics)


class CalculatorInput(BaseModel):
    """Input for financial calculator"""
    calculation: str = Field(
        description="The calculation to perform. Examples: 'P/E ratio for AAPL', 'EV/EBITDA for MSFT', 'Debt to equity for TSLA', 'ROE for GOOGL', 'compound annual growth from 100 to 150 over 5 years'"
    )
    ticker: Optional[str] = Field(
        default=None,
        description="Stock ticker if calculation requires company data"
    )


class FinancialCalculatorTool(BaseTool):
    """Tool for performing financial calculations"""

    name: str = "calculate"
    description: str = """Performs financial calculations and ratio analysis.

    Supported calculations:
    - Valuation ratios: P/E, P/S, P/B, EV/EBITDA, PEG, FCF Yield
    - Profitability: ROE (fixed: uses book equity), ROA, ROIC
    - Leverage: Debt/Equity, Debt/EBITDA, Interest Coverage
    - Growth: CAGR, growth rates
    - All calculations use actual financial statement data

    Examples:
    - "P/E ratio for AAPL"
    - "EV/EBITDA for TSLA"
    - "ROE for MSFT"
    - "Interest coverage for AAPL"
    - "CAGR from 100 to 200 over 5 years"
    """
    args_schema: type[BaseModel] = CalculatorInput

    def _run(self, calculation: str, ticker: Optional[str] = None) -> str:
        """Perform the requested calculation"""
        try:
            calc_lower = calculation.lower()

            # Extract ticker from calculation if not provided
            if ticker is None:
                import re
                ticker_match = re.search(r'\b([A-Z]{1,5})\b', calculation)
                if ticker_match:
                    ticker = ticker_match.group(1)

            # CAGR calculation (no ticker needed)
            if 'cagr' in calc_lower or 'compound' in calc_lower:
                import re
                numbers = re.findall(r'[\d.]+', calculation)
                if len(numbers) >= 3:
                    start, end, years = float(numbers[0]), float(numbers[1]), float(numbers[2])
                    cagr = ((end / start) ** (1 / years) - 1) * 100
                    return f"**CAGR Calculation:**\n- Starting value: {start}\n- Ending value: {end}\n- Years: {years}\n- **CAGR: {cagr:.2f}%**"
                return "Error: Need starting value, ending value, and number of years for CAGR"

            # Growth rate calculation
            if 'growth' in calc_lower and 'from' in calc_lower:
                import re
                numbers = re.findall(r'[\d.]+', calculation)
                if len(numbers) >= 2:
                    start, end = float(numbers[0]), float(numbers[1])
                    growth = ((end - start) / start) * 100
                    return f"**Growth Rate:**\n- Starting: {start}\n- Ending: {end}\n- **Growth: {growth:.2f}%**"

            # Ticker-based calculations
            if ticker:
                ticker = ticker.strip().upper()
                fetcher = FinancialDataFetcher()
                metrics = fetcher.get_key_metrics(ticker)
                if not metrics:
                    return f"Error: Could not retrieve data for {ticker}"

                revenue = metrics.get('latest_revenue', 0)
                net_income = metrics.get('latest_net_income', 0)
                ebit = metrics.get('latest_ebit', 0)
                fcf = metrics.get('latest_fcf', 0)
                cash = metrics.get('cash_and_equivalents', 0)
                debt = metrics.get('total_debt', 0)
                shares = metrics.get('shares_outstanding', 1)
                interest_expense = metrics.get('latest_interest_expense', 0)
                depreciation_amortization = metrics.get('latest_depreciation_amortization', 0)

                # Get stock info (same fetcher instance due to singleton pattern)
                stock_info = fetcher.get_stock_info(ticker)
                price = stock_info.get('current_price', 0)
                market_cap = stock_info.get('market_cap', price * shares if price > 0 else 0)

                # Get balance sheet data for book equity
                statements = fetcher.get_financial_statements(ticker)
                balance_sheets = statements.get('balance_sheets', [])
                book_equity = 0
                total_assets = 0
                if balance_sheets:
                    latest_bs = balance_sheets[0]
                    book_equity = latest_bs.get('total_equity', 0) or latest_bs.get('stockholders_equity', 0) or 0
                    total_assets = latest_bs.get('total_assets', 0) or 0

                # P/E Ratio
                if 'p/e' in calc_lower or 'pe ratio' in calc_lower or 'price to earnings' in calc_lower:
                    eps = net_income / shares if shares > 0 else 0
                    pe = price / eps if eps > 0 else None
                    if pe:
                        return f"**P/E Ratio for {ticker}:**\n- Price: ${price:.2f}\n- EPS: ${eps:.2f}\n- **P/E: {pe:.2f}x**"
                    return f"Cannot calculate P/E for {ticker} (negative or zero earnings)"

                # P/S Ratio
                if 'p/s' in calc_lower or 'price to sales' in calc_lower:
                    ps = market_cap / revenue if revenue > 0 else None
                    if ps:
                        return f"**P/S Ratio for {ticker}:**\n- Market Cap: ${market_cap/1e9:.2f}B\n- Revenue: ${revenue/1e9:.2f}B\n- **P/S: {ps:.2f}x**"

                # Debt to Equity
                if 'debt' in calc_lower and 'equity' in calc_lower:
                    equity = market_cap
                    de = debt / equity if equity > 0 else None
                    if de:
                        return f"**Debt/Equity for {ticker}:**\n- Total Debt: ${debt/1e9:.2f}B\n- Market Cap: ${equity/1e9:.2f}B\n- **D/E: {de:.2f}x**"

                # ROE (Return on Equity) - FIXED: now uses book equity instead of market cap
                if 'roe' in calc_lower or 'return on equity' in calc_lower:
                    if book_equity > 0 and net_income:
                        roe = (net_income / book_equity) * 100
                        return f"**ROE for {ticker}:**\n- Net Income: ${net_income/1e9:.2f}B\n- Book Equity: ${book_equity/1e9:.2f}B\n- **ROE: {roe:.2f}%**"
                    return f"Cannot calculate ROE for {ticker} (missing book equity or net income data)"

                # FCF Yield
                if 'fcf yield' in calc_lower or 'free cash flow yield' in calc_lower:
                    fcf_yield = (fcf / market_cap) * 100 if market_cap > 0 else None
                    if fcf_yield:
                        return f"**FCF Yield for {ticker}:**\n- Free Cash Flow: ${fcf/1e9:.2f}B\n- Market Cap: ${market_cap/1e9:.2f}B\n- **FCF Yield: {fcf_yield:.2f}%**"

                # P/B Ratio (Price to Book)
                if 'p/b' in calc_lower or 'price to book' in calc_lower:
                    if book_equity > 0:
                        pb = market_cap / book_equity
                        book_value_per_share = book_equity / shares if shares > 0 else 0
                        return f"**P/B Ratio for {ticker}:**\n- Market Cap: ${market_cap/1e9:.2f}B\n- Book Equity: ${book_equity/1e9:.2f}B\n- Book Value/Share: ${book_value_per_share:.2f}\n- **P/B: {pb:.2f}x**"
                    return f"Cannot calculate P/B for {ticker} (missing book equity)"

                # EV/EBITDA
                if ('ev/ebitda' in calc_lower or 'enterprise value' in calc_lower) and 'ebitda' in calc_lower:
                    if ebit > 0 and depreciation_amortization > 0:
                        ebitda = ebit + depreciation_amortization
                        enterprise_value = market_cap + debt - cash
                        ev_ebitda = enterprise_value / ebitda
                        return f"**EV/EBITDA for {ticker}:**\n- Enterprise Value: ${enterprise_value/1e9:.2f}B\n- EBITDA: ${ebitda/1e9:.2f}B\n- **EV/EBITDA: {ev_ebitda:.2f}x**"
                    return f"Cannot calculate EV/EBITDA for {ticker} (missing EBIT or D&A data)"

                # PEG Ratio (P/E to Growth)
                if 'peg' in calc_lower:
                    hist_revenue = metrics.get('historical_revenue', [])
                    if len(hist_revenue) >= 2 and net_income > 0 and shares > 0:
                        eps = net_income / shares
                        pe = price / eps if eps > 0 else 0
                        # Calculate revenue growth rate
                        growth = ((hist_revenue[0] / hist_revenue[-1]) ** (1 / (len(hist_revenue) - 1)) - 1) * 100
                        peg = pe / growth if growth > 0 else None
                        if peg:
                            return f"**PEG Ratio for {ticker}:**\n- P/E: {pe:.2f}x\n- Revenue Growth: {growth:.1f}%\n- **PEG: {peg:.2f}**\n(PEG < 1 may indicate undervaluation relative to growth)"
                    return f"Cannot calculate PEG for {ticker} (missing earnings or growth data)"

                # ROA (Return on Assets)
                if 'roa' in calc_lower or 'return on assets' in calc_lower:
                    if total_assets > 0 and net_income:
                        roa = (net_income / total_assets) * 100
                        return f"**ROA for {ticker}:**\n- Net Income: ${net_income/1e9:.2f}B\n- Total Assets: ${total_assets/1e9:.2f}B\n- **ROA: {roa:.2f}%**"
                    return f"Cannot calculate ROA for {ticker} (missing assets or net income)"

                # ROIC (Return on Invested Capital)
                if 'roic' in calc_lower or 'return on invested capital' in calc_lower:
                    if book_equity > 0 and debt >= 0 and net_income:
                        invested_capital = book_equity + debt
                        roic = (net_income / invested_capital) * 100
                        return f"**ROIC for {ticker}:**\n- Net Income: ${net_income/1e9:.2f}B\n- Invested Capital: ${invested_capital/1e9:.2f}B\n- **ROIC: {roic:.2f}%**\n(ROIC > WACC indicates value creation)"
                    return f"Cannot calculate ROIC for {ticker} (missing equity or debt data)"

                # Debt/EBITDA (Leverage ratio)
                if 'debt' in calc_lower and 'ebitda' in calc_lower:
                    if ebit > 0 and depreciation_amortization > 0:
                        ebitda = ebit + depreciation_amortization
                        debt_to_ebitda = debt / ebitda if ebitda > 0 else None
                        if debt_to_ebitda is not None:
                            return f"**Debt/EBITDA for {ticker}:**\n- Total Debt: ${debt/1e9:.2f}B\n- EBITDA: ${ebitda/1e9:.2f}B\n- **Debt/EBITDA: {debt_to_ebitda:.2f}x**\n(< 3x is generally healthy)"
                    return f"Cannot calculate Debt/EBITDA for {ticker} (missing EBIT or D&A)"

                # Interest Coverage
                if 'interest coverage' in calc_lower or ('interest' in calc_lower and 'coverage' in calc_lower):
                    if interest_expense > 0 and ebit > 0:
                        coverage = ebit / abs(interest_expense)
                        health = "Strong" if coverage > 5 else "Adequate" if coverage > 2.5 else "Weak"
                        return f"**Interest Coverage for {ticker}:**\n- EBIT: ${ebit/1e9:.2f}B\n- Interest Expense: ${abs(interest_expense)/1e9:.2f}B\n- **Coverage Ratio: {coverage:.2f}x**\n- Assessment: {health} (>{5}x is strong)"
                    return f"Cannot calculate Interest Coverage for {ticker} (missing EBIT or interest expense)"

            return f"Could not perform calculation: '{calculation}'. Try being more specific or check if ticker data is available."

        except Exception as e:
            return f"Error in calculation: {str(e)}"

    async def _arun(self, calculation: str, ticker: Optional[str] = None) -> str:
        return self._run(calculation, ticker)


class NewsInput(BaseModel):
    """Input for news search"""
    ticker: str = Field(description="Stock ticker symbol")
    query: Optional[str] = Field(
        default=None,
        description="Optional specific query about the company (e.g., 'earnings', 'acquisition', 'lawsuit')"
    )


class RecentNewsTool(BaseTool):
    """Tool for fetching and explaining recent news"""

    name: str = "get_recent_news"
    description: str = """Fetches and explains recent news, reports, and developments about a company.
    Use this when the user asks about recent news, earnings reports, announcements, or current events.

    Can search for general news or specific topics like:
    - Earnings reports
    - Product launches
    - Acquisitions/M&A
    - Regulatory issues
    - Management changes
    - Analyst upgrades/downgrades
    """
    args_schema: type[BaseModel] = NewsInput

    def _run(self, ticker: str, query: Optional[str] = None) -> str:
        """Fetch comprehensive news with financial context"""
        try:
            ticker = ticker.strip().upper()

            # Get company info and financial context
            fetcher = FinancialDataFetcher()
            stock_info = fetcher.get_stock_info(ticker)
            company_name = stock_info.get('name', ticker) if stock_info else ticker

            # Get recent financial metrics for context
            metrics = fetcher.get_key_metrics(ticker)
            current_price = stock_info.get('price', 0) if stock_info else 0
            market_cap = stock_info.get('market_cap', 0) if stock_info else 0

            # Use Perplexity API to search for comprehensive news
            api_key = os.getenv("PERPLEXITY_API_KEY")
            if not api_key:
                return "Error: PERPLEXITY_API_KEY not found in environment"

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

            # Build comprehensive search query
            if query:
                search_focus = f"{query} related news"
            else:
                search_focus = "recent news, earnings reports, product launches, strategic initiatives, analyst coverage, and market developments"

            payload = {
                "model": "sonar-pro",
                "messages": [
                    {
                        "role": "system",
                        "content": f"""You are an expert financial journalist providing comprehensive news coverage and analysis.

Your task is to research and report on recent developments for {company_name} ({ticker}).

INSTRUCTIONS:
1. Search for actual news articles, press releases, earnings reports, and analyst commentary from the past 30-60 days
2. Focus on material events: earnings, product launches, strategic shifts, M&A, regulatory issues, executive changes, market share changes
3. For each news item, provide:
   - A descriptive headline that captures the essence of the story
   - The date (as specific as possible)
   - Comprehensive summary of what happened
   - Business context and implications
   - Source attribution
4. Organize by theme/category (Earnings & Financials, Products & Innovation, Strategic Moves, Market Performance, etc.)
5. Include relevant numbers and metrics when discussing financial news
6. Write in a journalistic style - comprehensive but clear
7. If you find limited recent news, expand the time window or discuss the company's current business situation and recent quarter performance

DO NOT:
- Make up news that doesn't exist
- Use vague broker recommendations as "news"
- List items without context
- Be overly cautious - if you find news in your search, report it with full detail

LENGTH: Write as much as needed to fully cover recent developments. Comprehensive analysis is valued over brevity."""
                    },
                    {
                        "role": "user",
                        "content": f"""Research and provide a comprehensive news report on {company_name} ({ticker}).

Search for: {search_focus}

Current context:
- Stock Price: ${current_price:.2f}
- Market Cap: ${market_cap/1e9:.2f}B

Provide a detailed report with actual headlines, dates, summaries, and business implications. Organize by category for readability."""
                    }
                ],
                "max_tokens": 3000,  # Allow longer, more comprehensive responses
                "temperature": 0.2,
                "return_citations": True,
                "return_related_questions": False
            }

            response = requests.post(
                "https://api.perplexity.ai/chat/completions",
                headers=headers,
                json=payload,
                timeout=45
            )

            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                citations = result.get('citations', [])

                # Build comprehensive response with context
                output = f"# 📰 News & Developments: {company_name} ({ticker})\n\n"

                # Add current snapshot
                output += f"**Current Snapshot** (as of latest data):\n"
                output += f"- Stock Price: ${current_price:.2f}\n"
                output += f"- Market Capitalization: ${market_cap/1e9:.2f}B\n"
                if metrics:
                    latest_revenue = metrics.get('latest_revenue', 0)
                    if latest_revenue > 0:
                        output += f"- Latest Annual Revenue: ${latest_revenue/1e9:.2f}B\n"
                output += f"\n---\n\n"

                # Add news content
                output += content

                # Add sources at the end
                if citations:
                    output += "\n\n---\n\n## 📚 Sources\n\n"
                    for citation in citations:
                        output += f"- {citation}\n"

                return output
            else:
                return f"Error fetching news: HTTP {response.status_code}"

        except Exception as e:
            return f"Error getting news for {ticker}: {str(e)}"

    async def _arun(self, ticker: str, query: Optional[str] = None) -> str:
        return self._run(ticker, query)


class ComparisonInput(BaseModel):
    """Input for company comparison"""
    ticker1: str = Field(description="First company ticker symbol")
    ticker2: str = Field(description="Second company ticker symbol")
    metrics: Optional[str] = Field(
        default="valuation,profitability,growth",
        description="Comparison categories: 'valuation', 'profitability', 'growth', 'size', 'all'"
    )


class CompanyComparisonTool(BaseTool):
    """Tool for comparing two companies"""

    name: str = "compare_companies"
    description: str = """Compares key metrics between two companies side by side.
    Use this when the user wants to compare companies or asks "vs" questions.

    Comparison categories:
    - valuation: P/E, P/S, market cap
    - profitability: Margins, ROE, FCF
    - growth: Revenue growth, earnings growth
    - size: Revenue, market cap, employees
    - all: Complete comparison

    Example: ticker1='AAPL', ticker2='MSFT', metrics='valuation,profitability'
    """
    args_schema: type[BaseModel] = ComparisonInput

    def _run(self, ticker1: str, ticker2: str, metrics: str = "valuation,profitability,growth") -> str:
        """Compare two companies with enhanced formatting and insights"""
        try:
            # Input validation
            ticker1 = ticker1.strip().upper()
            ticker2 = ticker2.strip().upper()

            if not ticker1 or not ticker2:
                return "Error: Both ticker symbols are required for comparison."

            if ticker1 == ticker2:
                return f"Error: Cannot compare {ticker1} to itself. Please provide two different tickers."

            # Get data for both companies with better error handling
            fetcher = FinancialDataFetcher()

            try:
                info1 = fetcher.get_stock_info(ticker1)
                metrics1 = fetcher.get_key_metrics(ticker1)
            except Exception as e:
                return f"Error: Could not retrieve data for {ticker1}. Please verify the ticker is correct."

            try:
                info2 = fetcher.get_stock_info(ticker2)
                metrics2 = fetcher.get_key_metrics(ticker2)
            except Exception as e:
                return f"Error: Could not retrieve data for {ticker2}. Please verify the ticker is correct."

            if not info1 or not metrics1:
                return f"Error: Incomplete data for {ticker1}. This ticker may be invalid or delisted."

            if not info2 or not metrics2:
                return f"Error: Incomplete data for {ticker2}. This ticker may be invalid or delisted."

            name1 = info1.get('company_name', ticker1)
            name2 = info2.get('company_name', ticker2)

            result = f"📊 **Company Comparison: {name1} vs {name2}**\n\n"

            categories = [m.strip().lower() for m in metrics.split(',')]
            show_all = 'all' in categories

            # Extract common metrics used across multiple sections
            mcap1 = info1.get('market_cap', 0)
            mcap2 = info2.get('market_cap', 0)
            rev1 = metrics1.get('latest_revenue', 0)
            rev2 = metrics2.get('latest_revenue', 0)

            # Size comparison with winner
            if show_all or 'size' in categories:

                result += "**SIZE & SCALE:**\n"
                result += f"- Market Cap: ${mcap1/1e9:.1f}B vs ${mcap2/1e9:.1f}B"
                if mcap1 > mcap2:
                    result += f" → **{ticker1} larger** ({mcap1/mcap2:.1f}x)\n"
                else:
                    result += f" → **{ticker2} larger** ({mcap2/mcap1:.1f}x)\n"

                result += f"- Revenue (TTM): ${rev1/1e9:.1f}B vs ${rev2/1e9:.1f}B"
                if rev1 > rev2:
                    result += f" → **{ticker1} larger** ({rev1/rev2:.1f}x)\n"
                else:
                    result += f" → **{ticker2} larger** ({rev2/rev1:.1f}x)\n"

                size_winner = ticker1 if (mcap1 > mcap2 and rev1 > rev2) else ticker2 if (mcap2 > mcap1 and rev2 > rev1) else "Mixed"
                result += f"**Winner: {size_winner}** (larger business)\n\n"

            # Valuation comparison with winner
            if show_all or 'valuation' in categories:
                # P/E ratios
                ni1 = metrics1.get('latest_net_income', 0)
                ni2 = metrics2.get('latest_net_income', 0)
                shares1 = metrics1.get('shares_outstanding', 1)
                shares2 = metrics2.get('shares_outstanding', 1)
                price1 = info1.get('current_price', 0)
                price2 = info2.get('current_price', 0)

                eps1 = ni1 / shares1 if shares1 > 0 else 0
                eps2 = ni2 / shares2 if shares2 > 0 else 0
                pe1 = price1 / eps1 if eps1 > 0 else None
                pe2 = price2 / eps2 if eps2 > 0 else None

                # P/S ratios
                mcap1 = info1.get('market_cap', 0)
                mcap2 = info2.get('market_cap', 0)
                ps1 = mcap1 / rev1 if rev1 > 0 else None
                ps2 = mcap2 / rev2 if rev2 > 0 else None

                result += "**VALUATION (Lower = Cheaper):**\n"
                if pe1 and pe2:
                    result += f"- P/E Ratio: {pe1:.1f}x vs {pe2:.1f}x"
                    result += f" → **{ticker1 if pe1 < pe2 else ticker2} cheaper**\n"

                if ps1 and ps2:
                    result += f"- P/S Ratio: {ps1:.1f}x vs {ps2:.1f}x"
                    result += f" → **{ticker1 if ps1 < ps2 else ticker2} cheaper**\n"

                val_winner = ticker1 if (pe1 and pe2 and pe1 < pe2 and ps1 < ps2) else ticker2 if (pe1 and pe2 and pe2 < pe1 and ps2 < ps1) else "Mixed"
                result += f"**Winner: {val_winner}** (better value)\n\n"

            # Profitability comparison with winner
            if show_all or 'profitability' in categories:
                fcf1 = metrics1.get('latest_fcf', 0)
                fcf2 = metrics2.get('latest_fcf', 0)
                fcf_margin1 = (fcf1 / rev1 * 100) if rev1 > 0 else 0
                fcf_margin2 = (fcf2 / rev2 * 100) if rev2 > 0 else 0

                result += "**PROFITABILITY (Higher = Better):**\n"
                result += f"- FCF Margin: {fcf_margin1:.1f}% vs {fcf_margin2:.1f}%"
                result += f" → **{ticker1 if fcf_margin1 > fcf_margin2 else ticker2} more profitable**\n"

                result += f"**Winner: {ticker1 if fcf_margin1 > fcf_margin2 else ticker2}** (better margins)\n\n"

            # Growth comparison with winner
            if show_all or 'growth' in categories:
                # Calculate CAGR from historical data
                hist_rev1 = metrics1.get('historical_revenue', [])
                hist_rev2 = metrics2.get('historical_revenue', [])
                hist_fcf1 = metrics1.get('historical_fcf', [])
                hist_fcf2 = metrics2.get('historical_fcf', [])

                rev_cagr1 = ((hist_rev1[0] / hist_rev1[-1]) ** (1 / (len(hist_rev1) - 1)) - 1) * 100 if len(hist_rev1) >= 2 else 0
                rev_cagr2 = ((hist_rev2[0] / hist_rev2[-1]) ** (1 / (len(hist_rev2) - 1)) - 1) * 100 if len(hist_rev2) >= 2 else 0

                result += "**GROWTH (Historical CAGR):**\n"
                result += f"- Revenue Growth: {rev_cagr1:.1f}% vs {rev_cagr2:.1f}%"
                result += f" → **{ticker1 if rev_cagr1 > rev_cagr2 else ticker2} growing faster**\n"

                if len(hist_fcf1) >= 2 and hist_fcf1[-1] > 0 and len(hist_fcf2) >= 2 and hist_fcf2[-1] > 0:
                    fcf_cagr1 = ((hist_fcf1[0] / hist_fcf1[-1]) ** (1 / (len(hist_fcf1) - 1)) - 1) * 100
                    fcf_cagr2 = ((hist_fcf2[0] / hist_fcf2[-1]) ** (1 / (len(hist_fcf2) - 1)) - 1) * 100
                    result += f"- FCF Growth: {fcf_cagr1:.1f}% vs {fcf_cagr2:.1f}%"
                    result += f" → **{ticker1 if fcf_cagr1 > fcf_cagr2 else ticker2} faster**\n"

                growth_winner = ticker1 if rev_cagr1 > rev_cagr2 else ticker2
                result += f"**Winner: {growth_winner}** (faster growth)\n\n"

            # Overall insight (only if showing all or multiple categories)
            if show_all or len(categories) > 1:
                result += "**💡 OVERALL INSIGHT:**\n"

                # Determine overall winner based on category winners
                winners = {}
                if show_all or 'valuation' in categories:
                    if pe1 and pe2:
                        winners['valuation'] = ticker1 if pe1 < pe2 else ticker2
                if show_all or 'profitability' in categories:
                    winners['profitability'] = ticker1 if fcf_margin1 > fcf_margin2 else ticker2
                if show_all or 'growth' in categories:
                    winners['growth'] = ticker1 if rev_cagr1 > rev_cagr2 else ticker2

                # Count wins
                ticker1_wins = sum(1 for w in winners.values() if w == ticker1)
                ticker2_wins = sum(1 for w in winners.values() if w == ticker2)

                if ticker1_wins > ticker2_wins:
                    result += f"{ticker1} wins {ticker1_wins}/{len(winners)} categories. "
                elif ticker2_wins > ticker1_wins:
                    result += f"{ticker2} wins {ticker2_wins}/{len(winners)} categories. "
                else:
                    result += "Tied performance across categories. "

                # Provide specific insight
                if 'valuation' in winners and 'growth' in winners:
                    val_winner = winners['valuation']
                    growth_winner = winners['growth']
                    if val_winner != growth_winner:
                        result += f"\n{val_winner} trades cheaper but {growth_winner} is growing faster - "
                        result += f"{growth_winner}'s premium valuation may be justified by superior growth."

                result += "\n"

            return result.strip()

        except Exception as e:
            logger.error(f"Comparison error: {e}", exc_info=True)
            return f"Error comparing companies: {str(e)}. Please verify both tickers are valid."

    async def _arun(self, ticker1: str, ticker2: str, metrics: str = "valuation,profitability,growth") -> str:
        return self._run(ticker1, ticker2, metrics)


def get_research_assistant_tools() -> List[BaseTool]:
    """Get all research assistant tools"""
    return [
        QuickFinancialDataTool(),
        FinancialCalculatorTool(),
        RecentNewsTool(),
        CompanyComparisonTool(),
    ]
