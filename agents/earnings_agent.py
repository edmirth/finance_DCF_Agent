"""
Earnings-Focused Equity Research Agent using LangGraph

Generates equity research reports focusing on:
- Latest earnings reports & historical trends
- Analyst estimates & earnings surprises
- Management guidance analysis
- Competitive comparison
- Investment thesis with BUY/HOLD/SELL rating

7-node workflow: data gathering (parallel) → analysis (1 LLM call) → thesis (1 LLM call) → report
"""
from typing import TypedDict, List, Optional, Annotated
import operator
from langgraph.graph import StateGraph, END
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
import time
import logging
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# State Reducers
# ============================================================================

def keep_first(left, right):
    """Reducer that keeps the first non-None/non-empty value"""
    return left if left else right


# ============================================================================
# State Schema
# ============================================================================

class EarningsAnalysisState(TypedDict):
    # Input
    ticker: Annotated[str, keep_first]
    quarters_back: Annotated[int, keep_first]

    # Company Context (Node 1)
    company_name: Annotated[str, keep_first]
    sector: Annotated[str, keep_first]
    industry: Annotated[str, keep_first]
    current_price: Annotated[float, keep_first]
    market_cap: Annotated[float, keep_first]

    # Raw Data (Nodes 2-4, parallel)
    earnings_history: Annotated[str, keep_first]
    analyst_estimates: Annotated[str, keep_first]
    earnings_surprises: Annotated[str, keep_first]
    earnings_guidance: Annotated[str, keep_first]
    peer_comparison: Annotated[str, keep_first]

    # Analysis (Node 6 — single LLM call)
    comprehensive_analysis: Annotated[str, keep_first]
    management_accountability: Annotated[str, keep_first]

    # Thesis (Node 7 — single LLM call)
    investment_thesis: Annotated[str, keep_first]
    rating: Annotated[str, keep_first]
    price_target: Annotated[float, keep_first]
    key_catalysts: Annotated[List[str], keep_first]
    key_risks: Annotated[List[str], keep_first]

    # Output
    final_report: Annotated[str, keep_first]

    # Metadata
    start_time: Annotated[float, keep_first]
    errors: Annotated[List[str], operator.add]


# ============================================================================
# Backend Compatibility Adapter
# ============================================================================

class EarningsAgentExecutorAdapter:
    """Adapter: translates backend invoke() calls to LangGraph invoke()."""

    def __init__(self, graph, agent_owner):
        self.graph = graph
        self.agent_owner = agent_owner
        self.ticker_pattern = re.compile(r'\b[A-Z]{1,5}\b')
        self.last_state = None
        self.last_ticker = None

    def invoke(self, input_dict: dict, config: Optional[dict] = None) -> dict:
        try:
            query = input_dict.get("input", "")
            is_followup = input_dict.get("followup", False)

            # Follow-up mode: use cached state, 1 LLM call
            if is_followup and self.last_state:
                return self._answer_followup(query, config)

            ticker = self._extract_ticker(query)

            if not ticker:
                return {"output": "Error: Please provide a stock ticker symbol (e.g., AAPL, MSFT, NVDA)"}

            logger.info(f"Starting earnings analysis for {ticker}")

            initial_state = {
                "ticker": ticker,
                "quarters_back": 8,
                "company_name": "",
                "sector": "",
                "industry": "",
                "current_price": 0.0,
                "market_cap": 0.0,
                "earnings_history": "",
                "analyst_estimates": "",
                "earnings_surprises": "",
                "earnings_guidance": "",
                "peer_comparison": "",
                "comprehensive_analysis": "",
                "management_accountability": "",
                "investment_thesis": "",
                "rating": "",
                "price_target": 0.0,
                "key_catalysts": [],
                "key_risks": [],
                "final_report": "",
                "start_time": time.time(),
                "errors": []
            }

            result = self.graph.invoke(initial_state, config=config)

            # Cache state for follow-ups
            self.last_state = result
            self.last_ticker = ticker

            execution_time = time.time() - result["start_time"]
            logger.info(f"Earnings analysis completed in {execution_time:.1f} seconds")

            final_output = result.get("final_report", "Error: No report generated")
            final_output += f"\n\n---\n*Analysis completed in {execution_time/60:.1f} minutes*"

            return {"output": final_output}

        except Exception as e:
            logger.error(f"Error in earnings agent: {e}")
            return {"output": f"Error analyzing earnings: {str(e)}"}

    def _answer_followup(self, question: str, config: Optional[dict] = None) -> dict:
        """Answer follow-up using cached analysis state. Single LLM call."""
        state = self.last_state
        logger.info(f"Answering follow-up for {state['ticker']}: {question[:80]}...")

        try:
            prompt = f"""You are a senior equity research analyst. You just completed a comprehensive
earnings analysis for {state['company_name']} ({state['ticker']}).

ANALYSIS CONTEXT:
{state['comprehensive_analysis']}

EARNINGS DATA:
{state['earnings_history'][:3000]}

MANAGEMENT GUIDANCE:
{state['earnings_guidance'][:3000]}

INVESTMENT THESIS:
{state['investment_thesis']}

The investor now asks: {question}

Provide a focused, data-driven answer. Reference specific numbers from the analysis.
Be concise (2-4 paragraphs). If the question requires data you don't have, say so."""

            llm = ChatAnthropic(
                model=self.agent_owner.model,
                temperature=0,
                max_retries=3,
                default_request_timeout=60.0,
                max_tokens=4096,
            )
            response = llm.invoke(
                [
                    SystemMessage(content="You are a senior equity research analyst answering follow-up questions."),
                    HumanMessage(content=prompt),
                ],
                config=config,
            )

            logger.info(f"Follow-up answered ({len(response.content)} chars)")
            return {"output": response.content}

        except Exception as e:
            logger.error(f"Error answering follow-up: {e}")
            return {"output": f"Error answering follow-up: {str(e)}"}

    def _extract_ticker(self, query: str) -> Optional[str]:
        """Extract ticker symbol from user query"""
        query_upper = query.upper()

        KNOWN_TICKERS = {
            'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'NVDA', 'TSLA',
            'META', 'NFLX', 'AMD', 'INTC', 'CSCO', 'ADBE', 'CRM',
            'ORCL', 'IBM', 'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C',
            'V', 'MA', 'PYPL', 'SQ', 'DIS', 'CMCSA', 'T', 'VZ',
            'KO', 'PEP', 'WMT', 'TGT', 'HD', 'LOW', 'NKE', 'SBUX',
            'MCD', 'BA', 'CAT', 'DE', 'MMM', 'GE', 'F', 'GM',
        }
        COMMON_WORDS = {'THE', 'AND', 'FOR', 'WITH', 'FROM', 'ABOUT', 'WHAT', 'HOW', 'WHY'}

        for word in query_upper.split():
            clean_word = re.sub(r'[^\w]', '', word)
            if 1 <= len(clean_word) <= 5 and clean_word.isalpha() and clean_word in KNOWN_TICKERS:
                return clean_word

        matches = self.ticker_pattern.findall(query_upper)
        for match in matches:
            if match not in COMMON_WORDS:
                return match

        return None


# ============================================================================
# Earnings Agent
# ============================================================================

class EarningsAgent:
    """
    LangGraph-based earnings research agent.

    7-node workflow:
    1. Fetch company info
    2-4. Parallel: Fetch earnings history, analyst estimates, surprises+transcripts+peers
    5. Aggregate (sync point)
    6. Comprehensive analysis (1 LLM call)
    7. Investment thesis + rating (1 LLM call)
    8. Generate report
    """

    def __init__(self, model: str = "claude-sonnet-4-5-20250929"):
        self.model = model
        self.llm = ChatAnthropic(
            model=model,
            temperature=0,
            max_retries=3,
            default_request_timeout=60.0,
            max_tokens=8192,
        )

        from tools.earnings_tools import get_earnings_tools
        self.tools = get_earnings_tools()

        self.graph = self._build_graph()
        self.agent_executor = EarningsAgentExecutorAdapter(self.graph, agent_owner=self)

        logger.info(f"Earnings Agent initialized with model: {model}")

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(EarningsAnalysisState)

        # Nodes
        workflow.add_node("fetch_company_info", self.fetch_company_info)
        workflow.add_node("fetch_earnings_history", self.fetch_earnings_history)
        workflow.add_node("fetch_analyst_estimates", self.fetch_analyst_estimates)
        workflow.add_node("fetch_guidance_and_news", self.fetch_guidance_and_news)
        workflow.add_node("aggregate_data", self.aggregate_data)
        workflow.add_node("comprehensive_analysis", self.comprehensive_analysis)
        workflow.add_node("develop_thesis", self.develop_thesis)
        workflow.add_node("generate_report", self.generate_report)

        # Edges
        workflow.set_entry_point("fetch_company_info")

        # Phase 1: Parallel data gathering
        workflow.add_edge("fetch_company_info", "fetch_earnings_history")
        workflow.add_edge("fetch_company_info", "fetch_analyst_estimates")
        workflow.add_edge("fetch_company_info", "fetch_guidance_and_news")

        # Converge to sync point
        workflow.add_edge("fetch_earnings_history", "aggregate_data")
        workflow.add_edge("fetch_analyst_estimates", "aggregate_data")
        workflow.add_edge("fetch_guidance_and_news", "aggregate_data")

        # Phase 2: Sequential analysis → thesis → report
        workflow.add_edge("aggregate_data", "comprehensive_analysis")
        workflow.add_edge("comprehensive_analysis", "develop_thesis")
        workflow.add_edge("develop_thesis", "generate_report")
        workflow.add_edge("generate_report", END)

        return workflow.compile()

    # ========================================================================
    # Node 1: Company Info
    # ========================================================================

    def fetch_company_info(self, state: EarningsAnalysisState) -> EarningsAnalysisState:
        logger.info(f"[1/7] Fetching company info for {state['ticker']}")

        try:
            from data.financial_data import FinancialDataFetcher
            fetcher = FinancialDataFetcher()
            info = fetcher.get_stock_info(state["ticker"])

            if not info:
                state["errors"].append("Failed to fetch company info")
                return state

            state["company_name"] = info.get("company_name", "Unknown")
            state["sector"] = info.get("sector", "Unknown")
            state["industry"] = info.get("industry", "Unknown")
            state["current_price"] = info.get("current_price", 0.0)
            state["market_cap"] = info.get("market_cap", 0.0)

            logger.info(f"  → {state['company_name']} ({state['sector']})")

        except Exception as e:
            logger.error(f"Error in fetch_company_info: {e}")
            state["errors"].append(f"Company info error: {str(e)}")

        return state

    # ========================================================================
    # Nodes 2-4: Parallel Data Gathering
    # ========================================================================

    def fetch_earnings_history(self, state: EarningsAnalysisState) -> EarningsAnalysisState:
        logger.info(f"[2/7] Fetching earnings history for {state['ticker']}")

        try:
            from tools.earnings_tools import GetQuarterlyEarningsTool
            tool = GetQuarterlyEarningsTool()
            state["earnings_history"] = tool._run(
                ticker=state["ticker"],
                quarters=state["quarters_back"],
            )
            logger.info(f"  → Earnings history fetched")
        except Exception as e:
            logger.error(f"Error in fetch_earnings_history: {e}")
            state["errors"].append(f"Earnings history error: {str(e)}")
            state["earnings_history"] = f"Error fetching earnings data: {str(e)}"

        return state

    def fetch_analyst_estimates(self, state: EarningsAnalysisState) -> EarningsAnalysisState:
        logger.info(f"[3/7] Fetching analyst estimates for {state['ticker']}")

        try:
            from tools.earnings_tools import GetAnalystEstimatesTool
            tool = GetAnalystEstimatesTool()
            state["analyst_estimates"] = tool._run(ticker=state["ticker"])
            logger.info(f"  → Analyst estimates fetched")
        except Exception as e:
            logger.error(f"Error in fetch_analyst_estimates: {e}")
            state["errors"].append(f"Analyst estimates error: {str(e)}")
            state["analyst_estimates"] = f"Error fetching analyst estimates: {str(e)}"

        return state

    def fetch_guidance_and_news(self, state: EarningsAnalysisState) -> EarningsAnalysisState:
        logger.info(f"[4/7] Fetching surprises, call insights, and peer data for {state['ticker']}")

        try:
            from tools.earnings_tools import (
                GetEarningsSurprisesTool,
                EarningsCallInsightsTool,
                ComparePeerEarningsTool,
            )

            surprises_tool = GetEarningsSurprisesTool()
            state["earnings_surprises"] = surprises_tool._run(
                ticker=state["ticker"],
                quarters=state["quarters_back"],
            )
            logger.info(f"  → Earnings surprises fetched")

            insights_tool = EarningsCallInsightsTool()
            state["earnings_guidance"] = insights_tool._run(ticker=state["ticker"], quarters=2)
            logger.info(f"  → Earnings call insights fetched")

            peer_tool = ComparePeerEarningsTool()
            state["peer_comparison"] = peer_tool._run(ticker=state["ticker"], peers=None)
            logger.info(f"  → Peer comparison fetched")

        except Exception as e:
            logger.error(f"Error in fetch_guidance_and_news: {e}")
            state["errors"].append(f"Guidance/news error: {str(e)}")
            if not state.get("earnings_surprises"):
                state["earnings_surprises"] = f"Error: {str(e)}"
            if not state.get("earnings_guidance"):
                state["earnings_guidance"] = f"Error: {str(e)}"
            if not state.get("peer_comparison"):
                state["peer_comparison"] = f"Error: {str(e)}"

        return state

    # ========================================================================
    # Node 5: Aggregate (sync point)
    # ========================================================================

    def aggregate_data(self, state: EarningsAnalysisState) -> EarningsAnalysisState:
        logger.info("[5/7] All data gathered, ready for analysis")

        has = {
            "earnings": bool(state.get("earnings_history")),
            "estimates": bool(state.get("analyst_estimates")),
            "surprises": bool(state.get("earnings_surprises")),
            "guidance": bool(state.get("earnings_guidance")),
            "peers": bool(state.get("peer_comparison")),
            "accountability": bool(state.get("management_accountability")),
        }
        logger.info(f"  → Data: {has}")

        return state

    # ========================================================================
    # Node 6: Comprehensive Analysis (1 LLM call — replaces 4 separate calls)
    # ========================================================================

    def comprehensive_analysis(self, state: EarningsAnalysisState) -> EarningsAnalysisState:
        logger.info(f"[6/7] Running comprehensive analysis for {state['ticker']}")

        try:
            prompt = f"""You are a senior equity research analyst. Analyze all available data for {state['company_name']} ({state['ticker']}) and produce a structured analysis.

CURRENT METRICS:
- Price: ${state['current_price']:.2f} | Market Cap: ${state['market_cap']/1e9:.2f}B
- Sector: {state['sector']} | Industry: {state['industry']}

QUARTERLY EARNINGS DATA:
{state['earnings_history']}

EARNINGS SURPRISES:
{state['earnings_surprises']}

MANAGEMENT GUIDANCE & EARNINGS CALL INSIGHTS:
{state['earnings_guidance']}

ANALYST CONSENSUS ESTIMATES:
{state['analyst_estimates']}

PEER COMPARISON:
{state['peer_comparison']}

Write a comprehensive analysis with these sections:

## EARNINGS TREND
- Revenue growth trajectory (accelerating/stable/decelerating) with specific QoQ and YoY numbers
- EPS trends and margin expansion/contraction
- Beat/miss consistency and any inflection points

## EARNINGS QUALITY
- Cash flow vs reported earnings
- Earnings predictability, one-time items
- Quality rating: HIGH, MEDIUM, or LOW

## GUIDANCE & FORWARD OUTLOOK
- Management guidance vs consensus estimates (above/below/in-line)
- Guidance changes (raised/lowered/maintained)
- Management tone and key growth drivers or headwinds

## COMPETITIVE POSITIONING
- Relative performance vs peers (revenue/EPS growth, margins)
- Market share trends
- Position rating: STRONG, MODERATE, or WEAK

## VALUATION
- Forward P/E and PEG ratio
- Premium/discount vs history and peers
- Fair value range with justification

## MANAGEMENT ACCOUNTABILITY

### Promises vs Outcomes
- What specific commitments did management make in PREVIOUS quarters? (revenue targets, margin goals, product launches, strategic initiatives)
- Which promises were DELIVERED and which were MISSED?
- Grade management on follow-through: STRONG, MIXED, or POOR

### Forecasting Accuracy
- Compare management's prior guidance ranges to actual reported results
- Are they conservative (consistently beat own guidance), accurate, or optimistic (frequently miss)?
- Guidance accuracy pattern: CONSERVATIVE, ACCURATE, or OPTIMISTIC

### Red Flags
- Hedging language or vague deflections on direct questions
- Lowered or withdrawn guidance without clear justification
- Blaming external factors for misses while taking credit for beats
- Unusual changes in accounting, metrics, or KPI definitions
- Executive departures, especially CFO
- Growing gap between GAAP and non-GAAP earnings
- Declining cash flow while reporting earnings growth

List each red flag found, or state "No significant red flags identified" if clean.

Be specific with numbers. Cite data from the inputs. No filler."""

            messages = [
                SystemMessage(content="You are a senior equity research analyst. Be concise, specific, and data-driven."),
                HumanMessage(content=prompt),
            ]

            response = self.llm.invoke(messages)
            state["comprehensive_analysis"] = response.content

            # Extract management accountability section for the report
            content = response.content
            acc_start = content.find("## MANAGEMENT ACCOUNTABILITY")
            if acc_start == -1:
                acc_start = content.find("MANAGEMENT ACCOUNTABILITY")
            if acc_start != -1:
                next_section = content.find("\n## ", acc_start + 5)
                state["management_accountability"] = content[acc_start:next_section].strip() if next_section != -1 else content[acc_start:].strip()

            logger.info(f"  → Comprehensive analysis complete")

        except Exception as e:
            logger.error(f"Error in comprehensive_analysis: {e}")
            state["errors"].append(f"Analysis error: {str(e)}")
            state["comprehensive_analysis"] = "Error running comprehensive analysis"

        return state

    # ========================================================================
    # Node 7: Investment Thesis + Rating (1 LLM call — replaces 2 separate calls)
    # ========================================================================

    def develop_thesis(self, state: EarningsAnalysisState) -> EarningsAnalysisState:
        logger.info(f"[7/7] Developing investment thesis for {state['ticker']}")

        try:
            prompt = f"""Based on this analysis of {state['company_name']} ({state['ticker']}), provide an investment recommendation.

CURRENT PRICE: ${state['current_price']:.2f}

ANALYSIS:
{state['comprehensive_analysis']}

Provide exactly:

1. **INVESTMENT RATING**: BUY, HOLD, or SELL
   - BUY: expected upside >15% with favorable risk/reward
   - HOLD: expected return 0-15% or mixed signals
   - SELL: downside risk >10% or deteriorating fundamentals

2. **PRICE TARGET (12-month)**: A specific dollar amount (format: "$XXX.XX")

3. **INVESTMENT THESIS** (2-3 paragraphs): Why this rating, key drivers, risk/reward

4. **KEY CATALYSTS** (3-5 bullet points): Near-term positive events

5. **KEY RISKS** (3-5 bullet points): What could go wrong

Be decisive and quantitative. Don't hedge."""

            messages = [
                SystemMessage(content="You are a senior equity research analyst making actionable investment recommendations."),
                HumanMessage(content=prompt),
            ]

            response = self.llm.invoke(messages)
            thesis_text = response.content

            state["investment_thesis"] = thesis_text

            # --- Extract structured fields from LLM output ---

            # Rating
            state["rating"] = "HOLD"  # default
            for line in thesis_text.split('\n'):
                line_upper = line.upper()
                if 'RATING' in line_upper or 'RECOMMENDATION' in line_upper:
                    if 'BUY' in line_upper and 'SELL' not in line_upper:
                        state["rating"] = 'BUY'
                        break
                    elif 'SELL' in line_upper:
                        state["rating"] = 'SELL'
                        break
                    elif 'HOLD' in line_upper:
                        state["rating"] = 'HOLD'
                        break

            # Price target
            price_pattern = r'\$(\d+(?:\.\d{2})?)'
            for line in thesis_text.split('\n'):
                if 'TARGET' in line.upper() or 'PRICE TARGET' in line.upper():
                    prices_in_line = re.findall(price_pattern, line)
                    if prices_in_line:
                        state["price_target"] = float(prices_in_line[0])
                        break
            else:
                # Fallback: first reasonable price in the text
                for p in re.findall(price_pattern, thesis_text):
                    p_float = float(p)
                    if state['current_price'] > 0 and 0.5 * state['current_price'] < p_float < 3.0 * state['current_price']:
                        state["price_target"] = p_float
                        break

            # Catalysts
            catalysts = []
            in_section = False
            for line in thesis_text.split('\n'):
                stripped = line.strip()
                if 'CATALYST' in stripped.upper():
                    in_section = True
                    continue
                if in_section:
                    if stripped and (stripped[0] in '-•' or (stripped[0].isdigit() and '.' in stripped[:3])):
                        text = stripped.lstrip('-•0123456789. ').strip()
                        if text and len(text) > 10:
                            catalysts.append(text)
                    elif 'RISK' in stripped.upper() or 'BEAR' in stripped.upper():
                        break
            state["key_catalysts"] = catalysts[:5] if catalysts else ["Next earnings report", "Industry trends", "Market conditions"]

            # Risks
            risks = []
            in_section = False
            for line in thesis_text.split('\n'):
                stripped = line.strip()
                if 'KEY RISK' in stripped.upper() or (stripped.upper().startswith('**KEY RISK') or stripped.upper().startswith('## KEY RISK')):
                    in_section = True
                    continue
                if in_section:
                    if stripped and (stripped[0] in '-•' or (stripped[0].isdigit() and '.' in stripped[:3])):
                        text = stripped.lstrip('-•0123456789. ').strip()
                        if text and len(text) > 10:
                            risks.append(text)
                    elif len(risks) >= 3 and (not stripped or stripped.startswith('#')):
                        break
            state["key_risks"] = risks[:5] if risks else ["Market volatility", "Execution risk", "Competitive pressure"]

            logger.info(f"  → {state['rating']} | PT ${state['price_target']:.2f} | {len(state['key_catalysts'])} catalysts, {len(state['key_risks'])} risks")

        except Exception as e:
            logger.error(f"Error in develop_thesis: {e}")
            state["errors"].append(f"Thesis error: {str(e)}")
            state["investment_thesis"] = "Error developing investment thesis"
            state["rating"] = "HOLD"
            state["price_target"] = state['current_price']
            state["key_catalysts"] = ["Unable to determine catalysts"]
            state["key_risks"] = ["Unable to determine risks"]

        return state

    # ========================================================================
    # Node 8: Generate Report
    # ========================================================================

    def generate_report(self, state: EarningsAnalysisState) -> EarningsAnalysisState:
        logger.info(f"Generating final report for {state['ticker']}")

        try:
            upside_pct = ((state['price_target'] - state['current_price']) / state['current_price'] * 100) if state['current_price'] > 0 else 0
            execution_time = time.time() - state['start_time']
            minutes = int(execution_time // 60)
            seconds = int(execution_time % 60)

            report = f"""
{'='*80}
EARNINGS-FOCUSED EQUITY RESEARCH REPORT
{'='*80}

COMPANY: {state['company_name']} ({state['ticker']})
SECTOR: {state['sector']} | INDUSTRY: {state['industry']}
CURRENT PRICE: ${state['current_price']:.2f} | MARKET CAP: ${state['market_cap']/1e9:.2f}B

PRICE TARGET (12M): ${state['price_target']:.2f}
IMPLIED RETURN: {upside_pct:+.1f}%

Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}
Analysis Time: {minutes}m {seconds}s

{'='*80}
EXECUTIVE SUMMARY
{'='*80}

{state['investment_thesis']}

{'='*80}
COMPREHENSIVE ANALYSIS
{'='*80}

{state['comprehensive_analysis']}

{'='*80}
MANAGEMENT ACCOUNTABILITY
{'='*80}

{state.get('management_accountability', 'No accountability data available.')}

{'='*80}
QUARTERLY EARNINGS DATA
{'='*80}

{state['earnings_history']}

EARNINGS SURPRISES:
{state['earnings_surprises']}

{'='*80}
MANAGEMENT GUIDANCE & EARNINGS CALL INSIGHTS
{'='*80}

{state['earnings_guidance']}

ANALYST ESTIMATES:
{state['analyst_estimates']}

{'='*80}
PEER COMPARISON
{'='*80}

{state['peer_comparison']}

{'='*80}
KEY CATALYSTS
{'='*80}

"""
            for i, catalyst in enumerate(state['key_catalysts'], 1):
                report += f"{i}. {catalyst}\n"

            report += f"""
{'='*80}
KEY RISKS
{'='*80}

"""
            for i, risk in enumerate(state['key_risks'], 1):
                report += f"{i}. {risk}\n"

            report += f"""
{'='*80}
BOTTOM LINE
{'='*80}

PRICE TARGET: ${state['price_target']:.2f} (Current: ${state['current_price']:.2f}, Upside: {upside_pct:+.1f}%)

"""

            if state['errors']:
                report += f"""
{'='*80}
ANALYSIS NOTES
{'='*80}

The following non-critical issues were encountered during analysis:
"""
                for error in state['errors']:
                    report += f"- {error}\n"

            report += f"""
{'='*80}
Generated by AI Earnings Analyst | Powered by LangGraph
Analysis completed in {minutes}m {seconds}s
{'='*80}
"""

            state["final_report"] = report
            logger.info(f"  → Report generated ({len(report)} chars)")

        except Exception as e:
            logger.error(f"Error in generate_report: {e}")
            state["errors"].append(f"Report generation error: {str(e)}")
            state["final_report"] = f"ERROR GENERATING REPORT for {state['ticker']}: {str(e)}"

        return state

    # ========================================================================
    # Direct CLI method
    # ========================================================================

    def analyze(self, ticker: str, quarters_back: int = 8) -> str:
        initial_state = {
            "ticker": ticker,
            "quarters_back": quarters_back,
            "company_name": "",
            "sector": "",
            "industry": "",
            "current_price": 0.0,
            "market_cap": 0.0,
            "earnings_history": "",
            "analyst_estimates": "",
            "earnings_surprises": "",
            "earnings_guidance": "",
            "peer_comparison": "",
            "comprehensive_analysis": "",
            "management_accountability": "",
            "investment_thesis": "",
            "rating": "",
            "price_target": 0.0,
            "key_catalysts": [],
            "key_risks": [],
            "final_report": "",
            "start_time": time.time(),
            "errors": [],
        }

        result = self.graph.invoke(initial_state)
        return result.get("final_report", "Error: No report generated")


# ============================================================================
# Factory Function
# ============================================================================

def create_earnings_agent(model: str = "claude-sonnet-4-5-20250929") -> EarningsAgent:
    """Factory function to create an earnings agent."""
    return EarningsAgent(model=model)
