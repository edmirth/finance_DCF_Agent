"""
Company Context Tools for DCF Analysis

Provides rich business context including company overview, recent news,
stock performance, and upcoming catalysts before financial analysis.
"""
from langchain.tools import BaseTool
from typing import Type
from pydantic import BaseModel, Field
from data.financial_data import FinancialDataFetcher
from shared.tavily_client import get_tavily_client
import logging

logger = logging.getLogger(__name__)


class CompanyContextInput(BaseModel):
    """Input for company context tool"""
    ticker: str = Field(description="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)")


class GetCompanyContextTool(BaseTool):
    """Tool to gather rich company context before financial analysis"""
    name: str = "get_company_context"
    description: str = """Gather comprehensive company context before performing financial analysis. This provides:
    - Business overview and revenue model
    - Recent news and catalysts (last 30 days)
    - Stock price performance and trends
    - Upcoming events (earnings, conferences)
    - Key business segments and geographic exposure

    Use this FIRST to understand the company's business model and recent developments
    before diving into financial metrics and DCF analysis."""
    args_schema: Type[BaseModel] = CompanyContextInput

    def _run(self, ticker: str) -> str:
        """Gather company context"""
        try:
            ticker_clean = ticker.upper().strip()

            # Get basic stock info from Financial Datasets API
            fetcher = FinancialDataFetcher()
            stock_info = fetcher.get_stock_info(ticker_clean)

            if not stock_info:
                return f"Error: Could not fetch basic information for ticker {ticker_clean}"

            company_name = stock_info.get('company_name', ticker_clean)
            sector = stock_info.get('sector', 'Unknown')
            industry = stock_info.get('industry', 'Unknown')
            market_cap = stock_info.get('market_cap', 0)
            current_price = stock_info.get('current_price', 0)

            # Format market cap for display
            if market_cap >= 1e12:
                market_cap_str = f"${market_cap/1e12:.2f}T"
            elif market_cap >= 1e9:
                market_cap_str = f"${market_cap/1e9:.2f}B"
            elif market_cap >= 1e6:
                market_cap_str = f"${market_cap/1e6:.2f}M"
            else:
                market_cap_str = f"${market_cap:,.0f}"

            # Get rich context from web search via Tavily
            try:
                tavily = get_tavily_client()
                context_query = f"{company_name} ({ticker_clean}) business model revenue segments recent news catalysts stock performance risks {sector}"
                web_context = tavily.search_text(
                    query=context_query,
                    topic="finance",
                    search_depth="advanced",
                    max_results=5,
                    include_answer="advanced",
                )
            except Exception as search_err:
                logger.warning(f"Web search failed for {ticker_clean}: {search_err}")
                web_context = "Unable to fetch detailed context from web search."

            # Combine basic info with web context
            result = f"""
Company Context for {company_name} ({ticker_clean}):

BASIC INFORMATION:
- Sector: {sector}
- Industry: {industry}
- Market Cap: {market_cap_str}
- Current Price: ${current_price:.2f}

{web_context}
"""
            return result

        except Exception as e:
            logger.error(f"Error gathering company context for {ticker}: {e}")
            return f"Error gathering company context for {ticker}: {str(e)}"

    async def _arun(self, ticker: str) -> str:
        """Async version"""
        return self._run(ticker)
