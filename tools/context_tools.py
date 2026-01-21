"""
Company Context Tools for DCF Analysis

Provides rich business context including company overview, recent news,
stock performance, and upcoming catalysts before financial analysis.
"""
from langchain.tools import BaseTool
from typing import Type
from pydantic import BaseModel, Field
from data.financial_data import FinancialDataFetcher
import os
from openai import OpenAI
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

            # Get rich context from web search
            api_key = os.getenv("PERPLEXITY_API_KEY")
            if not api_key:
                # Return basic info if no Perplexity API key
                return f"""
Company Context for {company_name} ({ticker_clean}):

BASIC INFORMATION:
- Sector: {sector}
- Industry: {industry}
- Market Cap: {market_cap_str}
- Current Price: ${current_price:.2f}

Note: PERPLEXITY_API_KEY not found. Unable to fetch detailed business context, recent news, and catalysts.
Please add PERPLEXITY_API_KEY to your .env file for comprehensive context.
"""

            client = OpenAI(api_key=api_key, base_url="https://api.perplexity.ai")

            # Query for comprehensive company context
            context_query = f"""Provide a comprehensive business context for {company_name} ({ticker_clean}):

1. BUSINESS MODEL & REVENUE STREAMS:
   - How does the company make money?
   - Key business segments and % of revenue
   - Geographic revenue breakdown
   - Recurring vs one-time revenue

2. RECENT NEWS & CATALYSTS (Last 30 days):
   - Major announcements or developments
   - Product launches or partnerships
   - Management changes or strategic shifts
   - Analyst upgrades/downgrades

3. STOCK PERFORMANCE CONTEXT:
   - Recent price trends and drivers
   - How has the stock performed YTD and vs S&P 500?
   - Any significant price movements and reasons

4. UPCOMING EVENTS & CATALYSTS:
   - Next earnings date
   - Upcoming product launches
   - Conferences or investor days
   - Regulatory decisions pending

5. KEY RISKS & CONCERNS:
   - Current market concerns about the company
   - Competitive threats
   - Regulatory or legal issues

Be specific with dates, numbers, and cite sources."""

            response = client.chat.completions.create(
                model="sonar-pro",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a financial research analyst providing business context for investment analysis. Be specific, cite sources, and focus on recent developments."
                    },
                    {"role": "user", "content": context_query}
                ],
            )

            if response.choices and len(response.choices) > 0:
                web_context = response.choices[0].message.content
            else:
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
