"""
Earnings-Focused Equity Research Agent using LangGraph

Generates equity research reports focusing on:
- Latest earnings reports & historical trends
- Analyst estimates & earnings surprises
- Management guidance analysis
- Competitive comparison
- Investment thesis

11-node workflow: 6 parallel data nodes → aggregate → analysis (1 LLM call) → thesis (1 LLM call) → report
"""
from typing import TypedDict, List, Optional, Annotated
import operator
from langgraph.graph import StateGraph, END
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
import time
import logging
import re
import json as _json
import threading
from shared.ticker_utils import extract_ticker as _extract_ticker_shared

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

    # Raw Data (Nodes 2-5, parallel)
    earnings_history: Annotated[str, keep_first]
    analyst_estimates: Annotated[str, keep_first]
    earnings_surprises: Annotated[str, keep_first]
    earnings_guidance: Annotated[str, keep_first]
    peer_comparison: Annotated[str, keep_first]
    sec_filings_summary: Annotated[str, keep_first]

    # Analysis (Node 6 — single LLM call)
    comprehensive_analysis: Annotated[str, keep_first]

    # Thesis (Node 7 — single LLM call)
    investment_thesis: Annotated[str, keep_first]
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
        self._state_lock = threading.Lock()
        self.last_state = None
        self.last_state_time: float = 0.0

    def invoke(self, input_dict: dict, config: Optional[dict] = None) -> dict:
        try:
            query = input_dict.get("input", "")
            is_followup = input_dict.get("followup", False)

            ticker = self._extract_ticker(query)

            # Follow-up mode: serve from cached state if the ticker matches and cache is fresh.
            # Ticker check prevents cross-ticker answers (e.g. user switches from AAPL to MSFT).
            if is_followup:
                with self._state_lock:
                    cached_state = None
                    if self.last_state is not None:
                        cache_age_ok = time.time() - self.last_state_time <= 1800
                        cached_ticker = self.last_state.get("ticker", "")
                        ticker_matches = (not ticker) or (ticker == cached_ticker)
                        if cache_age_ok and ticker_matches:
                            cached_state = dict(self.last_state)
                if cached_state:
                    return self._answer_followup(query, cached_state, config)

            if not ticker:
                return {"output": "Error: Please provide a stock ticker symbol (e.g., AAPL, MSFT, NVDA)"}

            logger.info(f"Starting earnings analysis for {ticker}")

            result = self.graph.invoke(
                self.agent_owner._build_initial_state(ticker),
                config=config,
            )

            # Cache state for follow-ups (thread-safe)
            with self._state_lock:
                self.last_state = result
                self.last_state_time = time.time()

            execution_time = time.time() - result["start_time"]
            logger.info(f"Earnings analysis completed in {execution_time:.1f} seconds")

            final_output = result.get("final_report", "Error: No report generated")
            final_output += f"\n\n---\n*Analysis completed in {execution_time/60:.1f} minutes*"

            return {"output": final_output}

        except Exception as e:
            logger.error(f"Error in earnings agent: {e}")
            return {"output": f"Error analyzing earnings: {str(e)}"}

    def _answer_followup(self, question: str, state: dict, config: Optional[dict] = None) -> dict:
        """Answer follow-up using cached analysis state. Single LLM call."""
        logger.info(f"Answering follow-up for {state['ticker']}: {question[:80]}...")

        try:
            prompt = f"""You are a senior equity research analyst. You just completed a comprehensive
earnings analysis for {state['company_name']} ({state['ticker']}).

ANALYSIS CONTEXT:
{self.agent_owner._clean_field(state['comprehensive_analysis'], 'analysis', limit=3000)}

EARNINGS DATA:
{self.agent_owner._clean_field(state['earnings_history'], 'earnings data', limit=3000)}

MANAGEMENT GUIDANCE:
{self.agent_owner._clean_field(state['earnings_guidance'], 'guidance', limit=3000)}

INVESTMENT THESIS:
{self.agent_owner._clean_field(state['investment_thesis'], 'thesis', limit=3000)}

The investor now asks: {question}

Provide a focused, data-driven answer. Reference specific numbers from the analysis.
Be concise (2-4 paragraphs). If the question requires data you don't have, say so."""

            response = self.agent_owner.llm.invoke(
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
        """Delegate to shared.ticker_utils.extract_ticker."""
        return _extract_ticker_shared(query)


# ============================================================================
# Earnings Agent
# ============================================================================

class EarningsAgent:
    """
    LangGraph-based earnings research agent.

    11-node workflow:
    1. Fetch company info
    2-7. Parallel: earnings history, analyst estimates, earnings surprises,
         call insights, peer comparison, SEC filings
    8. Aggregate (sync point)
    9a. Comprehensive analysis (1 LLM call)
    9b. Investment thesis (1 LLM call)
    9c. Generate report
    """

    _CHART_RE = re.compile(
        r'---CHART_DATA:([^-\n]+)---\n(.*?)\n---END_CHART_DATA:[^-\n]+---',
        re.DOTALL,
    )
    _ERROR_PREFIXES = ("error fetching", "error analyzing", "error:", "error in ")

    def __init__(self, model: str = "claude-sonnet-4-5-20250929"):
        self.model = model
        self.llm = ChatAnthropic(
            model=model,
            temperature=0,
            max_retries=3,
            default_request_timeout=180.0,
            max_tokens=8192,
            streaming=True,
        )

        # Progress streaming (injected by api_server before graph invocation)
        self._progress_queue = None
        self._progress_loop = None

        self.graph = self._build_graph()
        self.agent_executor = EarningsAgentExecutorAdapter(self.graph, agent_owner=self)

        logger.info(f"Earnings Agent initialized with model: {model}")

    def _emit_progress(self, node: str, status: str, detail: str = ""):
        """Push a progress event to the SSE queue (no-op if no queue injected).

        Reads both queue and loop atomically under the GIL to avoid a race
        where the API server clears one attribute between the two reads.
        """
        queue, loop = self._progress_queue, self._progress_loop
        if queue is not None and loop is not None:
            event = {"type": "earnings_progress", "node": node, "status": status, "detail": detail}
            loop.call_soon_threadsafe(queue.put_nowait, event)

    def _emit_chart_data(self, tool_output: str):
        """Extract ---CHART_DATA--- blocks from tool output and emit as chart_data SSE events.

        The earnings agent calls tools directly (no LangChain callback chain), so
        chart_data events must be extracted and emitted here rather than relying on
        StreamingCallbackHandler.on_tool_end.
        """
        queue, loop = self._progress_queue, self._progress_loop
        if queue is None or loop is None or not isinstance(tool_output, str):
            return

        for match in self._CHART_RE.finditer(tool_output):
            try:
                chart_event = _json.loads(match.group(2).strip())
                chart_event["type"] = "chart_data"
                loop.call_soon_threadsafe(queue.put_nowait, chart_event)
            except Exception as e:
                logger.warning(f"chart_data parse error in earnings agent: {e}")

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(EarningsAnalysisState)

        # Nodes
        workflow.add_node("fetch_company_info", self.fetch_company_info)
        workflow.add_node("fetch_earnings_history", self.fetch_earnings_history)
        workflow.add_node("fetch_analyst_estimates", self.fetch_analyst_estimates)
        workflow.add_node("fetch_earnings_surprises", self.fetch_earnings_surprises)
        workflow.add_node("fetch_call_insights", self.fetch_call_insights)
        workflow.add_node("fetch_peer_comparison", self.fetch_peer_comparison)
        workflow.add_node("fetch_sec_filings", self.fetch_sec_filings)
        workflow.add_node("aggregate_data", self.aggregate_data)
        workflow.add_node("comprehensive_analysis", self.comprehensive_analysis)
        workflow.add_node("develop_thesis", self.develop_thesis)
        workflow.add_node("generate_report", self.generate_report)

        # Edges
        workflow.set_entry_point("fetch_company_info")

        # Phase 1: Parallel data gathering (6 nodes in parallel)
        workflow.add_edge("fetch_company_info", "fetch_earnings_history")
        workflow.add_edge("fetch_company_info", "fetch_analyst_estimates")
        workflow.add_edge("fetch_company_info", "fetch_earnings_surprises")
        workflow.add_edge("fetch_company_info", "fetch_call_insights")
        workflow.add_edge("fetch_company_info", "fetch_peer_comparison")
        workflow.add_edge("fetch_company_info", "fetch_sec_filings")

        # Converge to sync point
        workflow.add_edge("fetch_earnings_history", "aggregate_data")
        workflow.add_edge("fetch_analyst_estimates", "aggregate_data")
        workflow.add_edge("fetch_earnings_surprises", "aggregate_data")
        workflow.add_edge("fetch_call_insights", "aggregate_data")
        workflow.add_edge("fetch_peer_comparison", "aggregate_data")
        workflow.add_edge("fetch_sec_filings", "aggregate_data")

        # Phase 2: Sequential analysis → thesis → report
        # Route from aggregate: skip LLM nodes entirely if critical data is missing
        workflow.add_conditional_edges(
            "aggregate_data",
            self._route_after_aggregate,
            {"analyze": "comprehensive_analysis", "error": "generate_report"},
        )
        workflow.add_edge("comprehensive_analysis", "develop_thesis")
        workflow.add_edge("develop_thesis", "generate_report")
        workflow.add_edge("generate_report", END)

        return workflow.compile()

    # ========================================================================
    # Node 1: Company Info
    # ========================================================================

    def fetch_company_info(self, state: EarningsAnalysisState) -> dict:
        logger.info(f"[1/11] Fetching company info for {state['ticker']}")
        self._emit_progress("fetch_company_info", "started", "Looking up company info")

        try:
            from data.financial_data import FinancialDataFetcher
            fetcher = FinancialDataFetcher()
            info = fetcher.get_stock_info(state["ticker"])

            if not info:
                self._emit_progress("fetch_company_info", "completed", "Partial data (error)")
                return {"errors": ["Failed to fetch company info"]}

            result = {
                "company_name": info.get("company_name", "Unknown"),
                "sector": info.get("sector", "Unknown"),
                "industry": info.get("industry", "Unknown"),
                "current_price": info.get("current_price", 0.0),
                "market_cap": info.get("market_cap", 0.0),
            }

            logger.info(f"  → {result['company_name']} ({result['sector']})")
            self._emit_progress("fetch_company_info", "completed", f"{result['company_name']} ({result['sector']})")
            return result

        except Exception as e:
            logger.error(f"Error in fetch_company_info: {e}")
            self._emit_progress("fetch_company_info", "completed", "Partial data (error)")
            return {"errors": [f"Company info error: {str(e)}"]}

    # ========================================================================
    # Nodes 2-4: Parallel Data Gathering
    # ========================================================================

    def fetch_earnings_history(self, state: EarningsAnalysisState) -> dict:
        logger.info(f"[2/11] Fetching earnings history for {state['ticker']}")
        self._emit_progress("fetch_earnings_history", "started", "Fetching quarterly earnings")

        try:
            from tools.earnings_tools import GetQuarterlyEarningsTool
            tool = GetQuarterlyEarningsTool()
            earnings_history = tool._run(
                ticker=state["ticker"],
                quarters=state["quarters_back"],
            )
            self._emit_chart_data(earnings_history)
            logger.info(f"  → Earnings history fetched")
            self._emit_progress("fetch_earnings_history", "completed", "Earnings history loaded")
            return {"earnings_history": earnings_history}
        except Exception as e:
            logger.error(f"Error in fetch_earnings_history: {e}")
            self._emit_progress("fetch_earnings_history", "completed", "Partial data (error)")
            return {
                "earnings_history": f"Error fetching earnings data: {str(e)}",
                "errors": [f"Earnings history error: {str(e)}"],
            }

    def fetch_analyst_estimates(self, state: EarningsAnalysisState) -> dict:
        logger.info(f"[3/11] Fetching analyst estimates for {state['ticker']}")
        self._emit_progress("fetch_analyst_estimates", "started", "Getting analyst consensus")

        try:
            from tools.earnings_tools import GetAnalystEstimatesTool
            tool = GetAnalystEstimatesTool()
            analyst_estimates = tool._run(ticker=state["ticker"])
            self._emit_chart_data(analyst_estimates)
            logger.info(f"  → Analyst estimates fetched")
            self._emit_progress("fetch_analyst_estimates", "completed", "Analyst estimates loaded")
            return {"analyst_estimates": analyst_estimates}
        except Exception as e:
            logger.error(f"Error in fetch_analyst_estimates: {e}")
            self._emit_progress("fetch_analyst_estimates", "completed", "Partial data (error)")
            return {
                "analyst_estimates": f"Error fetching analyst estimates: {str(e)}",
                "errors": [f"Analyst estimates error: {str(e)}"],
            }

    def fetch_earnings_surprises(self, state: EarningsAnalysisState) -> dict:
        logger.info(f"[4/11] Fetching earnings surprises for {state['ticker']}")
        self._emit_progress("fetch_earnings_surprises", "started", "Fetching earnings surprises")

        try:
            from tools.earnings_tools import GetEarningsSurprisesTool
            tool = GetEarningsSurprisesTool()
            surprises = tool._run(ticker=state["ticker"], quarters=state["quarters_back"])
            self._emit_chart_data(surprises)
            logger.info(f"  → Earnings surprises fetched")
            self._emit_progress("fetch_earnings_surprises", "completed", "Surprises loaded")
            return {"earnings_surprises": surprises}
        except Exception as e:
            logger.error(f"Error in fetch_earnings_surprises: {e}")
            self._emit_progress("fetch_earnings_surprises", "completed", "Partial data (error)")
            return {
                "earnings_surprises": f"Error fetching earnings surprises: {str(e)}",
                "errors": [f"Earnings surprises error: {str(e)}"],
            }

    def fetch_call_insights(self, state: EarningsAnalysisState) -> dict:
        logger.info(f"[5/11] Fetching earnings call insights for {state['ticker']}")
        self._emit_progress("fetch_call_insights", "started", "Reading earnings call transcripts")

        try:
            from tools.earnings_tools import EarningsCallInsightsTool
            tool = EarningsCallInsightsTool(model=self.model)
            guidance = tool._run(ticker=state["ticker"], quarters=min(state["quarters_back"], 4))
            logger.info(f"  → Earnings call insights fetched")
            self._emit_progress("fetch_call_insights", "completed", "Call insights loaded")
            return {"earnings_guidance": guidance}
        except Exception as e:
            logger.error(f"Error in fetch_call_insights: {e}")
            self._emit_progress("fetch_call_insights", "completed", "Partial data (error)")
            return {
                "earnings_guidance": f"Error fetching earnings call insights: {str(e)}",
                "errors": [f"Call insights error: {str(e)}"],
            }

    def fetch_peer_comparison(self, state: EarningsAnalysisState) -> dict:
        logger.info(f"[6/11] Fetching peer comparison for {state['ticker']}")
        self._emit_progress("fetch_peer_comparison", "started", "Comparing peer earnings")

        try:
            from tools.earnings_tools import ComparePeerEarningsTool
            tool = ComparePeerEarningsTool()
            peers = tool._run(ticker=state["ticker"], peers=None)
            logger.info(f"  → Peer comparison fetched")
            self._emit_progress("fetch_peer_comparison", "completed", "Peer comparison loaded")
            return {"peer_comparison": peers}
        except Exception as e:
            logger.error(f"Error in fetch_peer_comparison: {e}")
            self._emit_progress("fetch_peer_comparison", "completed", "Partial data (error)")
            return {
                "peer_comparison": f"Error fetching peer comparison: {str(e)}",
                "errors": [f"Peer comparison error: {str(e)}"],
            }

    # ========================================================================
    # Node 7: SEC Filings (parallel with Nodes 2-6)
    # ========================================================================

    def fetch_sec_filings(self, state: EarningsAnalysisState) -> dict:
        logger.info(f"[7/11] Fetching SEC filings for {state['ticker']}")
        self._emit_progress("fetch_sec_filings", "started", "Reading SEC EDGAR filings")

        try:
            from tools.sec_tools import AnalyzeSECFilingTool

            # Fetch the most recent 10-Q (quarterly report) for management commentary
            self._emit_progress("fetch_sec_filings", "sub_progress", "Analyzing latest 10-Q filing")
            analyze_tool = AnalyzeSECFilingTool()
            sec_summary = analyze_tool._run(
                ticker=state["ticker"],
                filing_type="10-Q",
                sections="all",
            )

            # If 10-Q not available, fall back to 10-K
            if sec_summary.startswith("No 10-Q filing") or sec_summary.startswith("Error"):
                self._emit_progress("fetch_sec_filings", "sub_progress", "10-Q unavailable, trying 10-K")
                sec_summary = analyze_tool._run(
                    ticker=state["ticker"],
                    filing_type="10-K",
                    sections="all",
                )

            logger.info(f"  → SEC filing summary fetched ({len(sec_summary)} chars)")
            self._emit_progress("fetch_sec_filings", "completed", "SEC filing analysis complete")
            return {"sec_filings_summary": sec_summary}

        except Exception as e:
            logger.error(f"Error in fetch_sec_filings: {e}")
            self._emit_progress("fetch_sec_filings", "completed", "SEC data unavailable")
            return {
                "sec_filings_summary": f"SEC filing data unavailable: {str(e)}",
                "errors": [f"SEC filings error: {str(e)}"],
            }

    # ========================================================================
    # Node 8: Aggregate (sync point)
    # ========================================================================

    def _route_after_aggregate(self, state: EarningsAnalysisState) -> str:
        """Route to analysis if critical data is available, otherwise skip to report."""
        has_company = state.get("company_name", "") not in ("", "Unknown")
        has_price = state.get("current_price", 0) > 0
        # At least one of the primary data fields must have real content.
        # This catches the case where company info succeeded but all 6 parallel
        # data nodes failed — running the LLM on empty data produces a garbage report.
        parallel_fields = (
            state.get("earnings_history", ""),
            state.get("analyst_estimates", ""),
            state.get("earnings_surprises", ""),
            state.get("earnings_guidance", ""),
            state.get("peer_comparison", ""),
            state.get("sec_filings_summary", ""),
        )
        has_any_data = any(
            f and not f.lower().startswith(EarningsAgent._ERROR_PREFIXES)
            for f in parallel_fields
        )
        if not has_company or not has_price or not has_any_data:
            logger.warning(
                f"Critical data missing for {state['ticker']} "
                f"(company_name={state.get('company_name')!r}, "
                f"current_price={state.get('current_price')}, "
                f"has_any_data={has_any_data}). "
                "Skipping LLM analysis nodes."
            )
            return "error"
        return "analyze"

    def aggregate_data(self, state: EarningsAnalysisState) -> dict:
        logger.info("[8/11] All data gathered, ready for analysis")
        logger.info(
            "  → Data availability: earnings=%s estimates=%s surprises=%s "
            "guidance=%s peers=%s sec=%s",
            bool(state.get("earnings_history")),
            bool(state.get("analyst_estimates")),
            bool(state.get("earnings_surprises")),
            bool(state.get("earnings_guidance")),
            bool(state.get("peer_comparison")),
            bool(state.get("sec_filings_summary")),
        )
        return {}

    # ========================================================================
    # Node 9a: Comprehensive Analysis (1 LLM call)
    # ========================================================================

    def comprehensive_analysis(self, state: EarningsAnalysisState) -> dict:
        logger.info(f"[9/11] Running comprehensive analysis for {state['ticker']}")
        self._emit_progress("comprehensive_analysis", "started", "Running financial analysis")

        try:
            prompt = f"""You are a senior equity research analyst. Analyze all available data for {state['company_name']} ({state['ticker']}) and produce a structured analysis.

CURRENT METRICS:
- Price: ${state['current_price']:.2f} | Market Cap: ${state['market_cap']/1e9:.2f}B
- Sector: {state['sector']} | Industry: {state['industry']}

QUARTERLY EARNINGS DATA:
{self._clean_field(state['earnings_history'], 'Quarterly earnings')}

EARNINGS SURPRISES:
{self._clean_field(state['earnings_surprises'], 'Earnings surprises')}

MANAGEMENT GUIDANCE & EARNINGS CALL INSIGHTS:
{self._clean_field(state['earnings_guidance'], 'Earnings call insights')}

ANALYST CONSENSUS ESTIMATES:
{self._clean_field(state['analyst_estimates'], 'Analyst estimates')}

PEER COMPARISON:
{self._clean_field(state['peer_comparison'], 'Peer comparison')}

SEC FILING ANALYSIS (10-Q/10-K — Primary Source):
{self._clean_field(state.get('sec_filings_summary', ''), 'SEC filing')}

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

Be specific with numbers. Cite data from the inputs. No filler.

CHART PLACEHOLDERS — include these on their own line where relevant:
- Where you discuss quarterly revenue/EPS trends: {{CHART:quarterly_earnings_{state['ticker']}}}
- Where you discuss earnings surprises (beats/misses): {{CHART:earnings_surprises_{state['ticker']}}}
- Where you discuss analyst consensus estimates: {{CHART:analyst_estimates_{state['ticker']}}}
Do NOT reproduce any ---CHART_DATA--- blocks."""

            messages = [
                SystemMessage(content="You are a senior equity research analyst. Be concise, specific, and data-driven."),
                HumanMessage(content=prompt),
            ]

            response = self.llm.invoke(messages)
            result = {"comprehensive_analysis": response.content}

            logger.info(f"  → Comprehensive analysis complete")
            self._emit_progress("comprehensive_analysis", "completed", "Analysis complete")
            return result

        except Exception as e:
            logger.error(f"Error in comprehensive_analysis: {e}")
            self._emit_progress("comprehensive_analysis", "completed", "Partial data (error)")
            return {
                "comprehensive_analysis": "Error running comprehensive analysis",
                "errors": [f"Analysis error: {str(e)}"],
            }

    # ========================================================================
    # Node 9b: Investment Thesis + Rating (1 LLM call — replaces 2 separate calls)
    # ========================================================================

    def develop_thesis(self, state: EarningsAnalysisState) -> dict:
        logger.info(f"[10/11] Developing investment thesis for {state['ticker']}")
        self._emit_progress("develop_thesis", "started", "Developing investment thesis")

        try:
            prompt = f"""Based on this analysis of {state['company_name']} ({state['ticker']}), provide an investment recommendation.

CURRENT PRICE: ${state['current_price']:.2f}

ANALYSIS:
{state['comprehensive_analysis']}

Respond with two parts:

**Part 1 — Prose thesis** (2-3 paragraphs, no headers): Key drivers, risk/reward, and implied return. Be decisive and quantitative. Every claim must include a specific number. No emoji. No ASCII borders.

**Part 2 — Structured JSON** (on its own line, after the prose):
```json
{{
  "price_target": <number, 12-month per-share target>,
  "key_catalysts": ["<catalyst 1>", "<catalyst 2>", "<catalyst 3>"],
  "key_risks": ["<risk 1>", "<risk 2>", "<risk 3>"]
}}
```

3-5 items each for catalysts and risks. Be specific — no generic placeholders."""

            messages = [
                SystemMessage(content="You are a senior equity research analyst making actionable investment recommendations."),
                HumanMessage(content=prompt),
            ]

            response = self.llm.invoke(messages)
            thesis_text = response.content

            # Parse the JSON block — everything else is the prose thesis
            result = {"investment_thesis": thesis_text, "price_target": 0.0, "key_catalysts": [], "key_risks": []}

            json_match = re.search(r'```json\s*(\{.*?\})\s*```', thesis_text, re.DOTALL)
            if json_match:
                try:
                    structured = _json.loads(json_match.group(1))
                    result["price_target"] = float(structured.get("price_target", 0) or 0)
                    result["key_catalysts"] = structured.get("key_catalysts", [])[:5]
                    result["key_risks"] = structured.get("key_risks", [])[:5]
                    # Strip the JSON block from the prose shown to users
                    result["investment_thesis"] = thesis_text[:json_match.start()].strip()
                except (_json.JSONDecodeError, ValueError, TypeError):
                    logger.warning("develop_thesis: JSON parse failed, leaving structured fields empty")
                    result["errors"] = ["Structured thesis data (price target, catalysts, risks) could not be parsed from LLM response"]

            logger.info(f"  → PT ${result['price_target']:.2f} | {len(result['key_catalysts'])} catalysts, {len(result['key_risks'])} risks")
            self._emit_progress("develop_thesis", "completed", "Thesis complete")
            return result

        except Exception as e:
            logger.error(f"Error in develop_thesis: {e}")
            self._emit_progress("develop_thesis", "completed", "Partial data (error)")
            return {
                "investment_thesis": "Error developing investment thesis",
                "price_target": state['current_price'] if state['current_price'] > 0 else 0.0,
                "key_catalysts": ["Unable to determine catalysts"],
                "key_risks": ["Unable to determine risks"],
                "errors": [f"Thesis error: {str(e)}"],
            }

    # ========================================================================
    # Node 8: Generate Report
    # ========================================================================

    def generate_report(self, state: EarningsAnalysisState) -> dict:
        logger.info(f"Generating final report for {state['ticker']}")
        self._emit_progress("generate_report", "started", "Writing report")

        try:
            upside_pct = ((state['price_target'] - state['current_price']) / state['current_price'] * 100) if state['current_price'] > 0 else 0
            execution_time = time.time() - state['start_time']
            minutes = int(execution_time // 60)
            seconds = int(execution_time % 60)

            errors_md = ""
            if state.get('errors'):
                errors_md = "\n## Analysis Notes\n\n" + "\n".join(f"- {e}" for e in state['errors']) + "\n"

            display_name = state['company_name'] or state['ticker']
            report = f"""# {display_name} ({state['ticker']}) — Earnings Research Report

**{state['sector']}** | {state['industry']} | {time.strftime('%B %d, %Y')}

**Price Target (12M):** ${state['price_target']:.2f} &nbsp;|&nbsp; **Current Price:** ${state['current_price']:.2f} &nbsp;|&nbsp; **Implied Return:** {upside_pct:+.1f}% &nbsp;|&nbsp; **Market Cap:** {"${:.2f}B".format(state['market_cap']/1e9) if state['market_cap'] > 0 else "N/A"}

---

## Executive Summary

{state['investment_thesis']}

---

## Comprehensive Analysis

{state['comprehensive_analysis']}

---

## Quarterly Earnings Data

{self._clean_field(state['earnings_history'], 'Quarterly earnings')}

### Earnings Surprises

{self._clean_field(state['earnings_surprises'], 'Earnings surprises')}

---

## Management Guidance & Earnings Call Insights

{self._clean_field(state['earnings_guidance'], 'Earnings call insights')}

### Analyst Estimates

{self._clean_field(state['analyst_estimates'], 'Analyst estimates')}

---

## Peer Comparison

{self._clean_field(state['peer_comparison'], 'Peer comparison')}

{errors_md}
---

*Generated by AI Earnings Analyst in {minutes}m {seconds}s. Based on publicly available data. Not investment advice.*"""

            logger.info(f"  → Report generated ({len(report)} chars)")
            self._emit_progress("generate_report", "completed", "Report ready")
            return {"final_report": report}

        except Exception as e:
            logger.error(f"Error in generate_report: {e}")
            self._emit_progress("generate_report", "completed", "Partial data (error)")
            return {
                "final_report": f"ERROR GENERATING REPORT for {state['ticker']}: {str(e)}",
                "errors": [f"Report generation error: {str(e)}"],
            }

    # ========================================================================
    # Shared helpers
    # ========================================================================

    @staticmethod
    def _clean_field(value: str, label: str, limit: int = 0) -> str:
        """Return data value or a clear unavailable notice.

        Filters out empty values and raw error strings so neither the LLM
        prompt nor the user-facing report ever shows an error traceback.
        Optional `limit` truncates to that many characters (0 = no limit).
        """
        text = (value or "").strip()
        if not text or text.lower().startswith(EarningsAgent._ERROR_PREFIXES):
            return f"({label} unavailable)"
        return text[:limit] if limit else text

    @staticmethod
    def _build_initial_state(ticker: str, quarters_back: int = 8) -> dict:
        return {
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
            "sec_filings_summary": "",
            "comprehensive_analysis": "",
            "investment_thesis": "",
            "price_target": 0.0,
            "key_catalysts": [],
            "key_risks": [],
            "final_report": "",
            "start_time": time.time(),
            "errors": [],
        }

    # ========================================================================
    # Direct CLI method
    # ========================================================================

    def analyze(self, ticker: str, quarters_back: int = 8) -> str:
        result = self.graph.invoke(self._build_initial_state(ticker, quarters_back))
        return result.get("final_report", "Error: No report generated")


# ============================================================================
# Factory Function
# ============================================================================

def create_earnings_agent(model: str = "claude-sonnet-4-5-20250929") -> EarningsAgent:
    """Factory function to create an earnings agent."""
    return EarningsAgent(model=model)
