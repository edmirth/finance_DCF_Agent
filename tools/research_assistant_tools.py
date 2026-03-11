"""
Tools for the Financial Research Assistant agent.

These tools enable interactive, conversational financial analysis with:
- Quick data lookups for specific metrics
- Financial calculations and ratio analysis
- Recent news and report explanations
- Company comparisons
- Market comparisons
"""

import asyncio
import json
import logging
from typing import Optional, List, Dict, Any
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
from data.financial_data import FinancialDataFetcher
from shared.tavily_client import get_tavily_client

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

    Input must be valid JSON with ticker and metrics fields.
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
                return f"Error: Temporary API failure fetching data for {ticker}. Please try again."

            try:
                key_metrics = fetcher.get_key_metrics(ticker)
            except Exception as e:
                return f"Error: Temporary API failure fetching metrics for {ticker}. Please try again."

            if not stock_info or 'company_name' not in stock_info:
                error_type = getattr(fetcher, 'last_error_type', None)
                if error_type == "not_found":
                    return f"Error: Ticker '{ticker}' not found. Please verify the symbol is correct (e.g., NFLX, not Netflix)."
                elif error_type == "auth_failure":
                    return f"Error: Financial data API authentication failed. Please check your FINANCIAL_DATASETS_API_KEY."
                else:
                    return f"Error: Temporary API failure — could not retrieve data for '{ticker}'. Please try again in a moment."

            if not key_metrics:
                return f"Error: Financial metrics temporarily unavailable for {ticker}. Please try again."

            # Build response
            result = f"**{stock_info.get('company_name', ticker)} ({ticker})**\n\n"

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
                result += f"**Current Price:** ${stock_info.get('current_price', 'N/A')}\n"

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
                price = stock_info.get('current_price') or 0
                net_income = key_metrics.get('latest_net_income') or 0
                shares = key_metrics.get('shares_outstanding') or 1  # Use 'or' to handle both None and 0
                if price > 0 and net_income > 0 and shares > 0:
                    eps = net_income / shares
                    pe = price / eps
                    result += f"**P/E Ratio:** {pe:.2f}x\n"
                else:
                    result += f"**P/E Ratio:** N/A\n"

            if show_all or 'margins' in requested_metrics:
                revenue = key_metrics.get('latest_revenue', 0)
                net_income = key_metrics.get('latest_net_income', 0)
                ebit = key_metrics.get('latest_ebit', 0)
                da = key_metrics.get('latest_depreciation_amortization', 0)
                fcf = key_metrics.get('latest_fcf', 0)

                if revenue > 0:
                    # Calculate and display all margins
                    result += f"**CURRENT MARGINS (Latest Year):**\n"

                    # EBITDA Margin
                    if ebit and da:
                        ebitda = ebit + da
                        ebitda_margin = (ebitda / revenue) * 100
                        result += f"  EBITDA Margin: {ebitda_margin:.1f}%\n"

                    # EBIT/Operating Margin
                    if ebit:
                        ebit_margin = (ebit / revenue) * 100
                        result += f"  EBIT/Operating Margin: {ebit_margin:.1f}%\n"

                    # Net Profit Margin
                    if net_income:
                        net_margin = (net_income / revenue) * 100
                        result += f"  Net Profit Margin: {net_margin:.1f}%\n"

                    # FCF Margin
                    if fcf:
                        fcf_margin = (fcf / revenue) * 100
                        result += f"  FCF Margin: {fcf_margin:.1f}%\n"

                # Historical margins (last 5 years) - show all types
                hist_revenue = key_metrics.get('historical_revenue', [])
                hist_net_income = key_metrics.get('historical_net_income', [])
                hist_ebit = key_metrics.get('historical_ebit', [])
                hist_years = key_metrics.get('historical_years', [])

                if len(hist_revenue) > 0 and len(hist_revenue) == len(hist_net_income):
                    result += f"\n**HISTORICAL MARGINS:**\n"

                    for i in range(len(hist_revenue)):
                        rev = hist_revenue[i]
                        if rev <= 0:
                            continue

                        # Get year label
                        if i < len(hist_years) and hist_years[i]:
                            year_label = hist_years[i]
                        else:
                            year_label = f"Year {i+1}" if i > 0 else "Latest"

                        margins_str = f"  {year_label}:"

                        # EBIT margin (if available)
                        if i < len(hist_ebit) and hist_ebit[i]:
                            ebit_margin = (hist_ebit[i] / rev) * 100
                            margins_str += f" EBIT: {ebit_margin:.1f}%,"

                        # Net margin
                        if i < len(hist_net_income) and hist_net_income[i]:
                            net_margin = (hist_net_income[i] / rev) * 100
                            margins_str += f" Net: {net_margin:.1f}%"

                        result += margins_str + "\n"

            if show_all or 'growth' in requested_metrics:
                # Calculate growth rates from historical data
                hist_revenue = key_metrics.get('historical_revenue', [])
                hist_fcf = key_metrics.get('historical_fcf', [])

                # Revenue CAGR - requires both endpoints to be positive
                if len(hist_revenue) >= 2 and hist_revenue[0] > 0 and hist_revenue[-1] > 0:
                    rev_cagr = ((hist_revenue[0] / hist_revenue[-1]) ** (1 / (len(hist_revenue) - 1)) - 1) * 100
                    result += f"**Revenue CAGR ({len(hist_revenue)-1}Y):** {rev_cagr:.1f}%\n"
                elif len(hist_revenue) >= 2:
                    result += f"**Revenue CAGR:** N/A (negative or zero values in history)\n"

                # FCF CAGR - requires both endpoints to be positive
                if len(hist_fcf) >= 2 and hist_fcf[0] > 0 and hist_fcf[-1] > 0:
                    fcf_cagr = ((hist_fcf[0] / hist_fcf[-1]) ** (1 / (len(hist_fcf) - 1)) - 1) * 100
                    result += f"**FCF CAGR ({len(hist_fcf)-1}Y):** {fcf_cagr:.1f}%\n"
                elif len(hist_fcf) >= 2:
                    result += f"**FCF CAGR:** N/A (negative or zero values in history)\n"

            try:
                _hist_years = list(reversed(key_metrics.get('historical_years', [])))
                _hist_rev = list(reversed(key_metrics.get('historical_revenue', [])))
                _hist_gp = list(reversed(key_metrics.get('historical_gross_profit', [])))

                # Chart 1: Revenue history (bar)
                _chart_data = [
                    {"period": str(_hist_years[i]), "revenue_b": round(_hist_rev[i] / 1e9, 2)}
                    for i in range(min(len(_hist_years), len(_hist_rev)))
                    if _hist_rev[i]
                ]
                if _chart_data:
                    chart_id = f"quick_data_{ticker}"
                    chart_json = json.dumps({
                        "id": chart_id,
                        "chart_type": "bar",
                        "title": f"{ticker} Revenue History ($B)",
                        "data": _chart_data,
                        "series": [
                            {"key": "revenue_b", "label": "Revenue ($B)", "type": "bar", "color": "#2563EB"}
                        ],
                        "y_format": "currency_b"
                    })
                    result += f"\n---CHART_DATA:{chart_id}---\n{chart_json}\n---END_CHART_DATA:{chart_id}---\n[CHART_INSTRUCTION: Place {{{{CHART:{chart_id}}}}} on its own line where you discuss revenue history. Do NOT reproduce the CHART_DATA block.]"

                # Chart 2: Revenue vs Cost of Revenue (grouped bar + gross profit line)
                _cost_data = [
                    {
                        "period": str(_hist_years[i]),
                        "revenue_b": round(_hist_rev[i] / 1e9, 2),
                        "cost_b": round((_hist_rev[i] - _hist_gp[i]) / 1e9, 2),
                        "gross_profit_b": round(_hist_gp[i] / 1e9, 2),
                    }
                    for i in range(min(len(_hist_years), len(_hist_rev), len(_hist_gp)))
                    if _hist_rev[i] and _hist_gp[i]
                ]
                if _cost_data:
                    cost_chart_id = f"revenue_vs_cost_{ticker}"
                    cost_chart_json = json.dumps({
                        "id": cost_chart_id,
                        "chart_type": "bar_line",
                        "title": f"{ticker} Revenue vs Cost of Revenue ($B)",
                        "data": _cost_data,
                        "series": [
                            {"key": "revenue_b", "label": "Revenue ($B)", "type": "bar", "color": "#2563EB", "yAxis": "left"},
                            {"key": "cost_b", "label": "Cost of Revenue ($B)", "type": "bar", "color": "#EF4444", "yAxis": "left"},
                            {"key": "gross_profit_b", "label": "Gross Profit ($B)", "type": "line", "color": "#10B981", "yAxis": "right"},
                        ],
                        "y_format": "currency_b",
                        "y_right_format": "currency_b"
                    })
                    result += f"\n---CHART_DATA:{cost_chart_id}---\n{cost_chart_json}\n---END_CHART_DATA:{cost_chart_id}---\n[CHART_INSTRUCTION: Place {{{{CHART:{cost_chart_id}}}}} on its own line where you compare revenue vs cost or discuss gross profit. Do NOT reproduce the CHART_DATA block.]"
            except Exception:
                pass

            return result.strip()

        except Exception as e:
            return f"Error retrieving quick data for {ticker}: {str(e)}"

    async def _arun(self, ticker: str, metrics: str) -> str:
        # Run sync code in thread pool to avoid blocking event loop
        return await asyncio.to_thread(self._run, ticker, metrics)


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
                # Common metric abbreviations to exclude from ticker detection
                metric_abbreviations = {
                    'P', 'E', 'S', 'B', 'V',  # Single letters from P/E, P/S, P/B, EV
                    'PE', 'PS', 'PB', 'EV', 'FCF',  # Common ratio abbreviations
                    'ROE', 'ROA', 'ROI', 'ROIC',  # Return metrics
                    'EPS', 'BPS', 'DPS',  # Per-share metrics
                    'EBIT', 'EBITDA', 'D', 'A',  # Earnings metrics
                    'CAGR', 'YOY', 'QOQ', 'MOM',  # Growth metrics
                    'PEG', 'NAV', 'DCF', 'NPV', 'IRR',  # Valuation metrics
                    'FOR', 'THE', 'AND', 'FROM', 'TO', 'OF', 'IN', 'IS', 'AT'  # Common words
                }
                # Find all potential tickers (min 2 chars - real tickers are 2-5 chars)
                # and filter out metric abbreviations
                potential_tickers = re.findall(r'\b([A-Z]{2,5})\b', calculation)
                for match in potential_tickers:
                    if match not in metric_abbreviations:
                        ticker = match
                        break

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
                    error_type = getattr(fetcher, 'last_error_type', None)
                    if error_type == "not_found":
                        return f"Error: Ticker '{ticker}' not found. Please verify the symbol is correct."
                    return f"Error: Temporary API failure — could not retrieve data for '{ticker}'. Please try again."

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
                    # Validate both endpoints are positive before calculating growth
                    if len(hist_revenue) >= 2 and hist_revenue[0] > 0 and hist_revenue[-1] > 0 and net_income > 0 and shares > 0:
                        eps = net_income / shares
                        pe = price / eps if eps > 0 else 0
                        # Calculate revenue growth rate (safe - both endpoints validated positive)
                        growth = ((hist_revenue[0] / hist_revenue[-1]) ** (1 / (len(hist_revenue) - 1)) - 1) * 100
                        peg = pe / growth if growth > 0 else None
                        if peg:
                            return f"**PEG Ratio for {ticker}:**\n- P/E: {pe:.2f}x\n- Revenue Growth: {growth:.1f}%\n- **PEG: {peg:.2f}**\n(PEG < 1 may indicate undervaluation relative to growth)"
                    return f"Cannot calculate PEG for {ticker} (missing earnings or growth data, or negative revenue history)"

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
        # Run sync code in thread pool to avoid blocking event loop
        return await asyncio.to_thread(self._run, calculation, ticker)


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
            company_name = stock_info.get('company_name', ticker) if stock_info else ticker

            # Get recent financial metrics for context
            metrics = fetcher.get_key_metrics(ticker)
            # Use 'or 0' to handle None values (get() returns None if key exists with None value)
            current_price = (stock_info.get('current_price') or 0) if stock_info else 0
            market_cap = (stock_info.get('market_cap') or 0) if stock_info else 0

            # Use Tavily to search for comprehensive news
            tavily = get_tavily_client()

            # Build search query
            if query:
                search_query = f"{company_name} ({ticker}) {query} news"
            else:
                search_query = f"{company_name} ({ticker}) recent news earnings developments analyst coverage"

            result = tavily.search(
                query=search_query,
                topic="news",
                search_depth="advanced",
                max_results=10,
                include_answer="advanced",
                time_range="month",
            )

            answer = result.get("answer", "No news summary available.")
            sources = result.get("results", [])

            # Build comprehensive response with context
            output = f"# News & Developments: {company_name} ({ticker})\n\n"

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
            output += answer

            # Add sources at the end
            if sources:
                output += "\n\n---\n\n## Sources\n\n"
                for source in sources:
                    title = source.get("title", "Source")
                    url = source.get("url", "")
                    output += f"- [{title}]({url})\n"

            return output

        except Exception as e:
            return f"Error getting news for {ticker}: {str(e)}"

    async def _arun(self, ticker: str, query: Optional[str] = None) -> str:
        # Run sync code in thread pool to avoid blocking event loop
        return await asyncio.to_thread(self._run, ticker, query)


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
    Use this when the user wants to compare two companies or asks "vs" questions.
    Always generates a multi-line revenue history chart automatically.

    Comparison categories:
    - valuation: P/E, P/S, market cap
    - profitability: Margins, ROE, FCF
    - growth: Revenue growth, earnings growth
    - size: Revenue, market cap, employees
    - all: Complete comparison

    Input must be valid JSON with ticker1, ticker2, and optionally metrics.
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
                error_type = getattr(fetcher, 'last_error_type', None)
                if error_type == "not_found":
                    return f"Error: Ticker '{ticker1}' not found. Please verify the symbol is correct."
                return f"Error: Temporary API failure — could not retrieve data for '{ticker1}'. Please try again."

            if not info2 or not metrics2:
                error_type = getattr(fetcher, 'last_error_type', None)
                if error_type == "not_found":
                    return f"Error: Ticker '{ticker2}' not found. Please verify the symbol is correct."
                return f"Error: Temporary API failure — could not retrieve data for '{ticker2}'. Please try again."

            name1 = info1.get('company_name', ticker1)
            name2 = info2.get('company_name', ticker2)

            result = f"**Company Comparison: {name1} vs {name2}**\n\n"

            categories = [m.strip().lower() for m in metrics.split(',')]
            show_all = 'all' in categories

            # Initialize variables that may be used in OVERALL INSIGHT section
            # These will be set in their respective category blocks if those categories are requested
            pe1, pe2 = None, None
            fcf_margin1, fcf_margin2 = 0, 0
            rev_cagr1, rev_cagr2 = 0, 0

            # Extract common metrics used across multiple sections
            # Use 'or 0' to handle both None values and missing keys
            mcap1 = info1.get('market_cap') or 0
            mcap2 = info2.get('market_cap') or 0
            rev1 = metrics1.get('latest_revenue') or 0
            rev2 = metrics2.get('latest_revenue') or 0

            # Size comparison with winner
            if show_all or 'size' in categories:

                result += "**SIZE & SCALE:**\n"
                result += f"- Market Cap: ${mcap1/1e9:.1f}B vs ${mcap2/1e9:.1f}B"
                if mcap1 > 0 and mcap2 > 0 and mcap1 > mcap2:
                    result += f" → **{ticker1} larger** ({mcap1/mcap2:.1f}x)\n"
                elif mcap1 > 0 and mcap2 > 0:
                    result += f" → **{ticker2} larger** ({mcap2/mcap1:.1f}x)\n"

                result += f"- Revenue (TTM): ${rev1/1e9:.1f}B vs ${rev2/1e9:.1f}B"
                if rev1 > 0 and rev2 > 0 and rev1 > rev2:
                    result += f" → **{ticker1} larger** ({rev1/rev2:.1f}x)\n"
                elif rev1 > 0 and rev2 > 0:
                    result += f" → **{ticker2} larger** ({rev2/rev1:.1f}x)\n"
                else:
                    result += "\n"

                size_winner = ticker1 if (mcap1 > mcap2 and rev1 > rev2) else ticker2 if (mcap2 > mcap1 and rev2 > rev1) else "Mixed"
                result += f"**Winner: {size_winner}** (larger business)\n\n"

            # Valuation comparison with winner
            if show_all or 'valuation' in categories:
                # P/E ratios - use 'or' to handle None values
                ni1 = metrics1.get('latest_net_income') or 0
                ni2 = metrics2.get('latest_net_income') or 0
                shares1 = metrics1.get('shares_outstanding') or 1
                shares2 = metrics2.get('shares_outstanding') or 1
                price1 = info1.get('current_price') or 0
                price2 = info2.get('current_price') or 0

                eps1 = ni1 / shares1 if shares1 > 0 else 0
                eps2 = ni2 / shares2 if shares2 > 0 else 0
                pe1 = price1 / eps1 if eps1 > 0 else None
                pe2 = price2 / eps2 if eps2 > 0 else None

                # P/S ratios (mcap1, mcap2 already defined above)
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
                fcf1 = metrics1.get('latest_fcf') or 0
                fcf2 = metrics2.get('latest_fcf') or 0
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

                # Safe CAGR calculation - requires both endpoints to be positive
                def safe_cagr(data):
                    if len(data) >= 2 and data[0] > 0 and data[-1] > 0:
                        return ((data[0] / data[-1]) ** (1 / (len(data) - 1)) - 1) * 100
                    return None

                rev_cagr1 = safe_cagr(hist_rev1)
                rev_cagr2 = safe_cagr(hist_rev2)

                result += "**GROWTH (Historical CAGR):**\n"
                if rev_cagr1 is not None and rev_cagr2 is not None:
                    result += f"- Revenue Growth: {rev_cagr1:.1f}% vs {rev_cagr2:.1f}%"
                    result += f" → **{ticker1 if rev_cagr1 > rev_cagr2 else ticker2} growing faster**\n"
                else:
                    rev_cagr1 = rev_cagr1 or 0
                    rev_cagr2 = rev_cagr2 or 0
                    result += f"- Revenue Growth: {rev_cagr1:.1f}% vs {rev_cagr2:.1f}% (some data unavailable)\n"

                fcf_cagr1 = safe_cagr(hist_fcf1)
                fcf_cagr2 = safe_cagr(hist_fcf2)
                if fcf_cagr1 is not None and fcf_cagr2 is not None:
                    result += f"- FCF Growth: {fcf_cagr1:.1f}% vs {fcf_cagr2:.1f}%"
                    result += f" → **{ticker1 if fcf_cagr1 > fcf_cagr2 else ticker2} faster**\n"

                # Use 0 as fallback for winner calculation
                rev_cagr1 = rev_cagr1 if rev_cagr1 is not None else 0
                rev_cagr2 = rev_cagr2 if rev_cagr2 is not None else 0
                growth_winner = ticker1 if rev_cagr1 > rev_cagr2 else ticker2
                result += f"**Winner: {growth_winner}** (faster growth)\n\n"

            # Overall insight (only if showing all or multiple categories)
            if show_all or len(categories) > 1:
                result += "**OVERALL INSIGHT:**\n"

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

            # Emit historical revenue comparison chart
            try:
                _hr1 = metrics1.get('historical_revenue', [])
                _hr2 = metrics2.get('historical_revenue', [])
                _hy1 = metrics1.get('historical_years', [])
                _hy2 = metrics2.get('historical_years', [])
                _rev_map1 = {y: r for y, r in zip(_hy1, _hr1) if r}
                _rev_map2 = {y: r for y, r in zip(_hy2, _hr2) if r}
                _common_years = sorted(y for y in (set(_rev_map1) & set(_rev_map2)))
                _k1 = ticker1.lower()
                _k2 = ticker2.lower()
                _chart_rows = [
                    {"period": y, _k1: round(_rev_map1[y] / 1e9, 2), _k2: round(_rev_map2[y] / 1e9, 2)}
                    for y in _common_years
                ]
                if len(_chart_rows) >= 2:
                    _cid = f"revenue_compare_{ticker1}_{ticker2}"
                    _chart = {
                        "id": _cid,
                        "chart_type": "multi_line",
                        "title": f"{name1} vs {name2} — Revenue History ($B)",
                        "data": _chart_rows,
                        "series": [
                            {"key": _k1, "label": f"{name1} ($B)", "type": "line", "color": "#2563EB", "yAxis": "left"},
                            {"key": _k2, "label": f"{name2} ($B)", "type": "line", "color": "#10B981", "yAxis": "left"},
                        ],
                        "x_key": "period",
                        "y_format": "currency_b",
                    }
                    result += f"\n---CHART_DATA:{_cid}---\n{json.dumps(_chart)}\n---END_CHART_DATA:{_cid}---"
                    result += f"\n[CHART_INSTRUCTION: Place {{{{CHART:{_cid}}}}} on its own line where you discuss revenue history or the overall comparison. Do NOT reproduce the CHART_DATA block.]"
            except Exception:
                pass

            return result.strip()

        except Exception as e:
            logger.error(f"Comparison error: {e}", exc_info=True)
            return f"Error comparing companies: {str(e)}. Please verify both tickers are valid."

    async def _arun(self, ticker1: str, ticker2: str, metrics: str = "valuation,profitability,growth") -> str:
        # Run sync code in thread pool to avoid blocking event loop
        return await asyncio.to_thread(self._run, ticker1, ticker2, metrics)


class DateContextInput(BaseModel):
    """Input for date context lookup"""
    query: str = Field(
        description="Time period query like 'last year', 'last 5 years', 'previous quarter', 'last month', 'YTD', or 'recent'"
    )


class DateContextTool(BaseTool):
    """Tool for understanding date context and financial reporting periods"""

    name: str = "get_date_context"
    description: str = """Get current date and interpret time period queries for financial analysis.

    Use this tool when the user asks about:
    - "last year" / "previous year" / "past year"
    - "last X years" (e.g., "last 5 years")
    - "last quarter" / "previous quarter"
    - "last month" / "recent" / "latest"
    - "YTD" (year to date)
    - Any relative time reference

    This tool helps you understand:
    - What is today's date
    - What fiscal periods the user is referring to
    - What financial data is likely available given reporting lag
    - How to interpret relative time references correctly

    Input: Time period query (e.g., "last 5 years", "previous quarter", "YTD")
    Output: Detailed date context including what data periods to request
    """
    args_schema: type[BaseModel] = DateContextInput

    def _run(self, query: str) -> str:
        """Get date context for financial queries"""
        from datetime import datetime
        import calendar

        # Get current date
        now = datetime.now()
        current_year = now.year
        current_month = now.month
        current_day = now.day

        # Calculate current quarter
        current_quarter = (current_month - 1) // 3 + 1

        # Previous quarter
        if current_quarter == 1:
            prev_quarter = 4
            prev_quarter_year = current_year - 1
        else:
            prev_quarter = current_quarter - 1
            prev_quarter_year = current_year

        # Reporting lag: Quarters typically reported 45-60 days after quarter end
        # Q1 (Jan-Mar): Reported in May
        # Q2 (Apr-Jun): Reported in August
        # Q3 (Jul-Sep): Reported in November
        # Q4 (Oct-Dec): Reported in Feb/March

        # Determine what data is likely available based on reporting lag
        # Q1 (Jan-Mar) reported in May, Q2 (Apr-Jun) in Aug, Q3 (Jul-Sep) in Nov, Q4 (Oct-Dec) in Feb/Mar
        if current_month <= 2:
            # Jan-Feb: Q3 of previous year is latest available (Q4 not yet reported)
            latest_available_quarter = "Q3"
            latest_available_year = current_year - 1
        elif current_month <= 4:
            # Mar-Apr: Q4 of previous year is now available
            latest_available_quarter = "Q4"
            latest_available_year = current_year - 1
        elif current_month <= 7:
            # May-Jul: Q1 of current year is available
            latest_available_quarter = "Q1"
            latest_available_year = current_year
        elif current_month <= 10:
            # Aug-Oct: Q2 of current year is available
            latest_available_quarter = "Q2"
            latest_available_year = current_year
        else:
            # Nov-Dec: Q3 of current year is available
            latest_available_quarter = "Q3"
            latest_available_year = current_year

        # Parse query
        query_lower = query.lower()

        result = []
        result.append(f"**DATE CONTEXT**")
        result.append(f"\n**Current Date:** {now.strftime('%B %d, %Y')}")
        result.append(f"**Current Quarter:** Q{current_quarter} {current_year}")
        result.append(f"**Latest Likely Available Data:** {latest_available_quarter} {latest_available_year}")
        result.append(f"\n---")

        # Interpret the query
        result.append(f"\n**Interpreting: \"{query}\"**\n")

        if any(word in query_lower for word in ["last year", "previous year", "past year"]):
            result.append(f"➜ **\"Last Year\"** = Full fiscal year {current_year - 1}")
            result.append(f"  • Use annual data from {current_year - 1}")
            result.append(f"  • This data is complete and fully reported")

        elif "last" in query_lower and "years" in query_lower:
            # Extract number
            import re
            match = re.search(r'(\d+)\s*years', query_lower)
            if match:
                num_years = int(match.group(1))
                start_year = current_year - num_years
                end_year = current_year - 1
                result.append(f"➜ **\"Last {num_years} Years\"** = {start_year} to {end_year}")
                result.append(f"  • Use annual data from years: {', '.join(str(y) for y in range(start_year, end_year + 1))}")
                result.append(f"  • All this historical data is fully reported")
            else:
                result.append(f"➜ Could not extract number of years from query")

        elif any(word in query_lower for word in ["last quarter", "previous quarter", "past quarter"]):
            result.append(f"➜ **\"Last Quarter\"** = Q{prev_quarter} {prev_quarter_year}")
            if prev_quarter >= current_quarter or prev_quarter_year < current_year:
                result.append(f"  • This data is likely fully reported")
            else:
                result.append(f"  • This data may still be pending - use Q{latest_available_quarter} {latest_available_year} instead")

        elif any(word in query_lower for word in ["ytd", "year to date", "year-to-date"]):
            result.append(f"➜ **\"YTD\" (Year to Date)** = January 1, {current_year} to {now.strftime('%B %d, %Y')}")
            result.append(f"  • Use data from {current_year} through {latest_available_quarter}")
            result.append(f"  • Latest available: {latest_available_quarter} {current_year}")

        elif any(word in query_lower for word in ["recent", "latest", "current", "last month"]):
            result.append(f"➜ **\"Recent/Latest\"** = Most recently reported data")
            result.append(f"  • Latest available quarter: {latest_available_quarter} {latest_available_year}")
            result.append(f"  • Latest annual data: Year {current_year - 1}")

        else:
            result.append(f"➜ General interpretation:")
            result.append(f"  • For annual data: Use year {current_year - 1} (most recent complete year)")
            result.append(f"  • For quarterly data: Use {latest_available_quarter} {latest_available_year}")

        # Add reporting schedule context
        result.append(f"\n---")
        result.append(f"\n**REPORTING SCHEDULE (Typical for Public Companies)**")
        result.append(f"\n• **Q1** (Jan-Mar): Reported in **May**")
        result.append(f"• **Q2** (Apr-Jun): Reported in **August**")
        result.append(f"• **Q3** (Jul-Sep): Reported in **November**")
        result.append(f"• **Q4** (Oct-Dec): Reported in **February/March** of next year")

        result.append(f"\n\n**RECOMMENDATION**")
        result.append(f"\nFor queries about \"{query}\":")

        if "years" in query_lower:
            import re
            match = re.search(r'(\d+)\s*years', query_lower)
            if match:
                num_years = int(match.group(1))
                start_year = current_year - num_years
                end_year = current_year - 1
                result.append(f"• Request **annual financials** for years **{start_year}-{end_year}**")
                result.append(f"• Use tools with parameters covering this period")
        elif any(word in query_lower for word in ["last year", "previous year"]):
            result.append(f"• Request **annual financials** for **{current_year - 1}**")
        elif "quarter" in query_lower:
            result.append(f"• Request **quarterly data** for **{latest_available_quarter} {latest_available_year}**")
        else:
            result.append(f"• Request **{latest_available_quarter} {latest_available_year}** quarterly data")
            result.append(f"• Or request **{current_year - 1}** annual data")

        return "\n".join(result)

    async def _arun(self, query: str) -> str:
        # Run sync code in thread pool to avoid blocking event loop
        return await asyncio.to_thread(self._run, query)


class RevenueSegmentInput(BaseModel):
    ticker: str = Field(description="Stock ticker symbol (e.g., 'AAPL')")


class GetRevenueSegmentsTool(BaseTool):
    """Fetches revenue breakdown by product/geographic segment and emits a pie chart."""
    name: str = "get_revenue_segments"
    description: str = """Get a company's revenue breakdown by product or geographic segment.
    Use this when the user asks about revenue mix, segment breakdown, product revenue, geographic revenue, or wants a pie chart of revenue.
    Returns a pie chart showing each segment's contribution to total revenue.
    Examples: 'Show me Apple revenue by product', 'What is Amazon's revenue breakdown?', 'pie chart of MSFT segments'
    """
    args_schema: type[BaseModel] = RevenueSegmentInput

    def _run(self, ticker: str) -> str:
        import re
        ticker = ticker.strip().upper()

        fetcher = FinancialDataFetcher()
        stock_info = fetcher.get_stock_info(ticker)
        company_name = stock_info.get('company_name', ticker) if stock_info else ticker

        tavily = get_tavily_client()
        search_query = f"{company_name} {ticker} revenue breakdown by segment product line fiscal year billions"
        raw = tavily.search_text(
            query=search_query,
            topic="finance",
            search_depth="advanced",
            max_results=5,
            include_answer="advanced",
        )

        result = f"**{company_name} ({ticker}) Revenue by Segment**\n\n{raw}\n"

        # Parse dollar amounts: "Services $96.2B", "iPhone: $200.6 billion", "Services revenue of $85B"
        dollar_pattern = re.compile(
            r'([A-Za-z][A-Za-z &/\-]{1,30}?)\s*(?:revenue|sales|segment)?\s*[:\-–]?\s*\$\s*([\d,]+(?:\.\d+)?)\s*(billion|million|B|M|bn|m)\b',
            re.IGNORECASE,
        )
        segments: list[dict] = []
        seen: set[str] = set()
        for m in dollar_pattern.finditer(raw):
            label = m.group(1).strip().rstrip(':–-').strip()
            value = float(m.group(2).replace(',', ''))
            unit = m.group(3).lower()
            if unit in ('million', 'm'):
                value /= 1000  # convert to billions
            key = label.lower()
            if key not in seen and value > 0:
                seen.add(key)
                segments.append({"label": label, "value": round(value, 1)})

        # Fallback: parse percentages if no dollar amounts found
        if len(segments) < 2:
            pct_pattern = re.compile(
                r'([A-Za-z][A-Za-z &/\-]{1,30}?)\s*[:\-–]\s*([\d]+(?:\.\d+)?)\s*%',
                re.IGNORECASE,
            )
            seen.clear()
            segments = []
            for m in pct_pattern.finditer(raw):
                label = m.group(1).strip().rstrip(':–-').strip()
                value = float(m.group(2))
                key = label.lower()
                if key not in seen and 0 < value < 100:
                    seen.add(key)
                    segments.append({"label": label, "value": round(value, 1)})

        # Only emit a pie chart if we have at least 2 meaningful segments
        if len(segments) >= 2:
            # Sort largest first, cap at 8 segments for readability
            segments.sort(key=lambda x: x["value"], reverse=True)
            segments = segments[:8]
            chart_id = f"revenue_segments_{ticker}"
            unit_label = "% of revenue" if sum(s["value"] for s in segments) <= 101 else "$B revenue"
            chart_spec = json.dumps({
                "id": chart_id,
                "chart_type": "pie",
                "title": f"{ticker} Revenue by Segment",
                "subtitle": unit_label,
                "data": segments,
            })
            result += f"\n---CHART_DATA:{chart_id}---\n{chart_spec}\n---END_CHART_DATA:{chart_id}---"
            result += f"\n[CHART_INSTRUCTION: Place {{{{CHART:{chart_id}}}}} on its own line where you discuss the revenue breakdown. Do NOT reproduce the CHART_DATA block.]"

        return result

    async def _arun(self, ticker: str) -> str:
        return await asyncio.to_thread(self._run, ticker)


class MultiCompanyInput(BaseModel):
    tickers: str = Field(description="Comma-separated list of 2–8 ticker symbols, e.g. 'AAPL,MSFT,GOOGL,AMZN'")
    metric: Optional[str] = Field(
        default="revenue",
        description="Metric to compare: 'revenue' (default), 'market_cap', 'fcf_margin', or 'growth'"
    )


class CompareMultipleCompaniesTool(BaseTool):
    """Compare 2-8 companies on a single visual bar chart"""

    name: str = "compare_multiple_companies"
    description: str = """Compare 2–8 companies side-by-side with a visual chart. Generates charts automatically.

    Use this when the user asks to compare multiple companies, wants any kind of comparison chart,
    or asks for a line graph / bar chart comparing companies.

    Chart types generated:
    - metric='revenue' (default) → bar chart comparing latest revenue
    - metric='market_cap'        → bar chart comparing market capitalizations
    - metric='fcf_margin'        → bar chart comparing FCF margins
    - metric='growth'            → bar chart comparing revenue CAGR
    - metric='revenue_history'   → multi-line chart showing revenue over time for all companies

    Examples:
    - 'Compare revenue of Amazon, Microsoft, Google' → use metric='revenue'
    - 'Line graph of AAPL vs MSFT revenue over time' → use metric='revenue_history'
    - 'Show FAANG market caps' → use metric='market_cap'

    Input: comma-separated tickers like 'AAPL,MSFT,GOOGL,AMZN'
    """
    args_schema: type[BaseModel] = MultiCompanyInput

    def _run(self, tickers: str, metric: str = "revenue") -> str:
        try:
            ticker_list = [t.strip().upper() for t in tickers.split(',') if t.strip()]
            if len(ticker_list) < 2:
                return "Error: Please provide at least 2 tickers separated by commas."
            ticker_list = ticker_list[:8]

            fetcher = FinancialDataFetcher()
            COLORS = ["#2563EB", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#EC4899", "#14B8A6", "#F97316"]

            # Fetch data for all tickers up front
            company_data = []
            failed = []
            for tick in ticker_list:
                try:
                    info = fetcher.get_stock_info(tick)
                    m = fetcher.get_key_metrics(tick)
                    if not info or not m:
                        failed.append(tick)
                        continue
                    company_data.append((tick, info, m))
                except Exception:
                    failed.append(tick)

            if len(company_data) < 2:
                return f"Error: Could not retrieve enough data. Failed tickers: {', '.join(failed) or 'none'}"

            # ── revenue_history: multi-line chart over time ──────────────────
            if metric == "revenue_history":
                hist_map = {}
                all_years = set()
                text_lines = []
                for tick, info, m in company_data:
                    name = info.get('company_name', tick)
                    hist_rev   = m.get('historical_revenue', [])
                    hist_years = m.get('historical_years', [])
                    rev_map = {y: r for y, r in zip(hist_years, hist_rev) if r}
                    hist_map[tick] = {"name": name, "rev_map": rev_map}
                    all_years.update(rev_map.keys())
                    if hist_rev:
                        text_lines.append(f"- **{name}** ({tick}): latest revenue ${hist_rev[0]/1e9:.1f}B")

                common_years = sorted(all_years)
                chart_rows = []
                for y in common_years:
                    row: dict = {"period": y}
                    for tick, _, _ in company_data:
                        rv = hist_map[tick]["rev_map"].get(y)
                        if rv:
                            row[tick.lower()] = round(rv / 1e9, 2)
                    chart_rows.append(row)

                if len(chart_rows) < 2:
                    return "Error: Not enough historical revenue data to build a time-series chart."

                chart_id = f"rev_history_{'_'.join(t for t, _, _ in company_data)}"
                series = [
                    {"key": tick.lower(), "label": hist_map[tick]["name"], "type": "line",
                     "color": COLORS[i % len(COLORS)], "yAxis": "left"}
                    for i, (tick, _, _) in enumerate(company_data)
                ]
                chart_spec = {
                    "id": chart_id,
                    "chart_type": "multi_line",
                    "title": f"Revenue History ($B) — {', '.join(t for t, _, _ in company_data)}",
                    "data": chart_rows,
                    "series": series,
                    "x_key": "period",
                    "y_format": "currency_b",
                }
                result = f"**Revenue History Comparison**\n\n" + "\n".join(text_lines)
                if failed:
                    result += f"\n\n*Could not fetch: {', '.join(failed)}*"
                result += f"\n---CHART_DATA:{chart_id}---\n{json.dumps(chart_spec)}\n---END_CHART_DATA:{chart_id}---"
                result += f"\n[CHART_INSTRUCTION: Place {{{{CHART:{chart_id}}}}} on its own line where you discuss the revenue comparison. Do NOT reproduce the CHART_DATA block.]"
                return result

            # ── snapshot metrics: bar chart ──────────────────────────────────
            rows = []
            text_lines = []
            for i, (tick, info, m) in enumerate(company_data):
                name = info.get('company_name', tick)
                label = name if len(name) <= 18 else tick
                rev = m.get('latest_revenue') or 0
                mcap = info.get('market_cap') or 0
                fcf = m.get('latest_fcf') or 0
                fcf_margin = (fcf / rev * 100) if rev > 0 else 0
                hist_rev = m.get('historical_revenue', [])
                rev_cagr = None
                if len(hist_rev) >= 2 and hist_rev[-1] > 0 and hist_rev[0] > 0:
                    n = len(hist_rev) - 1
                    rev_cagr = ((hist_rev[0] / hist_rev[-1]) ** (1 / n) - 1) * 100

                if metric == "market_cap":
                    value = round(mcap / 1e9, 1)
                    text_lines.append(f"- **{name}** ({tick}): ${mcap/1e9:.1f}B market cap")
                elif metric == "fcf_margin":
                    value = round(fcf_margin, 1)
                    text_lines.append(f"- **{name}** ({tick}): {fcf_margin:.1f}% FCF margin")
                elif metric == "growth":
                    value = round(rev_cagr, 1) if rev_cagr is not None else 0
                    cagr_str = f"{rev_cagr:.1f}%" if rev_cagr is not None else "N/A"
                    text_lines.append(f"- **{name}** ({tick}): {cagr_str} revenue CAGR")
                else:
                    value = round(rev / 1e9, 1)
                    text_lines.append(f"- **{name}** ({tick}): ${rev/1e9:.1f}B revenue")
                rows.append({"company": label, "value": value})

            METRIC_LABELS = {
                "revenue": "Revenue ($B)", "market_cap": "Market Cap ($B)",
                "fcf_margin": "FCF Margin (%)", "growth": "Revenue CAGR (%)",
            }
            METRIC_FORMATS = {
                "revenue": "currency_b", "market_cap": "currency_b",
                "fcf_margin": "percent", "growth": "percent",
            }
            metric_label = METRIC_LABELS.get(metric, "Revenue ($B)")
            y_format = METRIC_FORMATS.get(metric, "currency_b")

            chart_id = f"multi_compare_{'_'.join(t for t, _, _ in company_data)}_{metric}"
            ticker_str = ", ".join(t for t, _, _ in company_data)
            chart_spec = {
                "id": chart_id,
                "chart_type": "bar",
                "title": f"{metric_label} Comparison — {ticker_str}",
                "data": rows,
                "series": [
                    {"key": "value", "label": metric_label, "type": "bar", "color": "#2563EB", "yAxis": "left"}
                ],
                "x_key": "company",
                "y_format": y_format,
            }

            result = f"**Multi-Company {metric_label} Comparison**\n\n"
            result += "\n".join(text_lines)
            if failed:
                result += f"\n\n*Could not fetch data for: {', '.join(failed)}*"
            result += f"\n---CHART_DATA:{chart_id}---\n{json.dumps(chart_spec)}\n---END_CHART_DATA:{chart_id}---"
            result += f"\n[CHART_INSTRUCTION: Place {{{{CHART:{chart_id}}}}} on its own line where you discuss the comparison. Do NOT reproduce the CHART_DATA block.]"
            return result

        except Exception as e:
            return f"Error comparing companies: {str(e)}"

    async def _arun(self, tickers: str, metric: str = "revenue") -> str:
        return await asyncio.to_thread(self._run, tickers, metric)


def get_research_assistant_tools() -> List[BaseTool]:
    """Get all research assistant tools"""
    from tools.sec_tools import GetSECFilingsTool, AnalyzeSECFilingTool, GetSECFinancialsTool
    return [
        QuickFinancialDataTool(),
        DateContextTool(),  # Temporal awareness for date queries
        FinancialCalculatorTool(),
        RecentNewsTool(),
        CompanyComparisonTool(),
        CompareMultipleCompaniesTool(),
        GetRevenueSegmentsTool(),
        GetSECFilingsTool(),
        AnalyzeSECFilingTool(),
        GetSECFinancialsTool(),
    ]
