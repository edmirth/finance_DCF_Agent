"""
LangGraph-based Equity Analyst Agent with structured workflow
"""
from typing import TypedDict, Annotated, List, Optional
from langgraph.graph import StateGraph, END
from langchain_anthropic import ChatAnthropic
from langchain.tools import BaseTool
from tools.stock_tools import get_stock_tools
from tools.equity_analyst_tools import get_equity_analyst_tools
from tools.earnings_tools import get_earnings_tools
import json
import operator
import os
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


# State definition - tracks all analysis data
class EquityAnalystState(TypedDict):
    """State for equity analyst workflow"""
    ticker: str
    company_name: str
    sector: str
    industry: str
    current_price: float

    # Step 1: Company info
    company_info: dict

    # Step 2: Financial metrics
    financial_metrics: dict
    historical_growth: dict

    # Step 3: Industry analysis
    industry_analysis: str
    market_size: str
    industry_trends: List[str]

    # Step 4: Competitive analysis
    competitors: List[str]
    competitive_position: str
    market_share: str

    # Step 5: Moat analysis
    moat_strength: str  # NONE, NARROW, WIDE
    moat_sources: List[str]

    # Step 6: Management analysis
    management_quality: str  # POOR, FAIR, GOOD, EXCELLENT
    capital_allocation: str

    # Parallel earnings analysis
    earnings_snapshot: str
    earnings_beat_rate: Optional[float]  # None = no structured data available

    # Step 7: SEC filing analysis
    sec_filing_analysis: str

    # Step 8: Multiples valuation
    multiples_valuation: str
    fair_value: float
    valuation_upside: float

    # Step 9: Investment thesis
    bull_case: List[str]
    bear_case: List[str]
    base_case: str

    # Step 9: Final recommendation
    price_target: float
    conviction: str  # HIGH, MEDIUM, LOW

    # Output
    final_report: str

    # Metadata
    # Annotated with operator.add so parallel branches concatenate instead of overwriting
    analysis_steps: Annotated[List[str], operator.add]
    errors: Annotated[List[str], operator.add]
    current_step: str


class EquityAnalystGraph:
    """LangGraph-based equity analyst with structured workflow"""

    def __init__(self, api_key: str = None, model: str = "claude-sonnet-4-5-20250929"):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model
        self.llm = ChatAnthropic(
            model=self.model,
            temperature=0,
            anthropic_api_key=self.api_key,
            max_retries=3,  # Retry failed API calls
            default_request_timeout=60.0,  # Request timeout in seconds
            max_tokens=8192,  # Max output tokens
        )

        # Get all tools
        self.stock_tools = {tool.name: tool for tool in get_stock_tools()}
        self.analyst_tools = {tool.name: tool for tool in get_equity_analyst_tools()}
        self.earnings_tools = {tool.name: tool for tool in get_earnings_tools()}

        # Detect and log silent name collisions before merging
        all_sources = [("stock", self.stock_tools), ("analyst", self.analyst_tools), ("earnings", self.earnings_tools)]
        seen: dict = {}
        for source_name, tool_dict in all_sources:
            for name in tool_dict:
                if name in seen:
                    logger.warning(
                        f"Tool name collision: '{name}' defined in both '{seen[name]}' and '{source_name}'. "
                        f"'{source_name}' version will be used."
                    )
                seen[name] = source_name

        # analyst_tools overwrites stock_tools on collision; earnings_tools overwrites both
        self.all_tools = {**self.stock_tools, **self.analyst_tools, **self.earnings_tools}

        # Build graph
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow"""

        # Create graph
        workflow = StateGraph(EquityAnalystState)

        # Add nodes
        workflow.add_node("get_company_info", self.get_company_info)
        workflow.add_node("get_financial_metrics", self.get_financial_metrics)
        # Parallel qualitative research nodes (Steps 3a-3e)
        workflow.add_node("analyze_industry", self.analyze_industry)
        workflow.add_node("analyze_competitors", self.analyze_competitors)
        workflow.add_node("analyze_moat", self.analyze_moat)
        workflow.add_node("analyze_management", self.analyze_management)
        workflow.add_node("fetch_earnings_snapshot", self.fetch_earnings_snapshot)
        # Fan-in sync point
        workflow.add_node("sync_qualitative", self.sync_qualitative)
        # Sequential nodes
        workflow.add_node("analyze_sec_filings", self.analyze_sec_filings)
        workflow.add_node("perform_multiples_valuation", self.perform_multiples_valuation)
        workflow.add_node("develop_thesis", self.develop_thesis)
        workflow.add_node("make_recommendation", self.make_recommendation)
        workflow.add_node("format_report", self.format_report)

        # Workflow edges
        workflow.set_entry_point("get_company_info")
        workflow.add_edge("get_company_info", "get_financial_metrics")

        # Fan-out: all five qualitative nodes run in parallel after financials
        workflow.add_edge("get_financial_metrics", "analyze_industry")
        workflow.add_edge("get_financial_metrics", "analyze_competitors")
        workflow.add_edge("get_financial_metrics", "analyze_moat")
        workflow.add_edge("get_financial_metrics", "analyze_management")
        workflow.add_edge("get_financial_metrics", "fetch_earnings_snapshot")

        # Fan-in: all five converge at the sync point
        workflow.add_edge("analyze_industry", "sync_qualitative")
        workflow.add_edge("analyze_competitors", "sync_qualitative")
        workflow.add_edge("analyze_moat", "sync_qualitative")
        workflow.add_edge("analyze_management", "sync_qualitative")
        workflow.add_edge("fetch_earnings_snapshot", "sync_qualitative")

        # Sequential tail
        workflow.add_edge("sync_qualitative", "analyze_sec_filings")
        workflow.add_edge("analyze_sec_filings", "perform_multiples_valuation")
        workflow.add_edge("perform_multiples_valuation", "develop_thesis")
        workflow.add_edge("develop_thesis", "make_recommendation")
        workflow.add_edge("make_recommendation", "format_report")
        workflow.add_edge("format_report", END)

        return workflow.compile()

    def get_company_info(self, state: EquityAnalystState) -> EquityAnalystState:
        """Step 1: Get basic company information"""
        _new_steps: list = []
        _new_errors: list = []
        logger.info(f"[Step 1/10] Getting company info for {state['ticker']}")
        state["current_step"] = "Company Info"
        _new_steps.append("Company Info")

        try:
            tool = self.all_tools["get_stock_info"]
            result = tool.invoke({"ticker": state["ticker"]})

            state["company_info"] = {"raw": result}

            # Safe field extraction — guard each split against missing substrings
            if "Company:" in result:
                state["company_name"] = result.split("Company:")[1].split("\n")[0].strip()
            if "Sector:" in result:
                state["sector"] = result.split("Sector:")[1].split("\n")[0].strip()
            if "Industry:" in result:
                state["industry"] = result.split("Industry:")[1].split("\n")[0].strip()
            if "Current Price: $" in result:
                try:
                    price_str = result.split("Current Price: $")[1].split("\n")[0].strip()
                    state["current_price"] = float(price_str.replace(",", ""))
                except (ValueError, IndexError) as e:
                    logger.warning(f"Could not parse current price: {e}")

        except Exception as e:
            logger.error(f"Error in get_company_info: {e}")
            _new_errors.append(f"Company info error: {str(e)}")

        # Validate critical fields — use ticker as fallback for company_name
        if not state.get("company_name"):
            state["company_name"] = state["ticker"]
            logger.warning(f"company_name not found, using ticker '{state['ticker']}' as fallback")

        state["analysis_steps"] = _new_steps
        state["errors"] = _new_errors
        return state

    def get_financial_metrics(self, state: EquityAnalystState) -> EquityAnalystState:
        """Step 2: Get financial metrics"""
        _new_steps: list = []
        _new_errors: list = []
        logger.info(f"[Step 2/10] Getting financial metrics")
        state["current_step"] = "Financial Metrics"
        _new_steps.append("Financial Metrics")

        try:
            tool = self.all_tools["get_financial_metrics"]
            result = tool.invoke({"ticker": state["ticker"]})
            state["financial_metrics"] = {"raw": result}

            # Extract growth rates with safe parsing
            if "Revenue CAGR:" in result:
                try:
                    growth_str = result.split("Revenue CAGR:")[1].split("%")[0].strip()
                    state["historical_growth"] = {"revenue_cagr": float(growth_str) / 100}
                except (ValueError, IndexError) as e:
                    logger.warning(f"Could not parse Revenue CAGR: {e}")

        except Exception as e:
            logger.error(f"Error in get_financial_metrics: {e}")
            _new_errors.append(f"Financial metrics error: {str(e)}")

        state["analysis_steps"] = _new_steps
        state["errors"] = _new_errors
        return state

    def analyze_industry(self, state: EquityAnalystState) -> EquityAnalystState:
        """Step 3: Industry analysis"""
        _new_steps: list = []
        _new_errors: list = []
        logger.info(f"[Step 3/10] Analyzing industry")
        state["current_step"] = "Industry Analysis"
        _new_steps.append("Industry Analysis")

        try:
            tool = self.all_tools["analyze_industry"]
            result = tool.invoke({
                "company": state["company_name"],
                "ticker": state["ticker"],
                "sector": state["sector"] or state["industry"] or "General",  # fallback if unparsed (#6)
            })
            state["industry_analysis"] = result

        except Exception as e:
            logger.error(f"Error in analyze_industry: {e}")
            _new_errors.append(f"Industry analysis error: {str(e)}")
            state["industry_analysis"] = "Industry analysis unavailable"

        state["analysis_steps"] = _new_steps
        state["errors"] = _new_errors
        return state

    def analyze_competitors(self, state: EquityAnalystState) -> EquityAnalystState:
        """Step 4: Competitive analysis"""
        _new_steps: list = []
        _new_errors: list = []
        logger.info(f"[Step 4/10] Analyzing competitors")
        state["current_step"] = "Competitive Analysis"
        _new_steps.append("Competitive Analysis")

        try:
            tool = self.all_tools["analyze_competitors"]
            result = tool.invoke({
                "company": state["company_name"],
                "ticker": state["ticker"],
                "industry": state["industry"] or state["sector"] or "General",  # fallback if unparsed (#6)
            })
            state["competitive_position"] = result

        except Exception as e:
            logger.error(f"Error in analyze_competitors: {e}")
            _new_errors.append(f"Competitor analysis error: {str(e)}")
            state["competitive_position"] = "Competitor analysis unavailable"

        state["analysis_steps"] = _new_steps
        state["errors"] = _new_errors
        return state

    def analyze_moat(self, state: EquityAnalystState) -> EquityAnalystState:
        """Step 5: Moat analysis"""
        _new_steps: list = []
        _new_errors: list = []
        logger.info(f"[Step 5/10] Analyzing competitive moat")
        state["current_step"] = "Moat Analysis"
        _new_steps.append("Moat Analysis")

        try:
            tool = self.all_tools["analyze_moat"]
            result = tool.invoke({
                "company": state["company_name"],
                "ticker": state["ticker"]
            })

            # Try JSON parsing first (structured output from tool)
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', result, re.DOTALL)
            if json_match:
                try:
                    parsed = json.loads(json_match.group(1))
                    moat_val = parsed.get("moat_rating", "").upper()
                    if moat_val in ("WIDE", "NARROW", "NONE"):
                        state["moat_strength"] = moat_val
                        state["moat_sources"] = []
                        state["analysis_steps"] = _new_steps
                        state["errors"] = _new_errors
                        return state  # skip regex fallback
                except (json.JSONDecodeError, KeyError):
                    pass

            # Fallback: moat-specific phrase matching only — no bare word patterns
            # that would match unrelated text ("wide range", "narrow margins", etc.)
            result_lower = result.lower()
            if (
                "wide moat" in result_lower
                or re.search(r'moat\s*(?:rating|strength|classification)\s*[:\-]\s*wide', result_lower)
            ):
                state["moat_strength"] = "WIDE"
            elif (
                "narrow moat" in result_lower
                or re.search(r'moat\s*(?:rating|strength|classification)\s*[:\-]\s*narrow', result_lower)
            ):
                state["moat_strength"] = "NARROW"
            elif (
                "no moat" in result_lower
                or re.search(r'moat\s*(?:rating|strength|classification)\s*[:\-]\s*none', result_lower)
            ):
                state["moat_strength"] = "NONE"
            else:
                # No clear moat signal found — mark unknown rather than guessing
                state["moat_strength"] = "UNKNOWN"

            state["moat_sources"] = []  # Would parse from result

        except Exception as e:
            logger.error(f"Error in analyze_moat: {e}")
            _new_errors.append(f"Moat analysis error: {str(e)}")
            state["moat_strength"] = "UNKNOWN"

        state["analysis_steps"] = _new_steps
        state["errors"] = _new_errors
        return state

    def analyze_management(self, state: EquityAnalystState) -> EquityAnalystState:
        """Step 6: Management analysis"""
        _new_steps: list = []
        _new_errors: list = []
        logger.info(f"[Step 6/10] Analyzing management quality")
        state["current_step"] = "Management Analysis"
        _new_steps.append("Management Analysis")

        try:
            tool = self.all_tools["analyze_management"]
            result = tool.invoke({
                "company": state["company_name"],
                "ticker": state["ticker"]
            })
            state["capital_allocation"] = result
            result_lower = result.lower()

            # Check if the result actually contains info about our company
            # Use word-boundary match for short tickers (<=2 chars) to avoid
            # matching single letters like "A" or "T" inside every English word
            ticker = state["ticker"]
            company = state.get("company_name", "")
            if len(ticker) <= 2:
                is_relevant = bool(re.search(r'\b' + re.escape(ticker) + r'\b', result, re.IGNORECASE))
            else:
                is_relevant = ticker.lower() in result_lower
            if not is_relevant and company and len(company) > 2:
                is_relevant = company.lower() in result_lower

            def _has_word(text, words):
                """Check for whole-word matches to avoid substring false positives."""
                return any(re.search(r'\b' + w + r'\b', text) for w in words)

            if not is_relevant:
                logger.warning(f"Management analysis may not be relevant to {state['ticker']}")
                state["management_quality"] = "UNKNOWN"
            else:
                # Try JSON parsing first (structured output from tool)
                json_match = re.search(r'```json\s*(\{.*?\})\s*```', result, re.DOTALL)
                if json_match:
                    try:
                        parsed = json.loads(json_match.group(1))
                        mgmt_val = parsed.get("management_quality", "").upper()
                        if mgmt_val in ("EXCELLENT", "GOOD", "FAIR", "POOR"):
                            state["management_quality"] = mgmt_val
                            state["analysis_steps"] = _new_steps
                            state["errors"] = _new_errors
                            return state  # skip keyword fallback
                    except (json.JSONDecodeError, KeyError):
                        pass

                # Fallback: keyword matching
                if _has_word(result_lower, ["excellent", "exceptional", "outstanding", "best-in-class"]):
                    state["management_quality"] = "EXCELLENT"
                elif _has_word(result_lower, ["strong leadership", "strong management", "good management", "effective leadership", "capable", "proven track record", "well-regarded"]):
                    state["management_quality"] = "GOOD"
                elif _has_word(result_lower, ["adequate management", "mixed record", "average management", "mediocre", "inconsistent"]):
                    # Avoid bare "fair"/"average" — too common in financial text (e.g. "fair value", "average revenue")
                    state["management_quality"] = "FAIR"
                elif _has_word(result_lower, ["poor management", "weak leadership", "weak management", "concerning", "questionable"]):
                    state["management_quality"] = "POOR"
                else:
                    state["management_quality"] = "UNKNOWN"

        except Exception as e:
            logger.error(f"Error in analyze_management: {e}")
            _new_errors.append(f"Management analysis error: {str(e)}")
            state["management_quality"] = "UNKNOWN"

        state["analysis_steps"] = _new_steps
        state["errors"] = _new_errors
        return state

    @staticmethod
    def _strip_chart_blocks(text: str) -> str:
        """Remove ---CHART_DATA--- blocks and CHART_INSTRUCTION lines from tool output.

        Earnings tools append raw JSON chart specs and instruction comments to their
        output for the frontend SSE layer to consume. These must be stripped before
        the text is inserted into the report or used in LLM prompts.
        """
        # Remove multiline chart data blocks: ---CHART_DATA:id---\n...\n---END_CHART_DATA:id---
        text = re.sub(
            r'\n---CHART_DATA:[^\n]+---\n.*?\n---END_CHART_DATA:[^\n]+---',
            '',
            text,
            flags=re.DOTALL,
        )
        # Remove single-line chart instruction comments
        text = re.sub(r'\n\[CHART_INSTRUCTION:[^\]]+\]', '', text)
        return text

    def fetch_earnings_snapshot(self, state: EquityAnalystState) -> EquityAnalystState:
        """Parallel Step: Fetch quarterly earnings, surprises, and call insights"""
        _new_steps: list = []
        _new_errors: list = []
        logger.info(f"[Parallel] Fetching earnings snapshot for {state['ticker']}")
        _new_steps.append("Earnings Snapshot")

        parts = []

        # 1. Quarterly earnings (4 quarters)
        try:
            tool = self.all_tools.get("get_quarterly_earnings")
            if tool:
                result = tool.invoke({"ticker": state["ticker"], "quarters": 4})
                parts.append(self._strip_chart_blocks(result))
        except Exception as e:
            logger.warning(f"get_quarterly_earnings failed: {e}")
            _new_errors.append(f"Quarterly earnings error: {str(e)}")

        # 2. Earnings surprises (6 quarters) — parse beat rate before stripping
        try:
            tool = self.all_tools.get("get_earnings_surprises")
            if tool:
                result = tool.invoke({"ticker": state["ticker"], "quarters": 6})
                # Parse beat rate from raw output before stripping (chart blocks don't affect this)
                match = re.search(r'Beats:\s*(\d+)/(\d+)', result)
                if match:
                    beats = int(match.group(1))
                    total = int(match.group(2))
                    if total > 0:
                        state["earnings_beat_rate"] = beats / total
                parts.append(self._strip_chart_blocks(result))
        except Exception as e:
            logger.warning(f"get_earnings_surprises failed: {e}")
            _new_errors.append(f"Earnings surprises error: {str(e)}")

        # 3. Earnings call insights (most recent quarter)
        try:
            tool = self.all_tools.get("get_earnings_call_insights")
            if tool:
                result = tool.invoke({"ticker": state["ticker"], "quarters": 1})
                parts.append(self._strip_chart_blocks(result))
        except Exception as e:
            logger.warning(f"get_earnings_call_insights failed: {e}")
            _new_errors.append(f"Earnings call insights error: {str(e)}")

        state["earnings_snapshot"] = "\n\n---\n\n".join(parts) if parts else "Earnings data unavailable"
        state["analysis_steps"] = _new_steps
        state["errors"] = _new_errors
        return state

    def sync_qualitative(self, state: EquityAnalystState) -> EquityAnalystState:
        """Fan-in sync point — waits for all parallel qualitative nodes to complete"""
        logger.info(f"[Sync] Parallel qualitative analysis complete for {state['ticker']}")
        state["current_step"] = "Qualitative Sync"

        # Warn for any parallel fields still at defaults — helps surface silent failures
        checks = {
            "industry_analysis": ("", "analyze_industry"),
            "competitive_position": ("", "analyze_competitors"),
            "moat_strength": ("", "analyze_moat"),
            "capital_allocation": ("", "analyze_management"),
            "earnings_snapshot": ("", "fetch_earnings_snapshot"),
        }
        for field, (default_val, node_name) in checks.items():
            if state.get(field) == default_val:
                logger.warning(f"[Sync] Field '{field}' is still at default — '{node_name}' may have failed silently")

        return state

    def perform_multiples_valuation(self, state: EquityAnalystState) -> EquityAnalystState:
        """Relative valuation via P/E, EV/EBITDA, P/S, P/B multiples (runs after qualitative sync)"""
        _new_steps: list = []
        _new_errors: list = []
        logger.info(f"[Step 6] Performing multiples valuation for {state['ticker']}")
        state["current_step"] = "Multiples Valuation"
        _new_steps.append("Multiples Valuation")

        try:
            tool = self.all_tools.get("perform_multiples_valuation")
            if tool is None:
                raise KeyError("perform_multiples_valuation tool not available")

            result = tool.invoke({
                "company": state["company_name"],
                "ticker": state["ticker"],
                "sector": state.get("sector") or state.get("industry") or "General",
            })
            state["multiples_valuation"] = result

            # Parse "Weighted Fair Value: $XXX.XX" from the structured output
            match = re.search(r'Weighted Fair Value:\s*\$([0-9,]+\.?\d*)', result)
            if match:
                fair_value = float(match.group(1).replace(",", ""))
                state["fair_value"] = fair_value
                current_price = state.get("current_price", 0)
                if current_price > 0:
                    state["valuation_upside"] = (fair_value / current_price - 1) * 100

        except Exception as e:
            logger.error(f"Error in perform_multiples_valuation: {e}")
            _new_errors.append(f"Multiples valuation error: {str(e)}")
            state["multiples_valuation"] = "Multiples valuation unavailable"

        state["analysis_steps"] = _new_steps
        state["errors"] = _new_errors
        return state

    def analyze_sec_filings(self, state: EquityAnalystState) -> EquityAnalystState:
        """Step 7: Analyze SEC filings (10-K/10-Q) for MD&A, risks, and guidance"""
        _new_steps: list = []
        _new_errors: list = []
        logger.info(f"[Step 7/10] Analyzing SEC filings for {state['ticker']}")
        state["current_step"] = "SEC Filing Analysis"
        _new_steps.append("SEC Filing Analysis")

        try:
            tool = self.all_tools.get("analyze_sec_filing")
            if tool is None:
                raise KeyError("analyze_sec_filing tool not available")

            result = tool.invoke({
                "ticker": state["ticker"],
                "filing_type": "10-K",
                "sections": "all",
            })
            state["sec_filing_analysis"] = result

        except Exception as e:
            logger.error(f"Error in analyze_sec_filings: {e}")
            _new_errors.append(f"SEC filing analysis error: {str(e)}")
            state["sec_filing_analysis"] = "SEC filing analysis unavailable"

        state["analysis_steps"] = _new_steps
        state["errors"] = _new_errors
        return state

    def develop_thesis(self, state: EquityAnalystState) -> EquityAnalystState:
        """Step 8: Develop investment thesis"""
        _new_steps: list = []
        _new_errors: list = []
        logger.info(f"[Step 8/10] Developing investment thesis")
        state["current_step"] = "Investment Thesis"
        _new_steps.append("Investment Thesis")

        fair_value = state.get("fair_value", 0)
        valuation_upside = state.get("valuation_upside", 0)
        valuation_context = (
            f"Multiples Fair Value: ${fair_value:.2f} ({valuation_upside:+.1f}% vs. current price)"
            if fair_value > 0 else "Multiples valuation unavailable"
        )

        # Use LLM to synthesize bull/bear cases from all analysis
        prompt = f"""Based on the following analysis for {state['company_name']} ({state['ticker']}),
        develop a concise bull case (3 points) and bear case (3 points).

        Use specific numbers and named factors — not generic statements.

        Industry: {state.get('industry_analysis', 'N/A')[:500]}
        Competitive Position: {state.get('competitive_position', 'N/A')[:500]}
        Moat: {state.get('moat_strength', 'UNKNOWN')}
        Management: {state.get('management_quality', 'UNKNOWN')}
        Valuation: {valuation_context}
        SEC Filing Highlights: {state.get('sec_filing_analysis', 'N/A')[:500]}
        Financial Metrics: {state.get('financial_metrics', {}).get('raw', 'N/A')[:400]}
        Earnings Trend: {state.get('earnings_snapshot', 'N/A')[:500]}
        Current Price: ${state.get('current_price', 0):.2f}

        Format exactly as:
        BULL CASE:
        1. [point]
        2. [point]
        3. [point]

        BEAR CASE:
        1. [point]
        2. [point]
        3. [point]
        """

        try:
            response = self.llm.invoke(prompt)
            thesis = response.content

            # Parse bull/bear cases with case-insensitive matching
            thesis_upper = thesis.upper()
            bull_idx = thesis_upper.find("BULL CASE")
            bear_idx = thesis_upper.find("BEAR CASE")

            def _extract_points(section: str) -> list:
                """Extract numbered, bulleted, or dashed list items."""
                points = []
                for line in section.split("\n"):
                    stripped = line.strip()
                    if not stripped:
                        continue
                    # Match: "1. ...", "1) ...", "- ...", "* ...", "• ..."
                    if re.match(r'^(\d+[\.\)]\s*|[-*•]\s+)', stripped):
                        # Remove the prefix
                        cleaned = re.sub(r'^(\d+[\.\)]\s*|[-*•]\s+)', '', stripped).strip()
                        if cleaned:
                            points.append(cleaned)
                return points

            # Parse sections — handle any ordering of BULL/BEAR in LLM output (#7)
            if bull_idx != -1:
                # Bull section ends at bear section (only if bear comes after bull)
                bull_end = bear_idx if (bear_idx != -1 and bear_idx > bull_idx) else len(thesis)
                bull_section = thesis[bull_idx:bull_end]
                bull_section = bull_section.split("\n", 1)[1] if "\n" in bull_section else ""
                state["bull_case"] = _extract_points(bull_section) or ["Analysis incomplete"]

            if bear_idx != -1:
                # Bear section ends at bull section (only if bull comes after bear)
                bear_end = bull_idx if (bull_idx != -1 and bull_idx > bear_idx) else len(thesis)
                bear_section = thesis[bear_idx:bear_end]
                bear_section = bear_section.split("\n", 1)[1] if "\n" in bear_section else ""
                state["bear_case"] = _extract_points(bear_section) or ["Analysis incomplete"]

            state["base_case"] = "Base case scenario based on current fundamentals"

        except Exception as e:
            logger.error(f"Error in develop_thesis: {e}")
            _new_errors.append(f"Thesis development error: {str(e)}")
            state["bull_case"] = ["Analysis incomplete"]
            state["bear_case"] = ["Analysis incomplete"]

        state["analysis_steps"] = _new_steps
        state["errors"] = _new_errors
        return state

    def make_recommendation(self, state: EquityAnalystState) -> EquityAnalystState:
        """Step 9: Make final recommendation based on qualitative analysis"""
        _new_steps: list = []
        _new_errors: list = []
        logger.info(f"[Step 9/10] Making recommendation")
        state["current_step"] = "Recommendation"
        _new_steps.append("Recommendation")

        # Composite score across four independent signals
        # Range: moat [-1,+2] + management [-2,+2] + financials [-1,+1] + valuation [-2,+2] = [-6, +7]
        score = 0

        # Signal 1: Moat quality
        moat = state.get("moat_strength", "UNKNOWN")
        if moat == "WIDE":
            score += 2
        elif moat == "NARROW":
            score += 1
        elif moat == "NONE":
            score -= 1
        # UNKNOWN is neutral

        # Signal 2: Management quality
        mgmt = state.get("management_quality", "UNKNOWN")
        if mgmt == "EXCELLENT":
            score += 2
        elif mgmt == "GOOD":
            score += 1
        elif mgmt == "POOR":
            score -= 2
        # FAIR and UNKNOWN are neutral

        # Signal 3: Financial health (revenue CAGR from Step 2)
        cagr = state.get("historical_growth", {}).get("revenue_cagr")
        if cagr is not None:
            if cagr > 0.15:
                score += 1   # Strong growth (>15% CAGR)
            elif cagr < 0:
                score -= 1   # Revenue declining

        # Signal 4: Relative valuation (multiples upside vs. fair value)
        valuation_upside = state.get("valuation_upside", None)
        if valuation_upside is not None:
            if valuation_upside > 25:
                score += 2   # Significantly undervalued
            elif valuation_upside > 10:
                score += 1   # Moderately undervalued
            elif valuation_upside < -25:
                score -= 2   # Significantly overvalued
            elif valuation_upside < -10:
                score -= 1   # Moderately overvalued

        # Signal 5: Earnings beat rate (consistency at meeting expectations)
        beat_rate = state.get("earnings_beat_rate")
        if beat_rate is not None and beat_rate > 0.0:
            if beat_rate >= 0.75:
                score += 1   # Consistently beats expectations
            elif beat_rate <= 0.25:
                score -= 1   # Frequently misses expectations

        if score >= 4:
            state["conviction"] = "HIGH"
        elif score >= 1:
            state["conviction"] = "MEDIUM"
        elif score >= -2:
            state["conviction"] = "MEDIUM"
        else:
            state["conviction"] = "HIGH" if score <= -5 else "MEDIUM"

        # Price target: use multiples fair value if available, else fall back to conviction-based estimate
        fair_value = state.get("fair_value", 0)
        current_price = state.get("current_price", 0)
        if fair_value > 0:
            state["price_target"] = round(fair_value, 2)
        elif current_price > 0:
            multipliers = {
                "HIGH": 1.20,
                "MEDIUM": 1.10,
                "LOW": 1.05,
            }
            mult = multipliers.get(state["conviction"], 1.0)
            state["price_target"] = round(current_price * mult, 2)
        else:
            state["price_target"] = 0.0

        state["analysis_steps"] = _new_steps
        state["errors"] = _new_errors
        return state

    def format_report(self, state: EquityAnalystState) -> EquityAnalystState:
        """Step 10: Format final report"""
        _new_steps: list = []
        _new_errors: list = []
        logger.info(f"[Step 10/10] Formatting final report")
        state["current_step"] = "Complete"
        _new_steps.append("Report")

        ticker = state["ticker"]
        company_name = state.get("company_name", ticker)
        current_price = state.get("current_price", 0)
        conviction = state.get("conviction", "N/A")
        moat_strength = state.get("moat_strength", "Unknown")
        management_quality = state.get("management_quality", "Unknown")
        date_str = datetime.now().strftime("%B %d, %Y")

        # Warnings as blockquote
        warnings = []
        if current_price == 0:
            warnings.append("Current price unavailable — rating may be unreliable.")
        if state.get("errors"):
            warnings.extend(state["errors"])
        warnings_md = ""
        if warnings:
            warnings_md = "> **Note:** " + " ".join(warnings) + "\n\n"

        # Bull/Bear case bullets
        bull_bullets = "\n".join(f"- {p}" for p in state.get("bull_case", [])) or "- No bull case points available."
        bear_bullets = "\n".join(f"- {p}" for p in state.get("bear_case", [])) or "- No bear case points available."

        # Base case / executive summary
        base_case = state.get("base_case", "")
        if not base_case:
            base_case = (
                f"{company_name} has **{conviction}** conviction in the base case. "
                f"The company has a **{moat_strength}** competitive moat and **{management_quality}** "
                f"management quality."
            )

        # Valuation section
        fair_value = state.get("fair_value", 0)
        valuation_upside = state.get("valuation_upside", 0)
        price_target = state.get("price_target", 0)
        multiples_md = state.get("multiples_valuation", "") or "_Multiples valuation unavailable._"

        if fair_value > 0:
            upside_sign = "+" if valuation_upside >= 0 else ""
            valuation_summary = (
                f"**Multiples Fair Value:** ${fair_value:.2f} &nbsp;|&nbsp; "
                f"**Current Price:** ${current_price:.2f} &nbsp;|&nbsp; "
                f"**Implied Upside:** {upside_sign}{valuation_upside:.1f}%\n\n"
            )
        else:
            valuation_summary = ""

        # Price target line for recommendation section
        if price_target > 0:
            pt_source = "multiples valuation" if fair_value > 0 else "rating-based estimate"
            pt_line = f"**Price Target:** ${price_target:.2f} ({pt_source})"
        else:
            pt_line = "_Price target unavailable._"

        # Industry, competitive, management, earnings, SEC sections
        industry_md = state.get("industry_analysis", "") or "_Industry analysis unavailable._"
        competitive_md = state.get("competitive_position", "") or "_Competitor analysis unavailable._"
        mgmt_md = state.get("capital_allocation", "") or "_Management analysis unavailable._"
        earnings_md = state.get("earnings_snapshot", "") or "_Earnings data unavailable._"
        sec_md = state.get("sec_filing_analysis", "") or "_SEC filing analysis unavailable._"

        report = f"""# {company_name} ({ticker})
## Equity Research Report · {date_str}

**Conviction:** {conviction} &nbsp;|&nbsp; **Current Price:** ${current_price:.2f} &nbsp;|&nbsp; **Price Target:** ${price_target:.2f} &nbsp;|&nbsp; **Moat:** {moat_strength} &nbsp;|&nbsp; **Management:** {management_quality}

{warnings_md}---

## Executive Summary

{base_case}

---

## Industry & Competitive Landscape

{industry_md}

---

## Competitive Positioning

{competitive_md}

---

## Management Assessment

{mgmt_md}

---

## Earnings Snapshot

{earnings_md}

---

## Valuation

{valuation_summary}{multiples_md}

---

## SEC Filing Highlights

{sec_md}

---

## Investment Thesis

### Bull Case

{bull_bullets}

### Bear Case

{bear_bullets}

---

## Conviction & Price Target

**Conviction: {conviction}** &nbsp;|&nbsp; {pt_line}

---

*This report was generated by the AI Equity Analyst (LangGraph) on {date_str}. Based on publicly available data. Not investment advice.*"""

        state["final_report"] = report
        state["analysis_steps"] = _new_steps
        state["errors"] = _new_errors
        return state

    def analyze(self, ticker: str, config: Optional[dict] = None) -> dict:
        """Run the complete analysis"""
        # Initialize state
        initial_state = {
            "ticker": ticker.upper(),
            "company_name": "",
            "sector": "",
            "industry": "",
            "current_price": 0.0,
            "company_info": {},
            "financial_metrics": {},
            "historical_growth": {},
            "industry_analysis": "",
            "market_size": "",
            "industry_trends": [],
            "competitors": [],
            "competitive_position": "",
            "market_share": "",
            "moat_strength": "",
            "moat_sources": [],
            "management_quality": "",
            "capital_allocation": "",
            "earnings_snapshot": "",
            "earnings_beat_rate": None,
            "sec_filing_analysis": "",
            "multiples_valuation": "",
            "fair_value": 0.0,
            "valuation_upside": 0.0,
            "bull_case": [],
            "bear_case": [],
            "base_case": "",
            "price_target": 0.0,
            "conviction": "",
            "analysis_steps": [],
            "errors": [],
            "current_step": "Starting",
            "final_report": ""
        }

        # Run the graph — forward callbacks config if provided (#12)
        final_state = self.graph.invoke(initial_state, config=config or {})

        return final_state


class EquityAnalystGraphAdapter:
    """
    Adapter to make LangGraph compatible with existing backend streaming.

    Backend expects: agent.agent_executor.invoke({"input": query}, config={...})
    LangGraph uses: graph.invoke(state, config={...})

    This adapter translates between the two interfaces.
    """

    def __init__(self, graph_agent: EquityAnalystGraph, owner=None):
        self.graph_agent = graph_agent
        self._owner = owner  # GraphWrapper — provides _emit_chart_data

    def _extract_ticker(self, query: str) -> Optional[str]:
        """Extract ticker from user query using multi-pattern matching with blacklist.

        Returns the ticker string, or None if no recognizable ticker is found.
        """
        from backend.config import TICKER_BLACKLIST, COMPANY_TICKER_MAP

        if not query:
            return None

        query_lower = query.lower()

        # Pattern 1: $TICKER format (e.g. "$AAPL")
        match = re.search(r'\$([A-Z]{2,5})\b', query)
        if match:
            return match.group(1).upper()

        # Pattern 2: Ticker with context keyword (e.g. "AAPL stock", "MSFT Analysis")
        # Apply IGNORECASE for the keyword suffix only — then verify the captured
        # ticker group is actually uppercase so "apple stock" doesn't become "APPLE".
        match = re.search(
            r'\b([A-Za-z]{2,5})\b\s*(?:stock|shares|earnings|analysis|price|chart|valuation)',
            query,
            re.IGNORECASE,
        )
        if match:
            candidate = match.group(1)
            # Accept only if the ticker was written in all-caps in the original query
            if candidate == candidate.upper() and candidate not in TICKER_BLACKLIST:
                return candidate.upper()

        # Pattern 3: Company name mapping (e.g. "Apple", "Tesla")
        for company, ticker in COMPANY_TICKER_MAP.items():
            if re.search(r'\b' + company + r'\b', query_lower):
                return ticker

        # Pattern 4: Standalone all-caps ticker in original text (e.g. "Analyze AAPL")
        match = re.search(r'\b([A-Z]{2,5})\b', query)
        if match:
            ticker = match.group(1)
            if ticker not in TICKER_BLACKLIST:
                return ticker

        return None  # No ticker found — caller must handle

    def invoke(self, inputs: dict, config: dict = None):
        """
        Invoke method compatible with LangChain agent_executor interface.

        Args:
            inputs: Dict with 'input' key containing user query
            config: Optional config dict (currently unused for LangGraph)

        Returns:
            Dict with 'output' key containing final report
        """
        query = inputs.get("input", "")
        ticker = self._extract_ticker(query)

        if ticker is None:
            logger.warning(f"[LangGraph] No ticker found in query: '{query}'")
            return {"output": "No stock ticker found in your query. Please specify a ticker (e.g. AAPL, MSFT) or company name."}

        logger.info(f"[LangGraph] Analyzing {ticker}")

        # Run the graph — forward config (includes callbacks for streaming) (#12)
        final_state = self.graph_agent.analyze(ticker, config=config)

        # Emit chart data from all tool outputs collected in state
        if self._owner is not None:
            for key, value in final_state.items():
                if isinstance(value, str):
                    self._owner._emit_chart_data(value)

        # Return in LangChain format
        return {"output": final_state.get("final_report", "Analysis failed")}


def create_equity_analyst_graph(api_key: str = None, model: str = "claude-sonnet-4-5-20250929"):
    """
    Factory function to create equity analyst graph with backend compatibility.

    Returns an object with:
    - analyze(ticker) method for direct CLI usage
    - agent_executor attribute for backend streaming compatibility
    - _progress_queue / _progress_loop for chart data emission (injected by api_server)
    """
    graph = EquityAnalystGraph(api_key=api_key, model=model)

    # Create wrapper object with both interfaces
    class GraphWrapper:
        def __init__(self, graph_instance):
            self.graph = graph_instance
            self.agent_executor = EquityAnalystGraphAdapter(graph_instance, owner=self)
            # Injected by api_server before each request
            self._progress_queue = None
            self._progress_loop = None

        def _emit_chart_data(self, text: str):
            """Extract ---CHART_DATA--- blocks from text and emit as chart_data SSE events."""
            import re as _re
            import json as _json
            queue = self._progress_queue
            loop = self._progress_loop
            if queue is None or loop is None or not isinstance(text, str):
                return
            _CHART_RE = _re.compile(
                r'---CHART_DATA:([^-\n]+)---\n(.*?)\n---END_CHART_DATA:[^-\n]+---',
                _re.DOTALL,
            )
            for match in _CHART_RE.finditer(text):
                try:
                    chart_event = _json.loads(match.group(2).strip())
                    chart_event["type"] = "chart_data"
                    loop.call_soon_threadsafe(queue.put_nowait, chart_event)
                except Exception as e:
                    logger.warning(f"chart_data parse error in graph agent: {e}")

        def analyze(self, query: str) -> str:
            """Direct CLI interface - extracts ticker and runs analysis"""
            adapter = EquityAnalystGraphAdapter(self.graph, owner=self)
            ticker = adapter._extract_ticker(query)
            if ticker is None:
                return f"Could not identify a ticker symbol in: '{query}'. Please specify a ticker (e.g., 'Analyze AAPL')."
            final_state = self.graph.analyze(ticker)
            return final_state.get("final_report", "Analysis failed")



    return GraphWrapper(graph)
