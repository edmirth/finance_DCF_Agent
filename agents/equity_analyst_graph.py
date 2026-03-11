"""
LangGraph-based Equity Analyst Agent with structured workflow
"""
from typing import TypedDict, Annotated, List, Optional
from langgraph.graph import StateGraph, END
from langchain_anthropic import ChatAnthropic
from langchain.tools import BaseTool
from tools.dcf_tools import get_dcf_tools
from tools.equity_analyst_tools import get_equity_analyst_tools
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

    # Step 7: DCF valuation
    dcf_results: dict
    intrinsic_value: float
    upside_potential: float

    # Step 8: Investment thesis
    bull_case: List[str]
    bear_case: List[str]
    base_case: str

    # Step 9: Final recommendation
    rating: str  # BUY, HOLD, SELL
    price_target: float
    conviction: str  # HIGH, MEDIUM, LOW

    # Output
    final_report: str

    # Metadata
    analysis_steps: List[str]
    errors: List[str]
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
        self.dcf_tools = {tool.name: tool for tool in get_dcf_tools()}
        self.analyst_tools = {tool.name: tool for tool in get_equity_analyst_tools()}
        self.all_tools = {**self.dcf_tools, **self.analyst_tools}

        # Build graph
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow"""

        # Create graph
        workflow = StateGraph(EquityAnalystState)

        # Add nodes (each is a step in the analysis)
        # Note: DCF node removed — tool not working properly yet
        workflow.add_node("get_company_info", self.get_company_info)
        workflow.add_node("get_financial_metrics", self.get_financial_metrics)
        workflow.add_node("analyze_industry", self.analyze_industry)
        workflow.add_node("analyze_competitors", self.analyze_competitors)
        workflow.add_node("analyze_moat", self.analyze_moat)
        workflow.add_node("analyze_management", self.analyze_management)
        workflow.add_node("develop_thesis", self.develop_thesis)
        workflow.add_node("make_recommendation", self.make_recommendation)
        workflow.add_node("format_report", self.format_report)

        # Define the workflow
        workflow.set_entry_point("get_company_info")
        workflow.add_edge("get_company_info", "get_financial_metrics")
        workflow.add_edge("get_financial_metrics", "analyze_industry")
        workflow.add_edge("analyze_industry", "analyze_competitors")
        workflow.add_edge("analyze_competitors", "analyze_moat")
        workflow.add_edge("analyze_moat", "analyze_management")
        workflow.add_edge("analyze_management", "develop_thesis")
        workflow.add_edge("develop_thesis", "make_recommendation")
        workflow.add_edge("make_recommendation", "format_report")
        workflow.add_edge("format_report", END)

        return workflow.compile()

    def get_company_info(self, state: EquityAnalystState) -> EquityAnalystState:
        """Step 1: Get basic company information"""
        logger.info(f"[Step 1/8] Getting company info for {state['ticker']}")
        state["current_step"] = "Company Info"
        state["analysis_steps"].append("✓ Company Info")

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
            state["errors"].append(f"Company info error: {str(e)}")

        # Validate critical fields — use ticker as fallback for company_name
        if not state.get("company_name"):
            state["company_name"] = state["ticker"]
            logger.warning(f"company_name not found, using ticker '{state['ticker']}' as fallback")

        return state

    def get_financial_metrics(self, state: EquityAnalystState) -> EquityAnalystState:
        """Step 2: Get financial metrics"""
        logger.info(f"[Step 2/8] Getting financial metrics")
        state["current_step"] = "Financial Metrics"
        state["analysis_steps"].append("✓ Financial Metrics")

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
            state["errors"].append(f"Financial metrics error: {str(e)}")

        return state

    def analyze_industry(self, state: EquityAnalystState) -> EquityAnalystState:
        """Step 3: Industry analysis"""
        logger.info(f"[Step 3/8] Analyzing industry")
        state["current_step"] = "Industry Analysis"
        state["analysis_steps"].append("✓ Industry Analysis")

        try:
            tool = self.all_tools["analyze_industry"]
            result = tool.invoke({
                "company": state["company_name"],
                "ticker": state["ticker"],
                "sector": state["sector"]
            })
            state["industry_analysis"] = result

        except Exception as e:
            logger.error(f"Error in analyze_industry: {e}")
            state["errors"].append(f"Industry analysis error: {str(e)}")
            state["industry_analysis"] = "Industry analysis unavailable"

        return state

    def analyze_competitors(self, state: EquityAnalystState) -> EquityAnalystState:
        """Step 4: Competitive analysis"""
        logger.info(f"[Step 4/8] Analyzing competitors")
        state["current_step"] = "Competitive Analysis"
        state["analysis_steps"].append("✓ Competitive Analysis")

        try:
            tool = self.all_tools["analyze_competitors"]
            result = tool.invoke({
                "company": state["company_name"],
                "ticker": state["ticker"],
                "industry": state["industry"]
            })
            state["competitive_position"] = result

        except Exception as e:
            logger.error(f"Error in analyze_competitors: {e}")
            state["errors"].append(f"Competitor analysis error: {str(e)}")
            state["competitive_position"] = "Competitor analysis unavailable"

        return state

    def analyze_moat(self, state: EquityAnalystState) -> EquityAnalystState:
        """Step 5: Moat analysis"""
        logger.info(f"[Step 5/8] Analyzing competitive moat")
        state["current_step"] = "Moat Analysis"
        state["analysis_steps"].append("✓ Moat Analysis")

        try:
            tool = self.all_tools["analyze_moat"]
            result = tool.invoke({
                "company": state["company_name"],
                "ticker": state["ticker"]
            })

            # Determine moat strength from result
            if "Wide Moat" in result or "wide moat" in result.lower():
                state["moat_strength"] = "WIDE"
            elif "Narrow Moat" in result or "narrow moat" in result.lower():
                state["moat_strength"] = "NARROW"
            else:
                state["moat_strength"] = "NONE"

            state["moat_sources"] = []  # Would parse from result

        except Exception as e:
            logger.error(f"Error in analyze_moat: {e}")
            state["errors"].append(f"Moat analysis error: {str(e)}")
            state["moat_strength"] = "UNKNOWN"

        return state

    def analyze_management(self, state: EquityAnalystState) -> EquityAnalystState:
        """Step 6: Management analysis"""
        logger.info(f"[Step 6/8] Analyzing management quality")
        state["current_step"] = "Management Analysis"
        state["analysis_steps"].append("✓ Management Analysis")

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
            elif _has_word(result_lower, ["excellent", "exceptional", "outstanding", "best-in-class"]):
                state["management_quality"] = "EXCELLENT"
            elif _has_word(result_lower, ["strong leadership", "strong management", "good management", "effective leadership", "capable", "proven track record", "well-regarded"]):
                state["management_quality"] = "GOOD"
            elif _has_word(result_lower, ["fair", "adequate", "mixed", "average"]):
                state["management_quality"] = "FAIR"
            elif _has_word(result_lower, ["poor", "weak leadership", "weak management", "concerning", "questionable"]):
                state["management_quality"] = "POOR"
            else:
                state["management_quality"] = "UNKNOWN"

        except Exception as e:
            logger.error(f"Error in analyze_management: {e}")
            state["errors"].append(f"Management analysis error: {str(e)}")
            state["management_quality"] = "UNKNOWN"

        return state

    def _parse_market_param(self, text: str, label: str) -> Optional[float]:
        """Extract a numeric value from get_market_parameters output by label."""
        for line in text.split("\n"):
            if label in line:
                # Find the first number after the label (e.g. "Beta:  1.15")
                match = re.search(r'[\d.]+', line.split(label)[-1])
                if match:
                    try:
                        return float(match.group())
                    except ValueError:
                        pass
        return None

    def perform_dcf(self, state: EquityAnalystState) -> EquityAnalystState:
        """Step 7: DCF valuation using real market parameters"""
        logger.info(f"[Step 7/9] Performing DCF analysis")
        state["current_step"] = "DCF Valuation"
        state["analysis_steps"].append("✓ DCF Valuation")

        try:
            # Fetch real market parameters (beta, risk-free rate, growth rates)
            market_params_tool = self.all_tools["get_market_parameters"]
            market_params_result = market_params_tool.invoke({
                "ticker": state["ticker"],
                "company_name": state.get("company_name", ""),
                "industry": state.get("industry", ""),
            })

            # Parse actual values from the structured output
            beta = self._parse_market_param(market_params_result, "Beta:")
            risk_free_rate = self._parse_market_param(market_params_result, "Risk-Free Rate:")
            near_term_growth = self._parse_market_param(market_params_result, "Near-Term Growth Rate:")
            industry_growth = self._parse_market_param(market_params_result, "Industry Growth Rate:")

            # If near-term growth wasn't found by get_market_parameters,
            # try a direct web search for analyst consensus as a second attempt
            if near_term_growth is None:
                logger.info(f"Near-term growth not found via market params, trying direct web search")
                try:
                    search_tool = self.all_tools["search_web"]
                    growth_search = search_tool.invoke({
                        "query": f"{state['ticker']} {state.get('company_name', '')} analyst consensus revenue growth rate forecast 2025 2026"
                    })
                    # Try to extract a percentage from the search result
                    pct_matches = re.findall(r'(\d+\.?\d*)\s*%', growth_search)
                    for pct_str in pct_matches:
                        pct = float(pct_str) / 100
                        if 0.01 <= pct <= 0.50:  # Reasonable growth range: 1% to 50%
                            near_term_growth = pct
                            logger.info(f"Extracted near-term growth from web search: {pct:.1%}")
                            break
                except Exception as e:
                    logger.warning(f"Web search fallback for growth rate failed: {e}")

            # Final fallback: use historical CAGR
            historical_cagr = state.get("historical_growth", {}).get("revenue_cagr")
            if near_term_growth is None and historical_cagr and historical_cagr > 0:
                near_term_growth = historical_cagr
                logger.warning(f"Using historical CAGR as fallback for near-term growth: {historical_cagr:.1%}")

            # Build DCF params with parsed values, fallback to sensible defaults
            dcf_params = {
                "ticker": state["ticker"],
                "beta": beta if beta is not None else 1.0,
                "risk_free_rate": risk_free_rate if risk_free_rate is not None else 0.045,
                "near_term_growth_rate": near_term_growth if near_term_growth is not None else 0.08,
                "long_term_growth_rate": industry_growth if industry_growth is not None else 0.05,
                "terminal_growth_rate": 0.025,
                "market_risk_premium": 0.055,
            }

            logger.info(f"DCF params for {state['ticker']}: beta={dcf_params['beta']}, rfr={dcf_params['risk_free_rate']}, growth={dcf_params['near_term_growth_rate']}")

            # Perform DCF with real parameters
            dcf_tool = self.all_tools["perform_dcf_analysis"]
            result = dcf_tool.invoke(dcf_params)

            state["dcf_results"] = {"raw": result, "params": dcf_params}

            # Extract base-case intrinsic value explicitly
            # The DCF output contains multiple scenarios (BASE, BULL, BEAR).
            # Find the BASE section and extract its intrinsic value to avoid
            # depending on dict insertion order.
            base_value = None
            base_marker = result.upper().find("BASE SCENARIO")
            if base_marker != -1:
                base_section = result[base_marker:]
                iv_marker = base_section.find("Intrinsic Value per Share: $")
                if iv_marker != -1:
                    value_str = base_section[iv_marker + len("Intrinsic Value per Share: $"):].split("\n")[0]
                    base_value = float(value_str.replace(",", ""))

            # Fallback: if BASE section not found, use the first occurrence
            if base_value is None and "Intrinsic Value per Share: $" in result:
                value_str = result.split("Intrinsic Value per Share: $")[1].split("\n")[0]
                base_value = float(value_str.replace(",", ""))

            if base_value is not None:
                state["intrinsic_value"] = base_value
                if state.get("current_price", 0) > 0:
                    state["upside_potential"] = (state["intrinsic_value"] / state["current_price"] - 1) * 100

        except Exception as e:
            logger.error(f"Error in perform_dcf: {e}")
            state["errors"].append(f"DCF error: {str(e)}")
            state["intrinsic_value"] = 0
            state["upside_potential"] = 0

        return state

    def develop_thesis(self, state: EquityAnalystState) -> EquityAnalystState:
        """Step 8: Develop investment thesis"""
        logger.info(f"[Step 7/8] Developing investment thesis")
        state["current_step"] = "Investment Thesis"
        state["analysis_steps"].append("✓ Investment Thesis")

        # Use LLM to synthesize bull/bear cases from all analysis
        prompt = f"""Based on the following analysis for {state['company_name']} ({state['ticker']}),
        develop a concise bull case (3 points) and bear case (3 points):

        Industry: {state.get('industry_analysis', 'N/A')[:500]}
        Competitive Position: {state.get('competitive_position', 'N/A')[:500]}
        Moat: {state.get('moat_strength', 'UNKNOWN')}
        Management: {state.get('management_quality', 'UNKNOWN')}
        Current Price: ${state.get('current_price', 0):.2f}

        Format as:
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

            if bull_idx != -1:
                bull_end = bear_idx if bear_idx > bull_idx else len(thesis)
                # Skip past the "BULL CASE:" header line
                bull_section = thesis[bull_idx:bull_end]
                bull_section = bull_section.split("\n", 1)[1] if "\n" in bull_section else ""
                state["bull_case"] = _extract_points(bull_section) or ["Analysis incomplete"]

            if bear_idx != -1:
                bear_section = thesis[bear_idx:]
                bear_section = bear_section.split("\n", 1)[1] if "\n" in bear_section else ""
                state["bear_case"] = _extract_points(bear_section) or ["Analysis incomplete"]

            state["base_case"] = "Base case scenario based on current fundamentals"

        except Exception as e:
            logger.error(f"Error in develop_thesis: {e}")
            state["errors"].append(f"Thesis development error: {str(e)}")
            state["bull_case"] = ["Analysis incomplete"]
            state["bear_case"] = ["Analysis incomplete"]

        return state

    def make_recommendation(self, state: EquityAnalystState) -> EquityAnalystState:
        """Step 8: Make final recommendation based on qualitative analysis"""
        logger.info(f"[Step 8/8] Making recommendation")
        state["current_step"] = "Recommendation"
        state["analysis_steps"].append("✓ Recommendation")

        # Score-based recommendation from qualitative factors
        # Each factor contributes to a composite score
        score = 0  # Range roughly -4 to +4

        moat = state.get("moat_strength", "UNKNOWN")
        if moat == "WIDE":
            score += 2
        elif moat == "NARROW":
            score += 1
        elif moat == "NONE":
            score -= 1

        mgmt = state.get("management_quality", "UNKNOWN")
        if mgmt == "EXCELLENT":
            score += 2
        elif mgmt == "GOOD":
            score += 1
        elif mgmt == "POOR":
            score -= 2
        elif mgmt == "FAIR":
            pass  # Neutral — average management is not a negative signal

        # Bull/bear case balance
        bull_count = len(state.get("bull_case", []))
        bear_count = len(state.get("bear_case", []))
        if bull_count > bear_count:
            score += 1
        elif bear_count > bull_count:
            score -= 1

        if score >= 3:
            state["rating"] = "BUY"
            state["conviction"] = "HIGH"
        elif score >= 1:
            state["rating"] = "BUY"
            state["conviction"] = "MEDIUM"
        elif score >= -1:
            state["rating"] = "HOLD"
            state["conviction"] = "MEDIUM"
        else:
            state["rating"] = "SELL"
            state["conviction"] = "HIGH" if score <= -3 else "MEDIUM"

        state["price_target"] = state.get("current_price", 0)

        return state

    def format_report(self, state: EquityAnalystState) -> EquityAnalystState:
        """Step 10: Format final report"""
        logger.info(f"Formatting final report")
        state["current_step"] = "Complete"

        # Build warnings for missing/suspect data
        warnings = []
        if state.get("current_price", 0) == 0:
            warnings.append("Current price unavailable — rating may be unreliable")
        if state.get("errors"):
            warnings.extend(state["errors"])

        warnings_section = ""
        if warnings:
            warnings_section = "\nWARNINGS:\n" + "\n".join(f"  ⚠ {w}" for w in warnings) + "\n"

        report = f"""
================================================================================
EQUITY RESEARCH REPORT: {state.get('company_name', 'N/A')} ({state['ticker']})
Analyst: AI Equity Analyst (LangGraph) | Date: {datetime.now().strftime('%Y-%m-%d')}
================================================================================
{warnings_section}
INVESTMENT RATING: {state.get('rating', 'N/A')}
Current Price: ${state.get('current_price', 0):.2f}
Conviction: {state.get('conviction', 'N/A')}

WORKFLOW STEPS COMPLETED:
{chr(10).join(state.get('analysis_steps', []))}

COMPETITIVE MOAT: {state.get('moat_strength', 'UNKNOWN')}
MANAGEMENT QUALITY: {state.get('management_quality', 'UNKNOWN')}

BULL CASE:
{chr(10).join(state.get('bull_case', ['N/A']))}

BEAR CASE:
{chr(10).join(state.get('bear_case', ['N/A']))}

================================================================================
        """

        state["final_report"] = report
        return state

    def analyze(self, ticker: str) -> dict:
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
            "dcf_results": {},
            "intrinsic_value": 0.0,
            "upside_potential": 0.0,
            "bull_case": [],
            "bear_case": [],
            "base_case": "",
            "rating": "",
            "price_target": 0.0,
            "conviction": "",
            "analysis_steps": [],
            "errors": [],
            "current_step": "Starting",
            "final_report": ""
        }

        # Run the graph
        final_state = self.graph.invoke(initial_state)

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

    def _extract_ticker(self, query: str) -> str:
        """Extract ticker from user query using multi-pattern matching with blacklist."""
        from backend.config import TICKER_BLACKLIST, COMPANY_TICKER_MAP

        if not query:
            return "AAPL"

        query_lower = query.lower()

        # Pattern 1: $TICKER format (e.g. "$AAPL")
        match = re.search(r'\$([A-Z]{2,5})\b', query)
        if match:
            return match.group(1).upper()

        # Pattern 2: Ticker with context keyword (e.g. "AAPL stock", "MSFT analysis")
        match = re.search(
            r'\b([A-Z]{2,5})\b\s*(?:stock|shares|earnings|analysis|price|chart|valuation)',
            query, re.IGNORECASE,
        )
        if match:
            ticker = match.group(1).upper()
            if ticker not in TICKER_BLACKLIST:
                return ticker

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

        return "AAPL"  # Default fallback

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

        logger.info(f"[LangGraph] Analyzing {ticker}")

        # Run the graph
        final_state = self.graph_agent.analyze(ticker)

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
            final_state = self.graph.analyze(ticker)
            return final_state.get("final_report", "Analysis failed")

    return GraphWrapper(graph)
