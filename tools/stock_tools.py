"""
General-purpose stock and financial data tools.
Provides get_stock_info, get_financial_metrics, and search_web tools
used by the Equity Analyst and other agents.
"""
from langchain.tools import BaseTool
from typing import Optional, Type
from pydantic import BaseModel, Field
from data.financial_data import FinancialDataFetcher
from shared.tavily_client import get_tavily_client
import json
import logging

logger = logging.getLogger(__name__)


# Input Schemas

class StockInfoInput(BaseModel):
    """Input for stock information tool"""
    ticker: str = Field(description="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)")


class FinancialMetricsInput(BaseModel):
    """Input for financial metrics tool"""
    ticker: str = Field(description="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)")


class WebSearchInput(BaseModel):
    """Input for web search tool"""
    query: str = Field(description="Search query to find information on the web (e.g., 'Apple revenue growth forecast', 'Tesla market share 2025')")


# Tool Implementations

class GetStockInfoTool(BaseTool):
    """Tool to get basic stock information"""
    name: str = "get_stock_info"
    description: str = "Get basic information about a stock including company name, sector, industry, market cap, and current price. Use this first to understand the company."
    args_schema: Type[BaseModel] = StockInfoInput

    def _run(self, ticker: str) -> str:
        fetcher = FinancialDataFetcher()
        info = fetcher.get_stock_info(ticker.strip().upper())

        if not info:
            return f"Error: Could not fetch information for ticker {ticker}"

        return f"""
Stock Information for {ticker.upper()}:
- Company: {info.get('company_name', 'N/A')}
- Sector: {info.get('sector', 'N/A')}
- Industry: {info.get('industry', 'N/A')}
- Market Cap: ${info.get('market_cap', 0):,.0f}
- Current Price: ${info.get('current_price', 0):.2f}
- Currency: {info.get('currency', 'USD')}
"""

    async def _arun(self, ticker: str) -> str:
        return self._run(ticker)


class GetFinancialMetricsTool(BaseTool):
    """Tool to get key financial metrics"""
    name: str = "get_financial_metrics"
    description: str = "Get key financial metrics including revenue, free cash flow, margins, valuation multiples, balance sheet data, and historical growth rates."
    args_schema: Type[BaseModel] = FinancialMetricsInput

    def _run(self, ticker: str) -> str:
        fetcher = FinancialDataFetcher()
        metrics = fetcher.get_key_metrics(ticker.strip().upper())

        if not metrics:
            return f"Error: Could not fetch financial metrics for ticker {ticker}"

        has_rev = metrics.get('latest_revenue', 0) > 0
        latest_rev = metrics.get('latest_revenue', 0) if has_rev else 0

        _gross_margin_api = metrics.get('gross_margin')
        gross_margin = _gross_margin_api if _gross_margin_api is not None else (
            metrics.get('latest_gross_profit', 0) / latest_rev if has_rev else None
        )
        _operating_margin_api = metrics.get('operating_margin')
        operating_margin = _operating_margin_api if _operating_margin_api is not None else (
            metrics.get('latest_ebit', 0) / latest_rev if has_rev else 0
        )
        _net_margin_api = metrics.get('net_margin')
        net_margin = _net_margin_api if _net_margin_api is not None else (
            metrics.get('latest_net_income', 0) / latest_rev if has_rev else 0
        )
        fcf_margin = metrics.get('latest_fcf', 0) / latest_rev if has_rev else 0

        capex_to_revenue = abs(metrics.get('latest_capex', 0) or 0) / latest_rev if has_rev else 0
        da_to_revenue = metrics.get('latest_depreciation_amortization', 0) / latest_rev if has_rev else 0
        nwc_to_revenue = metrics.get('net_working_capital', 0) / latest_rev if has_rev else 0
        total_debt_val = metrics.get('total_debt') or 0
        cost_of_debt = (
            metrics.get('latest_interest_expense', 0) / total_debt_val
            if total_debt_val > 0 else 0.05
        )

        revenue_growth = metrics.get('revenue_growth_rate') or fetcher.calculate_historical_growth_rate(
            metrics.get('historical_revenue', [])
        )
        fcf_growth = metrics.get('fcf_growth_rate') or fetcher.calculate_historical_growth_rate(
            metrics.get('historical_fcf', [])
        )
        earnings_growth = metrics.get('earnings_growth_rate')

        def pct(v):
            return f"{v * 100:.1f}%" if v is not None else "N/A"

        def dollar(v):
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

Capital Structure:
- Effective Tax Rate: {pct(metrics.get('effective_tax_rate', 0.21))}
- Interest Expense: {dollar(metrics.get('latest_interest_expense', 0))}
- Implied Cost of Debt: {cost_of_debt * 100:.2f}%
- Beta: {metrics.get('beta', 1.0):.2f}

Profitability Margins:
- Gross Margin: {pct(gross_margin)}
- Operating (EBIT) Margin: {pct(operating_margin)}
- Net Margin: {pct(net_margin)}
- FCF Margin: {pct(fcf_margin)}

Return Metrics:
- Return on Equity (ROE): {pct(metrics.get('return_on_equity'))}
- Return on Assets (ROA): {pct(metrics.get('return_on_assets'))}
- Return on Invested Capital (ROIC): {pct(metrics.get('return_on_invested_capital'))}

Valuation Multiples:
- P/E Ratio: {f"{metrics['price_to_earnings']:.1f}x" if metrics.get('price_to_earnings') else "N/A"}
- Price / Book: {f"{metrics['price_to_book']:.2f}x" if metrics.get('price_to_book') else "N/A"}
- Price / Sales: {f"{metrics['price_to_sales']:.2f}x" if metrics.get('price_to_sales') else "N/A"}
- EV / EBITDA: {f"{metrics['ev_to_ebitda']:.1f}x" if metrics.get('ev_to_ebitda') else "N/A"}
- EV / Revenue: {f"{metrics['ev_to_revenue']:.2f}x" if metrics.get('ev_to_revenue') else "N/A"}
- PEG Ratio: {f"{metrics['peg_ratio']:.2f}" if metrics.get('peg_ratio') else "N/A"}
- FCF Yield: {pct(metrics.get('fcf_yield'))}
- Enterprise Value: {dollar(metrics.get('enterprise_value_api'))}

Per-Share Metrics:
- EPS: {f"${metrics['earnings_per_share']:.2f}" if metrics.get('earnings_per_share') else "N/A"}
- Book Value / Share: {f"${metrics['book_value_per_share']:.2f}" if metrics.get('book_value_per_share') else "N/A"}
- FCF / Share: {f"${metrics['fcf_per_share']:.2f}" if metrics.get('fcf_per_share') else "N/A"}

Leverage & Liquidity:
- Debt / Equity: {f"{metrics['debt_to_equity_ratio']:.2f}x" if metrics.get('debt_to_equity_ratio') else "N/A"}
- Debt / Assets: {f"{metrics['debt_to_assets_ratio']:.2f}x" if metrics.get('debt_to_assets_ratio') else "N/A"}
- Interest Coverage: {f"{metrics['interest_coverage_ratio']:.1f}x" if metrics.get('interest_coverage_ratio') else "N/A"}
- Current Ratio: {f"{metrics['current_ratio']:.2f}" if metrics.get('current_ratio') else "N/A"}
- Quick Ratio: {f"{metrics['quick_ratio']:.2f}" if metrics.get('quick_ratio') else "N/A"}

Capital Intensity:
- CapEx / Revenue: {pct(capex_to_revenue)}
- D&A / Revenue: {pct(da_to_revenue)}
- NWC / Revenue: {pct(nwc_to_revenue)}
"""

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

                def fmt(v):
                    return f"${v/1e9:.2f}B" if abs(v) >= 1e9 else f"${v/1e6:.0f}M"

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
        return self._run(ticker)


class SearchWebTool(BaseTool):
    """Tool to search the web for current financial information"""
    name: str = "search_web"
    description: str = """Search the web for current financial information, analyst estimates, industry trends, and market data.
    Use this tool to find:
    - Analyst consensus on revenue/earnings growth rates
    - Recent company news, earnings reports, or guidance
    - Competitive analysis and market conditions
    - Industry-specific data and sector trends
    - Management commentary and strategic direction"""
    args_schema: Type[BaseModel] = WebSearchInput

    def _run(self, query: str) -> str:
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
        return self._run(query)


def get_stock_tools() -> list:
    """Return the list of general stock/financial tools."""
    return [
        GetStockInfoTool(),
        GetFinancialMetricsTool(),
        SearchWebTool(),
    ]
