"""
SEC EDGAR Tools for LangChain Agents

Three tools giving agents direct access to SEC filings and structured financials:
  - get_sec_filings: List recent 10-K/10-Q/8-K filings with dates
  - analyze_sec_filing: Fetch and analyze content of a specific filing
  - get_sec_financials: Retrieve XBRL time-series data for a financial concept

No API key required — SEC EDGAR is fully public.
"""
import os
import logging
from typing import Optional, Type, List

import anthropic
from langchain.tools import BaseTool
from pydantic import BaseModel, Field

from data.sec_edgar import SECEdgarClient

logger = logging.getLogger(__name__)


# ============================================================================
# Shared LLM helper (mirrors equity_analyst_tools._structure_with_llm)
# ============================================================================

def _analyze_with_llm(raw_text: str, analysis_prompt: str) -> str:
    """Use Claude Haiku to extract structured insights from raw SEC filing text.

    Falls back to the raw text if the LLM call fails.
    """
    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=3000,
            messages=[{
                "role": "user",
                "content": (
                    f"{analysis_prompt}\n\n"
                    "IMPORTANT RULES:\n"
                    "- Only include facts actually found in the filing text — never invent numbers\n"
                    "- When a specific number is missing, write 'not disclosed' rather than estimating\n"
                    "- Be concrete and specific; avoid vague statements\n"
                    "- Do NOT include source URLs or citation markers\n"
                    "- Do NOT use ASCII borders (=====, -----) — use clean Markdown only\n\n"
                    f"SEC Filing Text:\n\n{raw_text}"
                ),
            }],
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.warning(f"LLM analysis of SEC filing failed, returning raw text: {e}")
        return raw_text


# ============================================================================
# Tool 1: Get SEC Filings List
# ============================================================================

class GetSECFilingsInput(BaseModel):
    ticker: str = Field(description="Stock ticker symbol (e.g. 'AAPL')")
    filing_type: str = Field(
        default="10-K",
        description="Filing type: '10-K' (annual), '10-Q' (quarterly), '8-K' (material events)",
    )
    limit: int = Field(
        default=3,
        description="Number of recent filings to return (1-10)",
    )


class GetSECFilingsTool(BaseTool):
    """List recent SEC EDGAR filings for a company."""

    name: str = "get_sec_filings"
    description: str = """Retrieves a list of recent SEC EDGAR filings for a company.

    Returns filing metadata including dates, accession numbers, and direct links.
    Supports 10-K (annual report), 10-Q (quarterly report), and 8-K (material events).

    Use this to:
    - Check when a company last filed its annual or quarterly report
    - Find the most recent 8-K for material events, acquisitions, or guidance updates
    - Get accession numbers needed to read the actual filing content
    - Verify official filing dates for regulatory purposes

    Always use this before calling analyze_sec_filing to confirm a filing exists."""

    args_schema: Type[BaseModel] = GetSECFilingsInput

    def _run(self, ticker: str, filing_type: str = "10-K", limit: int = 3) -> str:
        try:
            client = SECEdgarClient()
            cik = client.get_cik(ticker)
            if not cik:
                return f"No SEC EDGAR record found for ticker '{ticker}'. Verify the ticker is correct and the company is publicly listed in the US."

            filings = client.get_recent_filings(ticker, filing_type=filing_type, limit=limit)
            if not filings:
                return f"No {filing_type} filings found for {ticker} (CIK: {cik}) in SEC EDGAR."

            lines = [
                f"## SEC EDGAR {filing_type} Filings — {ticker.upper()} (CIK: {int(cik)})",
                "",
            ]
            for i, f in enumerate(filings, 1):
                lines.append(f"### Filing {i}")
                lines.append(f"- **Type**: {f['filing_type']}")
                lines.append(f"- **Filed**: {f['filing_date']}")
                if f.get("report_date"):
                    lines.append(f"- **Period**: {f['report_date']}")
                lines.append(f"- **Accession**: {f['accession_number']}")
                if f.get("document_url"):
                    lines.append(f"- **Document**: {f['document_url']}")
                lines.append("")

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"get_sec_filings error for {ticker}: {e}")
            return f"Error fetching SEC filings for {ticker}: {str(e)}"

    async def _arun(self, ticker: str, filing_type: str = "10-K", limit: int = 3) -> str:
        return self._run(ticker, filing_type, limit)


# ============================================================================
# Tool 2: Analyze SEC Filing Content
# ============================================================================

class AnalyzeSECFilingInput(BaseModel):
    ticker: str = Field(description="Stock ticker symbol (e.g. 'AAPL')")
    filing_type: str = Field(
        default="10-K",
        description="Filing type to analyze: '10-K' (annual) or '10-Q' (quarterly)",
    )
    sections: str = Field(
        default="all",
        description=(
            "Sections to extract: 'mda' (Management Discussion & Analysis), "
            "'risk_factors' (Key risks), 'business' (Business overview), "
            "'guidance' (Forward guidance and outlook), or 'all' (all key sections)"
        ),
    )


class AnalyzeSECFilingTool(BaseTool):
    """Fetch and analyze the content of a company's most recent SEC filing."""

    name: str = "analyze_sec_filing"
    description: str = """Fetches and analyzes the content of a company's most recent SEC 10-K or 10-Q filing.

    Extracts and summarizes key sections using AI:
    - **MD&A (Management Discussion & Analysis)**: Revenue drivers, margin trends, segment performance
    - **Risk Factors**: Key business, market, and regulatory risks disclosed by management
    - **Business Overview**: Products, markets, competitive position, strategy
    - **Forward Guidance**: Management outlook, guidance ranges, strategic initiatives

    Use this to:
    - Read what management says about their business in their own words (primary source)
    - Find officially disclosed risks that aren't in news articles
    - Extract MD&A commentary on revenue trends, margins, and competitive dynamics
    - Get forward-looking statements and guidance directly from the filing
    - Supplement earnings call analysis with written management commentary

    This is authoritative primary-source data — more reliable than third-party summaries."""

    args_schema: Type[BaseModel] = AnalyzeSECFilingInput

    def _run(self, ticker: str, filing_type: str = "10-K", sections: str = "all") -> str:
        try:
            client = SECEdgarClient()
            filings = client.get_recent_filings(ticker, filing_type=filing_type, limit=1)

            if not filings:
                return (
                    f"No {filing_type} filing found for {ticker} in SEC EDGAR. "
                    f"The company may not be listed in the US or may not have filed recently."
                )

            filing = filings[0]
            if not filing.get("document_url"):
                return f"Filing found for {ticker} (filed {filing['filing_date']}) but document URL could not be constructed."

            filing_text = client.get_filing_text(
                accession_number=filing["accession_number"],
                cik=filing["cik"],
                primary_document=filing["primary_document"],
            )
            if not filing_text:
                return (
                    f"Could not retrieve filing text for {ticker} {filing_type} "
                    f"(filed {filing['filing_date']}). The document may be in an unsupported format."
                )

            # Build extraction prompt based on requested sections
            section_instructions = {
                "mda": (
                    "Extract and summarize the Management's Discussion and Analysis (MD&A) section. "
                    "Focus on: revenue and profit drivers, segment performance, year-over-year changes, "
                    "margin trends, and any notable commentary on business conditions."
                ),
                "risk_factors": (
                    "Extract and summarize the Risk Factors section. "
                    "List the top 10 most significant risks the company disclosed, "
                    "grouped by category (business, market, regulatory, financial, operational)."
                ),
                "business": (
                    "Extract and summarize the Business section. "
                    "Cover: products and services, target markets, revenue model, "
                    "competitive positioning, and strategic priorities."
                ),
                "guidance": (
                    "Extract any forward-looking statements, guidance, or outlook disclosed in the filing. "
                    "Include: revenue/earnings guidance ranges, strategic initiatives, planned investments, "
                    "and management's expectations for the next period."
                ),
                "all": (
                    "Extract and summarize ALL key sections of this filing in order: "
                    "1) Business Overview, "
                    "2) Risk Factors (top 8), "
                    "3) Management Discussion & Analysis (MD&A), "
                    "4) Forward-Looking Statements and Guidance. "
                    "Be specific and data-driven."
                ),
            }

            prompt = section_instructions.get(
                sections.lower(),
                section_instructions["all"],
            )

            full_prompt = (
                f"You are analyzing {ticker}'s {filing_type} filed on {filing['filing_date']} "
                f"(period ending {filing.get('report_date', 'unknown')}).\n\n"
                f"{prompt}"
            )

            analysis = _analyze_with_llm(filing_text, full_prompt)

            header = (
                f"## {ticker.upper()} {filing_type} Analysis — "
                f"Filed {filing['filing_date']} | Period: {filing.get('report_date', 'N/A')}\n"
                f"*Source: SEC EDGAR | Accession: {filing['accession_number']}*\n\n"
            )

            return header + analysis

        except Exception as e:
            logger.error(f"analyze_sec_filing error for {ticker}: {e}")
            return f"Error analyzing SEC {filing_type} filing for {ticker}: {str(e)}"

    async def _arun(self, ticker: str, filing_type: str = "10-K", sections: str = "all") -> str:
        return self._run(ticker, filing_type, sections)


# ============================================================================
# Tool 3: Get XBRL Structured Financials
# ============================================================================

# Map of common concept aliases to official US-GAAP taxonomy names
CONCEPT_ALIASES = {
    # Modern standard (post-ASC 606 adoption ~2018) — preferred for most companies
    "revenue": "RevenueFromContractWithCustomerExcludingAssessedTax",
    "revenues": "RevenueFromContractWithCustomerExcludingAssessedTax",
    "sales": "RevenueFromContractWithCustomerExcludingAssessedTax",
    "net_income": "NetIncomeLoss",
    "net income": "NetIncomeLoss",
    "assets": "Assets",
    "total_assets": "Assets",
    "liabilities": "Liabilities",
    "total_liabilities": "Liabilities",
    "equity": "StockholdersEquity",
    "shareholders_equity": "StockholdersEquity",
    "cash": "CashAndCashEquivalentsAtCarryingValue",
    "long_term_debt": "LongTermDebt",
    "debt": "LongTermDebt",
    "operating_income": "OperatingIncomeLoss",
    "ebit": "OperatingIncomeLoss",
    "eps": "EarningsPerShareBasic",
    "eps_basic": "EarningsPerShareBasic",
    "eps_diluted": "EarningsPerShareDiluted",
    "rd": "ResearchAndDevelopmentExpense",
    "r&d": "ResearchAndDevelopmentExpense",
    "capex": "PaymentsToAcquirePropertyPlantAndEquipment",
    "shares": "CommonStockSharesOutstanding",
    "shares_outstanding": "CommonStockSharesOutstanding",
    "gross_profit": "GrossProfit",
    "operating_cash_flow": "NetCashProvidedByUsedInOperatingActivities",
    "free_cash_flow": "NetCashProvidedByUsedInOperatingActivities",  # Best proxy available
}

# Concepts that use non-USD units
SHARE_CONCEPTS = {"CommonStockSharesOutstanding", "CommonStockSharesIssued"}
EPS_CONCEPTS = {"EarningsPerShareBasic", "EarningsPerShareDiluted"}


class GetSECFinancialsInput(BaseModel):
    ticker: str = Field(description="Stock ticker symbol (e.g. 'AAPL')")
    concept: str = Field(
        description=(
            "Financial concept to retrieve. Common options: "
            "'revenue', 'net_income', 'assets', 'liabilities', 'equity', 'cash', "
            "'long_term_debt', 'operating_income', 'eps', 'r&d', 'capex', "
            "'shares_outstanding', 'gross_profit', 'operating_cash_flow'. "
            "Can also use exact US-GAAP taxonomy names like 'Revenues' or 'NetIncomeLoss'."
        )
    )
    annual_only: bool = Field(
        default=True,
        description="If True (default), return only annual (10-K) data. Set False to include quarterly.",
    )
    years: int = Field(
        default=5,
        description="Number of years of historical data to return (default 5)",
    )


class GetSECFinancialsTool(BaseTool):
    """Retrieve XBRL-structured financial data directly from SEC filings."""

    name: str = "get_sec_financials"
    description: str = """Retrieves structured financial data directly from SEC EDGAR XBRL filings.

    Returns authoritative time-series data for financial metrics reported directly to the SEC.
    This is the most reliable source of financial data — pulled from the actual filings.

    Available metrics include: revenue, net_income, assets, liabilities, equity, cash,
    long_term_debt, operating_income, eps, r&d, capex, shares_outstanding, gross_profit,
    operating_cash_flow, or any US-GAAP taxonomy concept name.

    Use this to:
    - Verify financial figures with primary-source accuracy
    - Get multi-year historical trends for DCF analysis
    - Cross-check third-party financial data
    - Access financial data for companies where other APIs have gaps
    - Get EPS, revenue, and balance sheet data going back 10+ years"""

    args_schema: Type[BaseModel] = GetSECFinancialsInput

    def _run(
        self,
        ticker: str,
        concept: str,
        annual_only: bool = True,
        years: int = 5,
    ) -> str:
        try:
            client = SECEdgarClient()

            # Resolve concept alias to official taxonomy name
            concept_lower = concept.lower().strip()
            gaap_concept = CONCEPT_ALIASES.get(concept_lower, concept)  # Use as-is if not an alias

            # Determine the correct unit type
            if gaap_concept in EPS_CONCEPTS:
                unit = "USD/shares"
            elif gaap_concept in SHARE_CONCEPTS:
                unit = "shares"
            else:
                unit = "USD"

            data_points = client.get_financial_concept(
                ticker=ticker,
                concept=gaap_concept,
                unit=unit,
                annual_only=annual_only,
                limit=years,
            )

            # If initial concept lookup failed, try alternative names
            if not data_points and concept_lower in ("revenue", "revenues", "sales"):
                for alt in ["Revenues", "SalesRevenueNet", "RevenueFromContractWithCustomerExcludingAssessedTax"]:
                    if alt == gaap_concept:
                        continue
                    data_points = client.get_financial_concept(ticker, alt, unit="USD", annual_only=annual_only, limit=years)
                    if data_points:
                        gaap_concept = alt
                        break

            if not data_points:
                return (
                    f"No XBRL data found for concept '{concept}' (US-GAAP: {gaap_concept}) "
                    f"for {ticker}. The company may use a different concept name or may not "
                    f"report this metric in XBRL format. Try a different concept name."
                )

            # Format output
            period_type = "Annual (10-K)" if annual_only else "Annual + Quarterly"
            unit_label = {"USD": "$", "USD/shares": "$/share", "shares": "shares"}.get(unit, unit)

            lines = [
                f"## {ticker.upper()} — {gaap_concept}",
                f"*Source: SEC EDGAR XBRL | {period_type} | Unit: {unit_label}*",
                "",
                f"{'Period':<14} {'Value':>20} {'Form':<8} {'Filed':<12}",
                "-" * 58,
            ]

            for point in data_points:
                val = point.get("value")
                period = point.get("period", "N/A")
                form = point.get("form", "")
                filed = point.get("filed_date", "")

                if val is None:
                    val_str = "N/A"
                elif unit == "USD":
                    if abs(val) >= 1e9:
                        val_str = f"${val/1e9:>16.2f}B"
                    elif abs(val) >= 1e6:
                        val_str = f"${val/1e6:>16.2f}M"
                    else:
                        val_str = f"${val:>18,.0f}"
                elif unit == "USD/shares":
                    val_str = f"{val:>19.4f}"
                else:
                    val_str = f"{val:>20,.0f}"

                lines.append(f"{period:<14} {val_str} {form:<8} {filed:<12}")

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"get_sec_financials error for {ticker} ({concept}): {e}")
            return f"Error fetching SEC XBRL financials for {ticker} ({concept}): {str(e)}"

    async def _arun(
        self,
        ticker: str,
        concept: str,
        annual_only: bool = True,
        years: int = 5,
    ) -> str:
        return self._run(ticker, concept, annual_only, years)


# ============================================================================
# Tool registry
# ============================================================================

def get_sec_tools() -> List[BaseTool]:
    """Return all SEC EDGAR tools."""
    return [
        GetSECFilingsTool(),
        AnalyzeSECFilingTool(),
        GetSECFinancialsTool(),
    ]
