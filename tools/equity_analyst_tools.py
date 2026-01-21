"""
Specialized Tools for Equity Analyst Agent
"""
from langchain.tools import BaseTool
from typing import Optional, Type
from pydantic import BaseModel, Field
import os
from openai import OpenAI
import logging

logger = logging.getLogger(__name__)


# Input Schemas
class IndustryAnalysisInput(BaseModel):
    """Input for industry analysis tool"""
    company: str = Field(description="Company name (e.g., Apple Inc)")
    ticker: str = Field(description="Stock ticker symbol (e.g., AAPL)")
    sector: str = Field(description="Sector/Industry (e.g., Technology Hardware)")


class CompetitorAnalysisInput(BaseModel):
    """Input for competitor analysis tool"""
    company: str = Field(description="Company name (e.g., Apple Inc)")
    ticker: str = Field(default=None, description="Stock ticker symbol (e.g., AAPL)")
    industry: str = Field(default=None, description="Industry (e.g., Technology Hardware, Storage & Peripherals)")


class MoatAnalysisInput(BaseModel):
    """Input for competitive moat analysis tool"""
    company: str = Field(description="Company name (e.g., Apple Inc)")
    ticker: str = Field(description="Stock ticker symbol (e.g., AAPL)")


class ManagementAnalysisInput(BaseModel):
    """Input for management quality analysis tool"""
    company: str = Field(description="Company name (e.g., Apple Inc)")
    ticker: str = Field(description="Stock ticker symbol (e.g., AAPL)")


# Tool Implementations
class IndustryAnalysisTool(BaseTool):
    """Analyzes industry dynamics, market size, growth rates, and competitive structure"""
    name: str = "analyze_industry"
    description: str = """Performs comprehensive industry analysis including:
    - Market size and growth rates (TAM/SAM/SOM)
    - Industry structure and competitive dynamics (Porter's 5 Forces)
    - Key trends and technological shifts
    - Regulatory environment and policy impacts
    - Industry-specific metrics and benchmarks

    Use this to understand the broader context in which the company operates."""
    args_schema: Type[BaseModel] = IndustryAnalysisInput

    def _run(self, company: str, ticker: str, sector: str) -> str:
        """Analyze industry dynamics"""
        try:
            api_key = os.getenv("PERPLEXITY_API_KEY")
            if not api_key:
                return "Error: PERPLEXITY_API_KEY not found. Cannot perform industry analysis."

            client = OpenAI(api_key=api_key, base_url="https://api.perplexity.ai")

            query = f"""Provide a comprehensive industry analysis for {company} ({ticker}) in the {sector} sector:

1. Market Size & Growth:
   - Total Addressable Market (TAM)
   - Industry growth rate and projections
   - Key market segments and their growth

2. Industry Structure (Porter's 5 Forces):
   - Competitive rivalry intensity
   - Threat of new entrants
   - Bargaining power of suppliers
   - Bargaining power of buyers
   - Threat of substitutes

3. Key Industry Trends:
   - Technological innovations
   - Consumer behavior shifts
   - Regulatory changes
   - Macroeconomic factors

4. Industry Benchmarks:
   - Average profit margins
   - Typical valuation multiples (P/E, EV/EBITDA)
   - Growth rates
   - Return on capital metrics

Provide specific numbers and data points with sources."""

            response = client.chat.completions.create(
                model="sonar-pro",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert industry analyst. Provide detailed, data-driven analysis with specific metrics and cite your sources."
                    },
                    {"role": "user", "content": query}
                ],
            )

            if response.choices and len(response.choices) > 0:
                return f"Industry Analysis for {company} ({ticker}):\n\n{response.choices[0].message.content}"
            else:
                return "Error: No industry analysis results returned"

        except Exception as e:
            logger.error(f"Error in industry analysis: {e}")
            return f"Error performing industry analysis: {str(e)}"

    async def _arun(self, company: str, ticker: str, sector: str) -> str:
        return self._run(company, ticker, sector)


class CompetitorAnalysisTool(BaseTool):
    """Analyzes competitors and comparative market positioning"""
    name: str = "analyze_competitors"
    description: str = """Performs competitive analysis including:
    - Identification of top 3-5 direct competitors
    - Market share comparison and trends
    - Competitive positioning (strengths/weaknesses)
    - Product/service differentiation
    - Financial metrics comparison (margins, growth, ROIC)
    - Relative valuation multiples

    Use this to understand how the company stacks up against peers.

    Input can be provided as separate parameters or as a JSON string with keys: company, ticker, industry."""
    args_schema: Type[BaseModel] = CompetitorAnalysisInput

    def _run(self, company: str, ticker: str = None, industry: str = None) -> str:
        """Analyze competitors - handles both structured and JSON string inputs"""
        try:
            # Handle case where all params are passed as JSON string in 'company' field
            if ticker is None or industry is None:
                import json
                import re
                try:
                    # Try to parse company as JSON
                    if isinstance(company, str) and ('{' in company or company.startswith('{')):
                        # Clean up potential markdown or extra characters
                        json_str = re.sub(r'```json\s*|\s*```', '', company)
                        parsed = json.loads(json_str)
                        company = parsed.get('company', company)
                        ticker = parsed.get('ticker', ticker)
                        industry = parsed.get('industry', industry)
                except (json.JSONDecodeError, AttributeError):
                    pass

            # If still missing required fields, return error
            if not ticker or not industry:
                return f"Error: Missing required parameters. Please provide company, ticker, and industry."

            api_key = os.getenv("PERPLEXITY_API_KEY")
            if not api_key:
                return "Error: PERPLEXITY_API_KEY not found. Cannot perform competitor analysis."

            client = OpenAI(api_key=api_key, base_url="https://api.perplexity.ai")

            query = f"""Provide a comprehensive competitive analysis for {company} ({ticker}) in the {industry} industry:

1. Key Competitors:
   - Identify top 3-5 direct competitors with ticker symbols
   - Market share data for each competitor
   - Market share trends (gaining/losing)

2. Competitive Positioning:
   - {company}'s competitive strengths
   - {company}'s competitive weaknesses
   - Key differentiators vs competitors

3. Financial Comparison:
   - Revenue growth rates: {company} vs competitors
   - Profit margins comparison
   - Return on invested capital (ROIC)
   - Free cash flow generation

4. Valuation Comparison:
   - P/E ratio: {company} vs competitors
   - EV/EBITDA multiples
   - Price/Sales ratios
   - Is {company} trading at premium/discount?

5. Strategic Positioning:
   - Who is winning market share and why?
   - Which competitors are most threatening?
   - Competitive dynamics and pricing trends

Provide specific numbers and recent data with sources."""

            response = client.chat.completions.create(
                model="sonar-pro",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert competitive analyst. Provide detailed comparisons with specific metrics and cite your sources."
                    },
                    {"role": "user", "content": query}
                ],
            )

            if response.choices and len(response.choices) > 0:
                return f"Competitor Analysis for {company} ({ticker}):\n\n{response.choices[0].message.content}"
            else:
                return "Error: No competitor analysis results returned"

        except Exception as e:
            logger.error(f"Error in competitor analysis: {e}")
            return f"Error performing competitor analysis: {str(e)}"

    async def _arun(self, company: str, ticker: str = None, industry: str = None) -> str:
        return self._run(company, ticker, industry)


class MoatAnalysisTool(BaseTool):
    """Analyzes competitive advantages and economic moat"""
    name: str = "analyze_moat"
    description: str = """Analyzes the company's competitive moat (sustainable competitive advantages):
    - Brand power and customer loyalty
    - Network effects
    - Switching costs and customer lock-in
    - Cost advantages and economies of scale
    - Intangible assets (patents, licenses, regulatory barriers)
    - Pricing power
    - Moat strength rating (None/Narrow/Wide)

    Use this to assess the durability of competitive advantages."""
    args_schema: Type[BaseModel] = MoatAnalysisInput

    def _run(self, company: str, ticker: str) -> str:
        """Analyze competitive moat"""
        try:
            api_key = os.getenv("PERPLEXITY_API_KEY")
            if not api_key:
                return "Error: PERPLEXITY_API_KEY not found. Cannot perform moat analysis."

            client = OpenAI(api_key=api_key, base_url="https://api.perplexity.ai")

            query = f"""Analyze the competitive moat (sustainable competitive advantages) of {company} ({ticker}):

1. Moat Sources - Assess each:

   A. Brand Power:
   - Brand recognition and reputation
   - Customer loyalty metrics
   - Pricing premium vs competitors
   - Evidence: Net Promoter Score, brand value rankings

   B. Network Effects:
   - Does the product/service become more valuable as more people use it?
   - Examples and strength of network effects

   C. Switching Costs:
   - How difficult/expensive is it for customers to switch?
   - Lock-in mechanisms (ecosystem, data, integration)
   - Customer retention rates

   D. Cost Advantages:
   - Economies of scale
   - Proprietary technology or processes
   - Advantaged supply chain or distribution
   - Cost per unit vs competitors

   E. Intangible Assets:
   - Patents and intellectual property
   - Regulatory licenses or approvals
   - Proprietary data or technology

2. Pricing Power:
   - Can the company raise prices without losing customers?
   - Historical pricing trends
   - Price elasticity evidence

3. Moat Durability:
   - How sustainable are these advantages?
   - Threats to the moat
   - Is the moat widening or narrowing?

4. Overall Moat Rating:
   - No Moat / Narrow Moat / Wide Moat
   - Justification with evidence

Provide specific examples and data with sources."""

            response = client.chat.completions.create(
                model="sonar-pro",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert in competitive strategy and moat analysis. Assess competitive advantages critically with evidence and cite sources."
                    },
                    {"role": "user", "content": query}
                ],
            )

            if response.choices and len(response.choices) > 0:
                return f"Competitive Moat Analysis for {company} ({ticker}):\n\n{response.choices[0].message.content}"
            else:
                return "Error: No moat analysis results returned"

        except Exception as e:
            logger.error(f"Error in moat analysis: {e}")
            return f"Error performing moat analysis: {str(e)}"

    async def _arun(self, company: str, ticker: str) -> str:
        return self._run(company, ticker)


class ManagementAnalysisTool(BaseTool):
    """Analyzes management quality and capital allocation track record"""
    name: str = "analyze_management"
    description: str = """Analyzes management quality including:
    - CEO and leadership team background and track record
    - Capital allocation decisions (M&A, buybacks, dividends, R&D)
    - Insider ownership and alignment with shareholders
    - Strategic vision and execution
    - Corporate governance and transparency
    - Management compensation structure

    Use this to assess the quality of the team running the company."""
    args_schema: Type[BaseModel] = ManagementAnalysisInput

    def _run(self, company: str, ticker: str) -> str:
        """Analyze management quality"""
        try:
            api_key = os.getenv("PERPLEXITY_API_KEY")
            if not api_key:
                return "Error: PERPLEXITY_API_KEY not found. Cannot perform management analysis."

            client = OpenAI(api_key=api_key, base_url="https://api.perplexity.ai")

            query = f"""Analyze the management quality and leadership of {company} ({ticker}):

1. Leadership Team:
   - CEO name, background, tenure
   - Key executives (CFO, COO, etc.)
   - Relevant experience and track record
   - Succession planning

2. Capital Allocation Track Record:
   - Historical M&A deals and their outcomes
   - Share buyback programs and timing
   - Dividend policy and sustainability
   - R&D investment levels and innovation output
   - Debt management and capital structure decisions
   - Overall ROIC trend (improving/declining)

3. Alignment with Shareholders:
   - Insider ownership percentage
   - Recent insider buying/selling activity
   - Executive compensation structure (salary vs stock-based)
   - Vesting schedules and performance metrics

4. Strategic Vision & Execution:
   - Stated strategic priorities
   - Historical execution vs guidance
   - Product roadmap and innovation pipeline
   - Response to competitive threats

5. Governance & Transparency:
   - Board independence and quality
   - Related party transactions
   - Communication quality with shareholders
   - Accounting quality and any red flags

6. Management Quality Rating:
   - Overall assessment (Excellent/Good/Fair/Poor)
   - Key strengths and weaknesses
   - Red flags or concerns

Provide specific examples, data, and recent developments with sources."""

            response = client.chat.completions.create(
                model="sonar-pro",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert in management assessment and corporate governance. Provide balanced analysis with specific evidence and cite sources."
                    },
                    {"role": "user", "content": query}
                ],
            )

            if response.choices and len(response.choices) > 0:
                return f"Management Quality Analysis for {company} ({ticker}):\n\n{response.choices[0].message.content}"
            else:
                return "Error: No management analysis results returned"

        except Exception as e:
            logger.error(f"Error in management analysis: {e}")
            return f"Error performing management analysis: {str(e)}"

    async def _arun(self, company: str, ticker: str) -> str:
        return self._run(company, ticker)


def get_equity_analyst_tools():
    """Return list of all equity analyst tools"""
    return [
        IndustryAnalysisTool(),
        CompetitorAnalysisTool(),
        MoatAnalysisTool(),
        ManagementAnalysisTool()
    ]
