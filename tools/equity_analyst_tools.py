"""
Specialized Tools for Equity Analyst Agent
"""
from langchain.tools import BaseTool
from typing import Optional, Type
from pydantic import BaseModel, Field
import logging
import os
import anthropic
from shared.tavily_client import get_tavily_client

logger = logging.getLogger(__name__)

_SEARCH_UNAVAILABLE_CAVEAT = (
    "⚠️ DATA NOTE: Real-time web search was unavailable (API quota exceeded). "
    "The following analysis is based on training knowledge (cutoff Aug 2025). "
    "Verify current figures before making trading decisions.\n\n"
)


def _knowledge_based_fallback(structure_prompt: str, company: str, ticker: str) -> str:
    """Fallback when web search is unavailable: use Claude Haiku training knowledge.

    Returns analysis clearly labeled as training-data-based so callers and the
    orchestrator can distinguish it from real-time search results.
    """
    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2500,
            messages=[{
                "role": "user",
                "content": (
                    f"Real-time web search is unavailable. Using your training knowledge "
                    f"(cutoff August 2025), provide the best available analysis for "
                    f"{company} ({ticker}).\n\n"
                    f"RULES:\n"
                    f"- Only include figures you are confident about from your training\n"
                    f"- For uncertain values write 'estimated' or 'verify current figure'\n"
                    f"- Never fabricate specific numbers you are not confident about\n"
                    f"- Do NOT include source URLs\n\n"
                    f"{structure_prompt}"
                )
            }]
        )
        return _SEARCH_UNAVAILABLE_CAVEAT + response.content[0].text.strip()
    except Exception as e:
        logger.warning(f"Knowledge fallback also failed for {ticker}: {e}")
        return (
            f"⚠️ ANALYSIS UNAVAILABLE: Web search quota exceeded and knowledge fallback "
            f"failed for {company} ({ticker}). Cannot provide this section — do NOT "
            f"fabricate or estimate data. Report this limitation explicitly."
        )


def _structure_with_llm(raw_data: str, structure_prompt: str) -> str:
    """Use Claude Haiku to extract structured, specific data from raw Tavily results.

    This converts messy web search text into clean, analyst-ready data the
    equity research agent can directly insert into its report template.
    Falls back to the raw data if the LLM call fails.
    """
    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2500,
            messages=[{
                "role": "user",
                "content": (
                    f"{structure_prompt}\n\n"
                    "IMPORTANT RULES:\n"
                    "- Only include facts actually found in the source data — never invent numbers\n"
                    "- When a specific number is missing, write 'not disclosed' rather than estimating\n"
                    "- Be concrete and specific; avoid generic statements like 'the company is growing'\n"
                    "- Do NOT include source URLs or citation markers in your output\n"
                    "- Do NOT use ASCII borders (=====, -----) — use clean Markdown only\n\n"
                    f"Raw research data:\n\n{raw_data}"
                )
            }]
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.warning(f"LLM structuring failed, using raw Tavily output: {e}")
        return raw_data


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
        structure_prompt = f"""Provide a specific industry analysis for {company} ({ticker}) in the {sector} sector.

Structure your output using these headings:

**TAM & Market Size**
State the total addressable market in dollars and projected CAGR through 2028-2030. Name the source (e.g., IDC, Gartner, company filing) if mentioned.

**Porter's Five Forces**
For each force, state the intensity (High/Medium/Low) and the specific reason:
- Competitive Rivalry: [intensity — reason]
- Threat of New Entrants: [intensity — reason]
- Supplier Power: [intensity — reason]
- Buyer Power: [intensity — reason]
- Threat of Substitutes: [intensity — reason]

**Key Industry Trends**
List 3 specific structural trends with their expected timeline and direct impact on {company}.

**Regulatory Environment**
State any relevant regulations, pending legislation, or policy tailwinds/headwinds. Say whether this is a net positive, negative, or neutral for {company}.

**Industry Benchmark Metrics**
Gross margin range, EBIT margin range, typical P/E and EV/EBITDA multiples for the sector (if found in the data)."""

        try:
            tavily = get_tavily_client()
            query = (
                f"{company} ({ticker}) {sector} industry analysis 2024 2025: "
                f"(1) Total Addressable Market size in dollars and CAGR growth rate forecast through 2028-2030, "
                f"(2) Porter's Five Forces — competitive rivalry intensity, barriers to entry, supplier power, buyer power, substitute threats with specific reasons, "
                f"(3) top 3 structural trends reshaping the industry and their timeline, "
                f"(4) key regulatory environment, policy risks or tailwinds, "
                f"(5) industry benchmark margins (gross, EBIT, net) and valuation multiples (P/E, EV/EBITDA). "
                f"Include specific dollar figures, percentages, and named sources."
            )
            raw = tavily.search_text(
                query=query,
                topic="finance",
                search_depth="advanced",
                max_results=7,
                include_answer="advanced",
            )
            return _structure_with_llm(
                raw,
                f"Extract and structure the following raw research data about {company} ({ticker}) "
                f"in the {sector} sector into a clean, specific industry analysis. "
                f"Extract only facts present in the source — do not invent numbers.\n\n"
                + structure_prompt,
            )

        except Exception as e:
            logger.warning(f"Industry analysis: Tavily unavailable ({type(e).__name__}), using knowledge fallback")
            return _knowledge_based_fallback(structure_prompt, company, ticker)

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
        # Handle case where all params are passed as JSON string in 'company' field
        if ticker is None or industry is None:
            import json
            import re
            try:
                if isinstance(company, str) and ('{' in company or company.startswith('{')):
                    json_str = re.sub(r'```json\s*|\s*```', '', company)
                    parsed = json.loads(json_str)
                    company = parsed.get('company', company)
                    ticker = parsed.get('ticker', ticker)
                    industry = parsed.get('industry', industry)
            except (json.JSONDecodeError, AttributeError):
                pass

        if not ticker or not industry:
            return "Error: Missing required parameters. Please provide company, ticker, and industry."

        structure_prompt = f"""Provide a specific competitive analysis for {company} ({ticker}) in {industry}.

Structure your output as follows:

**Market Position**
State {company}'s estimated market share and rank (e.g., "#2 in North American cloud"). State whether it is gaining or losing share, with supporting evidence.

**Top Competitors**
For each key competitor, provide a row:
| Company (Ticker) | Est. Market Share | Revenue (TTM) | Revenue Growth | EBIT Margin | P/E | EV/EBITDA |
Fill with real data. If a metric is not known, write "N/A".

**Competitive Differentiators**
What does {company} do measurably better than peers? What are its clear weaknesses vs. competitors?

**Recent Competitive Moves**
Any new entrants, M&A deals, pricing changes, or product launches that shift the competitive landscape (last 12-18 months)."""

        try:
            tavily = get_tavily_client()
            query = (
                f"{company} ({ticker}) {industry} competitive landscape 2024 2025: "
                f"(1) name the top 4-5 direct competitors with their ticker symbols and estimated market share percentages, "
                f"(2) for each competitor provide: annual revenue (TTM), revenue growth rate, EBIT or operating margin, and current P/E and EV/EBITDA multiples, "
                f"(3) who is the market share leader and is {company} gaining or losing share, "
                f"(4) key competitive differentiators — what does {company} do better or worse than peers, "
                f"(5) any recent competitive moves (new entrants, M&A, pricing changes). "
                f"Be specific with dollar amounts, percentages, and company names."
            )
            raw = tavily.search_text(
                query=query,
                topic="finance",
                search_depth="advanced",
                max_results=7,
                include_answer="advanced",
            )
            return _structure_with_llm(
                raw,
                f"Extract and structure the following raw research data about {company} ({ticker}) "
                f"and its competitors in {industry} into a clean, specific competitive analysis. "
                f"Extract only facts present in the source — do not invent numbers.\n\n"
                + structure_prompt,
            )

        except Exception as e:
            logger.warning(f"Competitor analysis: Tavily unavailable ({type(e).__name__}), using knowledge fallback")
            return _knowledge_based_fallback(structure_prompt, company, ticker)

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
        structure_prompt = f"""Provide a specific economic moat analysis for {company} ({ticker}).

Structure your output as follows:

**Moat Rating: WIDE / NARROW / NONE**
State clearly which rating applies and give the single most compelling reason in one sentence.

**Moat Sources — Evidence**
For each moat type that applies to {company}, give one specific, concrete piece of evidence:
- **Switching Costs**: [customer retention rate %, average contract length, or cost-to-switch estimate]
- **Network Effects**: [user count, platform stickiness metric, or lock-in mechanism]
- **Brand Power**: [brand value ranking, pricing premium vs. generic, NPS score]
- **Cost Advantage / Scale**: [gross margin vs. peer median, unit cost advantage]
- **Intangible Assets**: [number of patents, exclusive licenses, regulatory moats]
If a moat type does NOT apply, omit it.

**Pricing Power**
Has {company} raised prices without meaningful customer loss? Give the most recent specific example if available.

**Moat Durability**
Is the moat strengthening, stable, or at risk of erosion? Give one specific reason supporting your assessment.

**Machine-readable summary (append at the very end of your response, after all other content):**
```json
{{"moat_rating": "WIDE|NARROW|NONE"}}
```
Replace WIDE|NARROW|NONE with exactly one of those three values matching your assessment."""

        try:
            tavily = get_tavily_client()
            query = (
                f"{company} ({ticker}) economic moat competitive advantage analysis 2024 2025: "
                f"(1) does {company} have a WIDE, NARROW, or NO economic moat — give a clear rating and why, "
                f"(2) for each moat source that applies, give a SPECIFIC piece of evidence: "
                f"    — switching costs (e.g., customer retention rate %, average contract length, cost-to-switch), "
                f"    — network effects (e.g., user counts, platform lock-in mechanisms), "
                f"    — brand power (e.g., NPS scores, brand value rankings, pricing premium vs. generic), "
                f"    — cost advantage / economies of scale (e.g., gross margin vs. peers, unit economics), "
                f"    — intangible assets / patents / regulatory moats (e.g., number of patents, exclusive licenses), "
                f"(3) pricing power evidence — has {company} been able to raise prices without losing customers, "
                f"(4) durability — is the moat strengthening, stable, or at risk of erosion. "
                f"Be concrete — cite customer retention rates, specific products, named examples."
            )
            raw = tavily.search_text(
                query=query,
                topic="finance",
                search_depth="advanced",
                max_results=7,
                include_answer="advanced",
            )
            return _structure_with_llm(
                raw,
                f"Extract and structure the following raw research data about {company} ({ticker})'s "
                f"economic moat into a clean, specific analysis. "
                f"Extract only facts present in the source — do not invent numbers.\n\n"
                + structure_prompt,
            )

        except Exception as e:
            logger.warning(f"Moat analysis: Tavily unavailable ({type(e).__name__}), using knowledge fallback")
            return _knowledge_based_fallback(structure_prompt, company, ticker)

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
        structure_prompt = f"""Provide a specific management quality assessment for {company} ({ticker}).

Structure your output as follows:

**Leadership Team**
- CEO: [Full name, years as CEO, background before joining, key strategic initiatives under their tenure]
- CFO: [Full name if known, background]
- Other key executives if noteworthy

**Capital Allocation Track Record**
Rate each category: Excellent / Good / Fair / Poor
- M&A: [Named deals, whether accretive or dilutive, approximate values]
- Share Buybacks: [Total spent in last 3 years, were they well-timed?]
- Dividends: [Current yield, payout ratio, growth history]
- R&D Investment: [% of revenue, key technology bets, any notable results]
Overall Capital Allocation Rating: [Excellent / Good / Fair / Poor] — one sentence justification

**Insider Ownership & Alignment**
- CEO ownership: [%]
- Board ownership: [collective %]
- Notable insider transactions in last 12 months: [buys or sells, amounts if disclosed]

**Compensation & Governance**
- Is pay tied to long-term performance metrics? [Yes/No, brief description]
- Any governance red flags: [related-party transactions, board independence issues, activist investors]

**Machine-readable summary (append at the very end of your response, after all other content):**
```json
{{"management_quality": "EXCELLENT|GOOD|FAIR|POOR"}}
```
Replace EXCELLENT|GOOD|FAIR|POOR with exactly one of those four values matching your assessment."""

        try:
            tavily = get_tavily_client()
            query = (
                f"{company} ({ticker}) management quality assessment 2024 2025: "
                f"(1) CEO full name, how long they have been CEO, and their professional background before joining, "
                f"(2) CFO and 1-2 other key executives if notable, "
                f"(3) capital allocation track record over the past 3-5 years: "
                f"    — M&A history (named deals, were they accretive or dilutive?), "
                f"    — share buybacks (total amount spent, was timing good?), "
                f"    — dividends (yield, payout ratio, growth history), "
                f"    — R&D investment (% of revenue, key bets), "
                f"(4) insider ownership percentage for CEO and board — is it meaningful?, "
                f"(5) any notable insider purchases or sales in the last 12 months, "
                f"(6) executive compensation structure — is pay aligned with shareholder value creation?, "
                f"(7) any governance red flags (related-party transactions, board independence issues). "
                f"Name specific people, deals, and dollar amounts."
            )
            raw = tavily.search_text(
                query=query,
                topic="finance",
                search_depth="advanced",
                max_results=7,
                include_answer="advanced",
            )
            return _structure_with_llm(
                raw,
                f"Extract and structure the following raw research data about {company} ({ticker})'s "
                f"management team into a clean, specific management quality assessment. "
                f"Extract only facts present in the source — do not invent numbers.\n\n"
                + structure_prompt,
            )

        except Exception as e:
            logger.warning(f"Management analysis: Tavily unavailable ({type(e).__name__}), using knowledge fallback")
            return _knowledge_based_fallback(structure_prompt, company, ticker)

    async def _arun(self, company: str, ticker: str) -> str:
        return self._run(company, ticker)


class MultiplesValuationInput(BaseModel):
    """Input for multiples-based valuation tool"""
    company: str = Field(description="Company name (e.g., Apple Inc)")
    ticker: str = Field(description="Stock ticker symbol (e.g., AAPL)")
    sector: str = Field(description="Sector or industry (e.g., Technology Hardware)")


class MultiplesValuationTool(BaseTool):
    """Performs relative valuation using P/E, EV/EBITDA, P/S, and P/B multiples"""
    name: str = "perform_multiples_valuation"
    description: str = """Performs relative valuation by comparing the company's current trading
    multiples against sector peers and computing an implied fair value. Covers:
    - Current P/E, Forward P/E, EV/EBITDA, P/S, P/B vs. sector median
    - Implied price per valuation method with assigned weights
    - Weighted average fair value
    - Analyst consensus price target and rating breakdown

    Use this to anchor a price target to fundamentals rather than arbitrary multiples."""
    args_schema: Type[BaseModel] = MultiplesValuationInput

    def _run(self, company: str, ticker: str, sector: str) -> str:
        """Perform multiples-based valuation"""
        structure_prompt = f"""Provide a specific multiples-based valuation for {company} ({ticker}) in the {sector} sector.

Structure your output exactly as follows:

**Current Multiples vs. Sector**
| Metric | {ticker} | Sector Median | Premium / Discount |
|--------|----------|---------------|-------------------|
| P/E (TTM) | Xx | Xx | +/-X% |
| Forward P/E | Xx | Xx | +/-X% |
| EV/EBITDA | Xx | Xx | +/-X% |
| P/S | Xx | Xx | +/-X% |
| P/B | Xx | Xx | +/-X% |
Fill with real data. Write "N/A" for any metric you are not confident about.

**Implied Fair Value by Method**
| Method | Implied Price | Weight |
|--------|--------------|--------|
| P/E (sector median applied) | $XXX | 30% |
| Forward P/E | $XXX | 30% |
| EV/EBITDA | $XXX | 25% |
| P/S | $XXX | 15% |
If a method cannot be computed (missing data), omit that row and redistribute weights proportionally.

**Weighted Fair Value: $XXX.XX**

**Analyst Consensus**
- 12-month consensus price target: $XXX
- Rating breakdown: X Buy / X Hold / X Sell
- Implied upside from consensus: +/-X%"""

        try:
            tavily = get_tavily_client()
            query = (
                f"{company} ({ticker}) valuation multiples 2024 2025: "
                f"(1) current trailing P/E ratio, forward P/E ratio, EV/EBITDA, Price/Sales, Price/Book for {ticker}, "
                f"(2) sector median P/E, EV/EBITDA, P/S for {sector} peers — give specific numbers, "
                f"(3) Wall Street analyst consensus price target for {ticker} — 12-month target, "
                f"(4) analyst rating breakdown — number of Buy, Hold, Sell ratings, "
                f"(5) current EPS (TTM and forward estimate), EBITDA, revenue for implied value math. "
                f"Include specific dollar figures and named sources."
            )
            raw = tavily.search_text(
                query=query,
                topic="finance",
                search_depth="advanced",
                max_results=7,
                include_answer="advanced",
            )
            return _structure_with_llm(
                raw,
                f"Extract and structure the following raw research data about {company} ({ticker}) "
                f"valuation into a clean, specific multiples analysis. "
                f"Only use numbers actually found in the source data.\n\n"
                + structure_prompt,
            )

        except Exception as e:
            logger.warning(f"Multiples valuation: Tavily unavailable ({type(e).__name__}), using knowledge fallback")
            return _knowledge_based_fallback(structure_prompt, company, ticker)

    async def _arun(self, company: str, ticker: str, sector: str) -> str:
        return self._run(company, ticker, sector)


def get_equity_analyst_tools():
    """Return list of all equity analyst tools"""
    from tools.sec_tools import GetSECFilingsTool, AnalyzeSECFilingTool, GetSECFinancialsTool
    return [
        IndustryAnalysisTool(),
        CompetitorAnalysisTool(),
        MoatAnalysisTool(),
        ManagementAnalysisTool(),
        MultiplesValuationTool(),
        GetSECFilingsTool(),
        AnalyzeSECFilingTool(),
        GetSECFinancialsTool(),
    ]
