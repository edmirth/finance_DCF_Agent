"""
LangGraph-based Equity Analyst Agent with structured workflow
"""
from typing import TypedDict, Annotated, List
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain.tools import BaseTool
from tools.dcf_tools import get_dcf_tools
from tools.equity_analyst_tools import get_equity_analyst_tools
import os
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

    # Metadata
    analysis_steps: List[str]
    errors: List[str]
    current_step: str


class EquityAnalystGraph:
    """LangGraph-based equity analyst with structured workflow"""

    def __init__(self, api_key: str = None, model: str = "gpt-4-turbo-preview"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self.llm = ChatOpenAI(model=self.model, temperature=0, api_key=self.api_key)

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
        workflow.add_node("get_company_info", self.get_company_info)
        workflow.add_node("get_financial_metrics", self.get_financial_metrics)
        workflow.add_node("analyze_industry", self.analyze_industry)
        workflow.add_node("analyze_competitors", self.analyze_competitors)
        workflow.add_node("analyze_moat", self.analyze_moat)
        workflow.add_node("analyze_management", self.analyze_management)
        workflow.add_node("perform_dcf", self.perform_dcf)
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
        workflow.add_edge("analyze_management", "perform_dcf")
        workflow.add_edge("perform_dcf", "develop_thesis")
        workflow.add_edge("develop_thesis", "make_recommendation")
        workflow.add_edge("make_recommendation", "format_report")
        workflow.add_edge("format_report", END)

        return workflow.compile()

    def get_company_info(self, state: EquityAnalystState) -> EquityAnalystState:
        """Step 1: Get basic company information"""
        logger.info(f"[Step 1/9] Getting company info for {state['ticker']}")
        state["current_step"] = "Company Info"
        state["analysis_steps"].append("✓ Company Info")

        try:
            tool = self.all_tools["get_stock_info"]
            result = tool.run(state["ticker"])

            # Parse result (simplified - you'd want better parsing)
            state["company_info"] = {"raw": result}

            # Extract key fields (you'd parse from result string)
            if "Company:" in result:
                state["company_name"] = result.split("Company:")[1].split("\n")[0].strip()
            if "Sector:" in result:
                state["sector"] = result.split("Sector:")[1].split("\n")[0].strip()
            if "Industry:" in result:
                state["industry"] = result.split("Industry:")[1].split("\n")[0].strip()
            if "Current Price:" in result:
                price_str = result.split("Current Price: $")[1].split("\n")[0].strip()
                state["current_price"] = float(price_str.replace(",", ""))

        except Exception as e:
            logger.error(f"Error in get_company_info: {e}")
            state["errors"].append(f"Company info error: {str(e)}")

        return state

    def get_financial_metrics(self, state: EquityAnalystState) -> EquityAnalystState:
        """Step 2: Get financial metrics"""
        logger.info(f"[Step 2/9] Getting financial metrics")
        state["current_step"] = "Financial Metrics"
        state["analysis_steps"].append("✓ Financial Metrics")

        try:
            tool = self.all_tools["get_financial_metrics"]
            result = tool.run(state["ticker"])
            state["financial_metrics"] = {"raw": result}

            # Extract growth rates
            if "Revenue CAGR:" in result:
                growth_str = result.split("Revenue CAGR:")[1].split("%")[0].strip()
                state["historical_growth"] = {"revenue_cagr": float(growth_str) / 100}

        except Exception as e:
            logger.error(f"Error in get_financial_metrics: {e}")
            state["errors"].append(f"Financial metrics error: {str(e)}")

        return state

    def analyze_industry(self, state: EquityAnalystState) -> EquityAnalystState:
        """Step 3: Industry analysis"""
        logger.info(f"[Step 3/9] Analyzing industry")
        state["current_step"] = "Industry Analysis"
        state["analysis_steps"].append("✓ Industry Analysis")

        try:
            tool = self.all_tools["analyze_industry"]
            result = tool.run(
                company=state["company_name"],
                ticker=state["ticker"],
                sector=state["sector"]
            )
            state["industry_analysis"] = result

        except Exception as e:
            logger.error(f"Error in analyze_industry: {e}")
            state["errors"].append(f"Industry analysis error: {str(e)}")
            state["industry_analysis"] = "Industry analysis unavailable"

        return state

    def analyze_competitors(self, state: EquityAnalystState) -> EquityAnalystState:
        """Step 4: Competitive analysis"""
        logger.info(f"[Step 4/9] Analyzing competitors")
        state["current_step"] = "Competitive Analysis"
        state["analysis_steps"].append("✓ Competitive Analysis")

        try:
            tool = self.all_tools["analyze_competitors"]
            result = tool.run(
                company=state["company_name"],
                ticker=state["ticker"],
                industry=state["industry"]
            )
            state["competitive_position"] = result

        except Exception as e:
            logger.error(f"Error in analyze_competitors: {e}")
            state["errors"].append(f"Competitor analysis error: {str(e)}")
            state["competitive_position"] = "Competitor analysis unavailable"

        return state

    def analyze_moat(self, state: EquityAnalystState) -> EquityAnalystState:
        """Step 5: Moat analysis"""
        logger.info(f"[Step 5/9] Analyzing competitive moat")
        state["current_step"] = "Moat Analysis"
        state["analysis_steps"].append("✓ Moat Analysis")

        try:
            tool = self.all_tools["analyze_moat"]
            result = tool.run(
                company=state["company_name"],
                ticker=state["ticker"]
            )

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
        logger.info(f"[Step 6/9] Analyzing management quality")
        state["current_step"] = "Management Analysis"
        state["analysis_steps"].append("✓ Management Analysis")

        try:
            tool = self.all_tools["analyze_management"]
            result = tool.run(
                company=state["company_name"],
                ticker=state["ticker"]
            )
            state["capital_allocation"] = result

            # Determine management quality from result
            if "Excellent" in result:
                state["management_quality"] = "EXCELLENT"
            elif "Good" in result:
                state["management_quality"] = "GOOD"
            elif "Fair" in result:
                state["management_quality"] = "FAIR"
            else:
                state["management_quality"] = "POOR"

        except Exception as e:
            logger.error(f"Error in analyze_management: {e}")
            state["errors"].append(f"Management analysis error: {str(e)}")
            state["management_quality"] = "UNKNOWN"

        return state

    def perform_dcf(self, state: EquityAnalystState) -> EquityAnalystState:
        """Step 7: DCF valuation"""
        logger.info(f"[Step 7/9] Performing DCF analysis")
        state["current_step"] = "DCF Valuation"
        state["analysis_steps"].append("✓ DCF Valuation")

        try:
            # Search for current beta
            search_tool = self.all_tools["search_web"]
            beta_search = search_tool.run(f"{state['ticker']} beta coefficient 2024")

            # Extract beta (simplified - you'd want better parsing)
            beta = 1.0  # default

            # Perform DCF
            dcf_tool = self.all_tools["perform_dcf_analysis"]
            result = dcf_tool.run(
                ticker=state["ticker"],
                beta=beta,
                revenue_growth_rate=state.get("historical_growth", {}).get("revenue_cagr", 0.10),
                fcf_margin=0.15,  # Would calculate from financials
                terminal_growth_rate=0.025,
                risk_free_rate=0.04,
                market_risk_premium=0.08
            )

            state["dcf_results"] = {"raw": result}

            # Extract intrinsic value (simplified parsing)
            if "Intrinsic Value per Share:" in result:
                value_str = result.split("Intrinsic Value per Share: $")[1].split("\n")[0]
                state["intrinsic_value"] = float(value_str.replace(",", ""))
                state["upside_potential"] = (state["intrinsic_value"] / state["current_price"] - 1) * 100

        except Exception as e:
            logger.error(f"Error in perform_dcf: {e}")
            state["errors"].append(f"DCF error: {str(e)}")
            state["intrinsic_value"] = 0
            state["upside_potential"] = 0

        return state

    def develop_thesis(self, state: EquityAnalystState) -> EquityAnalystState:
        """Step 8: Develop investment thesis"""
        logger.info(f"[Step 8/9] Developing investment thesis")
        state["current_step"] = "Investment Thesis"
        state["analysis_steps"].append("✓ Investment Thesis")

        # Use LLM to synthesize bull/bear cases from all analysis
        prompt = f"""Based on the following analysis for {state['company_name']} ({state['ticker']}),
        develop a concise bull case (3 points) and bear case (3 points):

        Industry: {state.get('industry_analysis', 'N/A')[:500]}
        Competitive Position: {state.get('competitive_position', 'N/A')[:500]}
        Moat: {state.get('moat_strength', 'UNKNOWN')}
        Management: {state.get('management_quality', 'UNKNOWN')}
        Intrinsic Value: ${state.get('intrinsic_value', 0):.2f} vs Current: ${state.get('current_price', 0):.2f}

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

            # Parse bull/bear cases
            if "BULL CASE:" in thesis:
                bull_section = thesis.split("BULL CASE:")[1].split("BEAR CASE:")[0]
                state["bull_case"] = [line.strip() for line in bull_section.split("\n") if line.strip() and line.strip()[0].isdigit()]

            if "BEAR CASE:" in thesis:
                bear_section = thesis.split("BEAR CASE:")[1]
                state["bear_case"] = [line.strip() for line in bear_section.split("\n") if line.strip() and line.strip()[0].isdigit()]

            state["base_case"] = "Base case scenario based on current fundamentals"

        except Exception as e:
            logger.error(f"Error in develop_thesis: {e}")
            state["errors"].append(f"Thesis development error: {str(e)}")
            state["bull_case"] = ["Analysis incomplete"]
            state["bear_case"] = ["Analysis incomplete"]

        return state

    def make_recommendation(self, state: EquityAnalystState) -> EquityAnalystState:
        """Step 9: Make final recommendation"""
        logger.info(f"[Step 9/9] Making recommendation")
        state["current_step"] = "Recommendation"
        state["analysis_steps"].append("✓ Recommendation")

        # Recommendation logic
        upside = state.get("upside_potential", 0)

        if upside > 20:
            state["rating"] = "BUY"
            state["conviction"] = "HIGH" if upside > 40 else "MEDIUM"
        elif upside > -20:
            state["rating"] = "HOLD"
            state["conviction"] = "MEDIUM"
        else:
            state["rating"] = "SELL"
            state["conviction"] = "HIGH" if upside < -40 else "MEDIUM"

        # Price target (simplified)
        state["price_target"] = state.get("intrinsic_value", state.get("current_price", 0))

        return state

    def format_report(self, state: EquityAnalystState) -> EquityAnalystState:
        """Step 10: Format final report"""
        logger.info(f"Formatting final report")
        state["current_step"] = "Complete"

        report = f"""
================================================================================
EQUITY RESEARCH REPORT: {state.get('company_name', 'N/A')} ({state['ticker']})
Analyst: AI Equity Analyst (LangGraph) | Date: {datetime.now().strftime('%Y-%m-%d')}
================================================================================

INVESTMENT RATING: {state.get('rating', 'N/A')}
Price Target (12M): ${state.get('price_target', 0):.2f} (Current: ${state.get('current_price', 0):.2f})
Upside Potential: {state.get('upside_potential', 0):.1f}%
Conviction: {state.get('conviction', 'N/A')}

WORKFLOW STEPS COMPLETED:
{chr(10).join(state.get('analysis_steps', []))}

COMPETITIVE MOAT: {state.get('moat_strength', 'UNKNOWN')}
MANAGEMENT QUALITY: {state.get('management_quality', 'UNKNOWN')}

BULL CASE:
{chr(10).join(state.get('bull_case', ['N/A']))}

BEAR CASE:
{chr(10).join(state.get('bear_case', ['N/A']))}

VALUATION:
Intrinsic Value: ${state.get('intrinsic_value', 0):.2f}
Current Price: ${state.get('current_price', 0):.2f}
Upside: {state.get('upside_potential', 0):.1f}%

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


def create_equity_analyst_graph(api_key: str = None, model: str = "gpt-4-turbo-preview") -> EquityAnalystGraph:
    """Factory function to create equity analyst graph"""
    return EquityAnalystGraph(api_key=api_key, model=model)
