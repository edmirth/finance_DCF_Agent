"""
Earnings-Focused Equity Research Agent using LangGraph

Generates comprehensive equity research reports in ~15 minutes focusing on:
- Latest earnings reports & historical trends
- Analyst estimates & earnings surprises
- Management guidance analysis
- Competitive comparison
- Investment thesis with BUY/HOLD/SELL rating
"""
from typing import TypedDict, List, Dict, Optional, Annotated
import operator
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
import time
import logging
import re
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# State Reducers
# ============================================================================

def keep_first(left, right):
    """Reducer that keeps the first non-None/non-empty value"""
    return left if left else right


# ============================================================================
# State Schema - Defines data flow through the graph
# ============================================================================

class EarningsAnalysisState(TypedDict):
    """
    State object that flows through all nodes in the LangGraph workflow.
    Each node reads from and writes to this state.
    Using Annotated with reducers to handle parallel node updates.
    """
    # Input - use keep_first to keep first value from parallel nodes
    ticker: Annotated[str, keep_first]
    quarters_back: Annotated[int, keep_first]

    # Company Context (Node 1) - use keep_first since only one node writes
    company_name: Annotated[str, keep_first]
    sector: Annotated[str, keep_first]
    industry: Annotated[str, keep_first]
    current_price: Annotated[float, keep_first]
    market_cap: Annotated[float, keep_first]

    # Earnings Data (Nodes 2-4) - different nodes write to different fields
    earnings_history: Annotated[str, keep_first]
    analyst_estimates: Annotated[str, keep_first]
    earnings_surprises: Annotated[str, keep_first]
    earnings_guidance: Annotated[str, keep_first]
    market_news: Annotated[str, keep_first]
    peer_comparison: Annotated[str, keep_first]

    # Analysis Results (Nodes 5-9) - different nodes write to different fields
    earnings_trend: Annotated[str, keep_first]
    quality_analysis: Annotated[str, keep_first]
    guidance_analysis: Annotated[str, keep_first]
    competitive_analysis: Annotated[str, keep_first]
    valuation_analysis: Annotated[str, keep_first]

    # Final Output (Nodes 10-11)
    investment_thesis: Annotated[str, keep_first]
    rating: Annotated[str, keep_first]
    price_target: Annotated[float, keep_first]
    key_catalysts: Annotated[List[str], keep_first]
    key_risks: Annotated[List[str], keep_first]
    final_report: Annotated[str, keep_first]

    # Metadata - errors accumulate so use operator.add
    start_time: Annotated[float, keep_first]
    errors: Annotated[List[str], operator.add]


# ============================================================================
# Backend Compatibility Adapter
# ============================================================================

class EarningsAgentExecutorAdapter:
    """
    Adapter to make LangGraph compatible with existing backend streaming.

    Backend expects: agent.agent_executor.invoke({"input": query}, config={...})
    LangGraph uses: graph.invoke(state, config={...})

    This adapter translates between the two interfaces.
    """

    def __init__(self, graph):
        self.graph = graph
        self.ticker_pattern = re.compile(r'\b[A-Z]{1,5}\b')  # Match stock tickers

    def invoke(self, input_dict: dict, config: Optional[dict] = None) -> dict:
        """
        Translate backend's invoke call to LangGraph invoke.

        Args:
            input_dict: {"input": "Analyze AAPL's latest earnings"}
            config: Optional config with callbacks

        Returns:
            {"output": "Complete earnings report..."}
        """
        try:
            # Extract ticker from user query
            query = input_dict.get("input", "")
            ticker = self._extract_ticker(query)

            if not ticker:
                return {"output": "Error: Please provide a stock ticker symbol (e.g., AAPL, MSFT, NVDA)"}

            logger.info(f"Starting earnings analysis for {ticker}")

            # Initialize state
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
                "market_news": "",
                "peer_comparison": "",
                "earnings_trend": "",
                "quality_analysis": "",
                "guidance_analysis": "",
                "competitive_analysis": "",
                "valuation_analysis": "",
                "investment_thesis": "",
                "rating": "",
                "price_target": 0.0,
                "key_catalysts": [],
                "key_risks": [],
                "final_report": "",
                "start_time": time.time(),
                "errors": []
            }

            # Invoke the graph
            result = self.graph.invoke(initial_state, config=config)

            # Calculate execution time
            execution_time = time.time() - result["start_time"]
            logger.info(f"Earnings analysis completed in {execution_time:.1f} seconds")

            # Return in backend-expected format
            final_output = result.get("final_report", "Error: No report generated")

            # Append execution time
            final_output += f"\n\n---\n*Analysis completed in {execution_time/60:.1f} minutes*"

            return {"output": final_output}

        except Exception as e:
            logger.error(f"Error in earnings agent: {e}")
            return {"output": f"Error analyzing earnings: {str(e)}"}

    def _extract_ticker(self, query: str) -> Optional[str]:
        """Extract ticker symbol from user query"""
        # Look for common patterns
        query_upper = query.upper()

        # Check for explicit mentions
        for word in query_upper.split():
            # Remove punctuation
            clean_word = re.sub(r'[^\w]', '', word)
            # Check if it looks like a ticker (1-5 uppercase letters)
            if len(clean_word) >= 1 and len(clean_word) <= 5 and clean_word.isalpha():
                # Common stock tickers
                if clean_word in ['AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'NVDA', 'TSLA',
                                  'META', 'NFLX', 'AMD', 'INTC', 'CSCO', 'ADBE', 'CRM',
                                  'ORCL', 'IBM', 'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C',
                                  'V', 'MA', 'PYPL', 'SQ', 'DIS', 'CMCSA', 'T', 'VZ',
                                  'KO', 'PEP', 'WMT', 'TGT', 'HD', 'LOW', 'NKE', 'SBUX',
                                  'MCD', 'BA', 'CAT', 'DE', 'MMM', 'GE', 'F', 'GM']:
                    return clean_word

        # If no known ticker found, try to find any valid ticker pattern
        matches = self.ticker_pattern.findall(query_upper)
        if matches:
            # Return the first match that's not a common word
            common_words = ['THE', 'AND', 'FOR', 'WITH', 'FROM', 'ABOUT', 'WHAT', 'HOW', 'WHY']
            for match in matches:
                if match not in common_words:
                    return match

        return None


# ============================================================================
# Earnings Agent Class
# ============================================================================

class EarningsAgent:
    """
    LangGraph-based earnings research agent.

    Workflow:
    1. Fetch company info
    2. Parallel: Fetch earnings, estimates, guidance, news
    3. Aggregate data
    4. Parallel: Analyze trend, quality, guidance, competition
    5. Calculate valuation
    6. Develop thesis
    7. Generate report
    """

    def __init__(self, model: str = "gpt-5.2"):
        """
        Initialize the earnings agent.

        Args:
            model: LLM model to use (default: gpt-5.2 for speed and quality)
        """
        self.model = model
        self.llm = ChatOpenAI(model=model, temperature=0)

        # Import tools
        from tools.earnings_tools import get_earnings_tools
        self.tools = get_earnings_tools()

        # Build the LangGraph workflow
        self.graph = self._build_graph()

        # Create adapter for backend compatibility
        self.agent_executor = EarningsAgentExecutorAdapter(self.graph)

        logger.info(f"Earnings Agent initialized with model: {model}")

    def _build_graph(self) -> StateGraph:
        """
        Build the LangGraph workflow with all nodes and edges.

        This is where we define the execution flow and parallelization.
        """
        # Create graph with our state schema
        workflow = StateGraph(EarningsAnalysisState)

        # Add all nodes (we'll implement these methods next)
        workflow.add_node("fetch_company_info", self.fetch_company_info)
        workflow.add_node("fetch_earnings_history", self.fetch_earnings_history)
        workflow.add_node("fetch_analyst_estimates", self.fetch_analyst_estimates)
        workflow.add_node("fetch_guidance_and_news", self.fetch_guidance_and_news)
        workflow.add_node("aggregate_data", self.aggregate_data)
        workflow.add_node("analyze_earnings_trend", self.analyze_earnings_trend)
        workflow.add_node("analyze_quality", self.analyze_quality)
        workflow.add_node("analyze_guidance", self.analyze_guidance)
        workflow.add_node("analyze_competition", self.analyze_competition)
        workflow.add_node("calculate_valuation", self.calculate_valuation)
        workflow.add_node("develop_thesis", self.develop_thesis)
        workflow.add_node("generate_report", self.generate_report)

        # Define the workflow edges
        # Start with company info
        workflow.set_entry_point("fetch_company_info")

        # Phase 1: Parallel data gathering (after company info)
        workflow.add_edge("fetch_company_info", "fetch_earnings_history")
        workflow.add_edge("fetch_company_info", "fetch_analyst_estimates")
        workflow.add_edge("fetch_company_info", "fetch_guidance_and_news")

        # All Phase 1 nodes converge to aggregate
        workflow.add_edge("fetch_earnings_history", "aggregate_data")
        workflow.add_edge("fetch_analyst_estimates", "aggregate_data")
        workflow.add_edge("fetch_guidance_and_news", "aggregate_data")

        # Phase 2: Parallel analysis (after aggregation)
        workflow.add_edge("aggregate_data", "analyze_earnings_trend")
        workflow.add_edge("aggregate_data", "analyze_quality")
        workflow.add_edge("aggregate_data", "analyze_guidance")
        workflow.add_edge("aggregate_data", "analyze_competition")

        # All Phase 2 nodes converge to valuation
        workflow.add_edge("analyze_earnings_trend", "calculate_valuation")
        workflow.add_edge("analyze_quality", "calculate_valuation")
        workflow.add_edge("analyze_guidance", "calculate_valuation")
        workflow.add_edge("analyze_competition", "calculate_valuation")

        # Phase 3: Sequential synthesis
        workflow.add_edge("calculate_valuation", "develop_thesis")
        workflow.add_edge("develop_thesis", "generate_report")

        # End after report generation
        workflow.add_edge("generate_report", END)

        # Compile and return
        return workflow.compile()

    # ========================================================================
    # Node Implementations (we'll add these step by step)
    # ========================================================================

    def fetch_company_info(self, state: EarningsAnalysisState) -> EarningsAnalysisState:
        """
        Node 1: Fetch basic company information.

        This runs first and provides context for all other nodes.
        """
        logger.info(f"Node 1: Fetching company info for {state['ticker']}")

        try:
            from data.financial_data import FinancialDataFetcher
            fetcher = FinancialDataFetcher()

            # Get company info
            info = fetcher.get_stock_info(state["ticker"])

            if not info:
                state["errors"].append("Failed to fetch company info")
                return state

            # Update state
            state["company_name"] = info.get("company_name", "Unknown")
            state["sector"] = info.get("sector", "Unknown")
            state["industry"] = info.get("industry", "Unknown")
            state["current_price"] = info.get("current_price", 0.0)
            state["market_cap"] = info.get("market_cap", 0.0)

            logger.info(f"✓ Company info: {state['company_name']} ({state['sector']})")

        except Exception as e:
            logger.error(f"Error in fetch_company_info: {e}")
            state["errors"].append(f"Company info error: {str(e)}")

        return state

    # We'll implement the remaining 11 nodes in the next step
    # For now, let's add placeholder stubs

    def fetch_earnings_history(self, state: EarningsAnalysisState) -> EarningsAnalysisState:
        """
        Node 2: Fetch quarterly earnings history (last 8 quarters).

        This runs in parallel with fetch_analyst_estimates and fetch_guidance_and_news.
        """
        logger.info(f"Node 2: Fetching earnings history for {state['ticker']}")

        try:
            # Get the quarterly earnings tool
            from tools.earnings_tools import GetQuarterlyEarningsTool
            tool = GetQuarterlyEarningsTool()

            # Fetch quarterly earnings data
            earnings_data = tool._run(
                ticker=state["ticker"],
                quarters=state["quarters_back"]
            )

            # Store in state
            state["earnings_history"] = earnings_data
            logger.info(f"✓ Earnings history fetched for {state['ticker']}")

        except Exception as e:
            logger.error(f"Error in fetch_earnings_history: {e}")
            state["errors"].append(f"Earnings history error: {str(e)}")
            state["earnings_history"] = f"Error fetching earnings data: {str(e)}"

        return state

    def fetch_analyst_estimates(self, state: EarningsAnalysisState) -> EarningsAnalysisState:
        """
        Node 3: Fetch analyst consensus estimates.

        This runs in parallel with fetch_earnings_history and fetch_guidance_and_news.
        """
        logger.info(f"Node 3: Fetching analyst estimates for {state['ticker']}")

        try:
            # Get the analyst estimates tool
            from tools.earnings_tools import GetAnalystEstimatesTool
            tool = GetAnalystEstimatesTool()

            # Fetch analyst estimates
            estimates_data = tool._run(ticker=state["ticker"])

            # Store in state
            state["analyst_estimates"] = estimates_data
            logger.info(f"✓ Analyst estimates fetched for {state['ticker']}")

        except Exception as e:
            logger.error(f"Error in fetch_analyst_estimates: {e}")
            state["errors"].append(f"Analyst estimates error: {str(e)}")
            state["analyst_estimates"] = f"Error fetching analyst estimates: {str(e)}"

        return state

    def fetch_guidance_and_news(self, state: EarningsAnalysisState) -> EarningsAnalysisState:
        """
        Node 4: Fetch earnings surprises, guidance, and peer comparison.

        This runs in parallel with fetch_earnings_history and fetch_analyst_estimates.
        Combines multiple tool calls into one node.
        """
        logger.info(f"Node 4: Fetching surprises, guidance, and peer data for {state['ticker']}")

        try:
            from tools.earnings_tools import (
                GetEarningsSurprisesTool,
                AnalyzeEarningsGuidanceTool,
                ComparePeerEarningsTool
            )

            # Fetch earnings surprises
            surprises_tool = GetEarningsSurprisesTool()
            surprises_data = surprises_tool._run(
                ticker=state["ticker"],
                quarters=state["quarters_back"]
            )
            state["earnings_surprises"] = surprises_data
            logger.info(f"✓ Earnings surprises fetched")

            # Fetch earnings guidance
            guidance_tool = AnalyzeEarningsGuidanceTool()
            guidance_data = guidance_tool._run(ticker=state["ticker"])
            state["earnings_guidance"] = guidance_data
            logger.info(f"✓ Earnings guidance fetched")

            # Fetch peer comparison
            peer_tool = ComparePeerEarningsTool()
            peer_data = peer_tool._run(ticker=state["ticker"], peers=None)
            state["peer_comparison"] = peer_data
            logger.info(f"✓ Peer comparison fetched")

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

    def aggregate_data(self, state: EarningsAnalysisState) -> EarningsAnalysisState:
        """
        Node 5: Aggregate all gathered data.

        This is a synchronization point - waits for all parallel Phase 1 nodes to complete.
        No actual processing, just ensures all data is ready for analysis.
        """
        logger.info("Node 5: All data gathered, ready for analysis")

        # Log what we have
        has_earnings = bool(state.get("earnings_history"))
        has_estimates = bool(state.get("analyst_estimates"))
        has_surprises = bool(state.get("earnings_surprises"))
        has_guidance = bool(state.get("earnings_guidance"))
        has_peers = bool(state.get("peer_comparison"))

        logger.info(f"✓ Data completeness: Earnings={has_earnings}, Estimates={has_estimates}, "
                   f"Surprises={has_surprises}, Guidance={has_guidance}, Peers={has_peers}")

        return state

    def analyze_earnings_trend(self, state: EarningsAnalysisState) -> EarningsAnalysisState:
        """
        Node 6: Analyze earnings growth trends.

        Uses LLM to analyze quarterly earnings data and identify:
        - Growth trajectory (accelerating/stable/decelerating)
        - Revenue and EPS trends
        - Margin expansion/contraction
        """
        logger.info(f"Node 6: Analyzing earnings trends for {state['ticker']}")

        try:
            prompt = f"""Analyze the earnings trends for {state['company_name']} ({state['ticker']}):

QUARTERLY EARNINGS DATA:
{state['earnings_history']}

EARNINGS SURPRISES:
{state['earnings_surprises']}

Provide a concise analysis (2-3 paragraphs) covering:
1. Revenue Growth Trajectory: Is growth accelerating, stable, or decelerating? Cite specific QoQ and YoY numbers.
2. EPS Trends: How is profitability trending? Any margin expansion/contraction?
3. Consistency: Does the company consistently beat, meet, or miss expectations?
4. Key Inflection Points: Any notable changes in trajectory?

Be specific with numbers and percentages. Focus on the trend, not just latest quarter."""

            messages = [
                SystemMessage(content="You are a financial analyst specializing in earnings analysis."),
                HumanMessage(content=prompt)
            ]

            response = self.llm.invoke(messages)
            state["earnings_trend"] = response.content

            logger.info(f"✓ Earnings trend analysis complete")

        except Exception as e:
            logger.error(f"Error in analyze_earnings_trend: {e}")
            state["errors"].append(f"Trend analysis error: {str(e)}")
            state["earnings_trend"] = "Error analyzing earnings trends"

        return state

    def analyze_quality(self, state: EarningsAnalysisState) -> EarningsAnalysisState:
        """
        Node 7: Analyze earnings quality.

        Assesses the quality and sustainability of earnings through:
        - Cash flow analysis
        - One-time items
        - Accounting quality
        """
        logger.info(f"Node 7: Analyzing earnings quality for {state['ticker']}")

        try:
            prompt = f"""Assess the earnings quality for {state['company_name']} ({state['ticker']}):

QUARTERLY EARNINGS DATA (including cash flow):
{state['earnings_history']}

EARNINGS SURPRISES PATTERN:
{state['earnings_surprises']}

Provide a concise assessment (2-3 paragraphs) covering:
1. Cash Flow Quality: How does operating cash flow compare to reported earnings? Is FCF growing?
2. Earnings Consistency: Are earnings predictable or volatile? Any one-time items?
3. Surprise Pattern: Does consistent beating indicate genuine strength or lowballing?
4. Quality Score: Rate as HIGH, MEDIUM, or LOW quality with justification.

Be specific and cite numbers. Conclude with an overall quality assessment."""

            messages = [
                SystemMessage(content="You are a financial analyst specializing in earnings quality assessment."),
                HumanMessage(content=prompt)
            ]

            response = self.llm.invoke(messages)
            state["quality_analysis"] = response.content

            logger.info(f"✓ Earnings quality analysis complete")

        except Exception as e:
            logger.error(f"Error in analyze_quality: {e}")
            state["errors"].append(f"Quality analysis error: {str(e)}")
            state["quality_analysis"] = "Error analyzing earnings quality"

        return state

    def analyze_guidance(self, state: EarningsAnalysisState) -> EarningsAnalysisState:
        """
        Node 8: Analyze management guidance.

        Evaluates forward-looking statements and management outlook.
        """
        logger.info(f"Node 8: Analyzing guidance for {state['ticker']}")

        try:
            prompt = f"""Analyze the forward guidance for {state['company_name']} ({state['ticker']}):

MANAGEMENT GUIDANCE:
{state['earnings_guidance']}

ANALYST CONSENSUS ESTIMATES:
{state['analyst_estimates']}

Provide analysis (2-3 paragraphs) covering:
1. Guidance vs. Expectations: Is management guidance above, below, or in-line with consensus?
2. Guidance Changes: Has guidance been raised, lowered, or maintained recently?
3. Management Tone: What's the confidence level based on commentary?
4. Key Drivers: What growth drivers or headwinds did management highlight?
5. Credibility: Does management have a track record of accurate guidance?

Be specific about guidance numbers and how they compare to street estimates."""

            messages = [
                SystemMessage(content="You are a financial analyst specializing in management guidance analysis."),
                HumanMessage(content=prompt)
            ]

            response = self.llm.invoke(messages)
            state["guidance_analysis"] = response.content

            logger.info(f"✓ Guidance analysis complete")

        except Exception as e:
            logger.error(f"Error in analyze_guidance: {e}")
            state["errors"].append(f"Guidance analysis error: {str(e)}")
            state["guidance_analysis"] = "Error analyzing guidance"

        return state

    def analyze_competition(self, state: EarningsAnalysisState) -> EarningsAnalysisState:
        """
        Node 9: Analyze competitive position.

        Compares company performance vs peers.
        """
        logger.info(f"Node 9: Analyzing competitive position for {state['ticker']}")

        try:
            prompt = f"""Analyze the competitive positioning for {state['company_name']} ({state['ticker']}):

PEER EARNINGS COMPARISON:
{state['peer_comparison']}

COMPANY EARNINGS TREND:
{state['earnings_trend']}

Provide analysis (2-3 paragraphs) covering:
1. Relative Performance: Is {state['ticker']} outperforming or underperforming peers in revenue/EPS growth?
2. Margin Comparison: How do margins compare to industry peers?
3. Market Share Implications: Is the company gaining or losing share?
4. Competitive Strengths: What's driving relative outperformance or underperformance?
5. Positioning: Rate competitive position as STRONG, MODERATE, or WEAK.

Be specific with relative metrics (e.g., "AAPL growing 8% vs peer average 12%")."""

            messages = [
                SystemMessage(content="You are a financial analyst specializing in competitive analysis."),
                HumanMessage(content=prompt)
            ]

            response = self.llm.invoke(messages)
            state["competitive_analysis"] = response.content

            logger.info(f"✓ Competitive analysis complete")

        except Exception as e:
            logger.error(f"Error in analyze_competition: {e}")
            state["errors"].append(f"Competition analysis error: {str(e)}")
            state["competitive_analysis"] = "Error analyzing competition"

        return state

    def calculate_valuation(self, state: EarningsAnalysisState) -> EarningsAnalysisState:
        """Node 10: Calculate forward valuation metrics"""
        logger.info(f"Node 10: Calculating valuation for {state['ticker']}")

        try:
            prompt = f"""Calculate forward valuation metrics for {state['company_name']} ({state['ticker']}):

CURRENT METRICS:
- Current Price: ${state['current_price']:.2f}
- Market Cap: ${state['market_cap']/1e9:.2f}B

ANALYST ESTIMATES:
{state['analyst_estimates']}

EARNINGS TREND:
{state['earnings_trend']}

QUALITY ANALYSIS:
{state['quality_analysis']}

COMPETITIVE POSITION:
{state['competitive_analysis']}

Calculate and explain:
1. Forward P/E Ratio: Based on next 12 months EPS estimate
2. PEG Ratio: Forward P/E divided by expected growth rate
3. Valuation Context: Is the stock trading at premium or discount vs:
   - Historical average
   - Sector peers
   - Growth rate justified multiple
4. Fair Value Range: Provide reasonable valuation range considering:
   - Earnings quality (high quality = premium multiple)
   - Growth trajectory (accelerating = higher multiple)
   - Competitive position (strong = premium)

Be specific with calculations and justify the multiples."""

            messages = [
                SystemMessage(content="You are a financial analyst specializing in equity valuation."),
                HumanMessage(content=prompt)
            ]

            response = self.llm.invoke(messages)
            state["valuation_analysis"] = response.content

            logger.info(f"✓ Valuation analysis complete")

        except Exception as e:
            logger.error(f"Error in calculate_valuation: {e}")
            state["errors"].append(f"Valuation error: {str(e)}")
            state["valuation_analysis"] = "Error calculating valuation"

        return state

    def develop_thesis(self, state: EarningsAnalysisState) -> EarningsAnalysisState:
        """Node 11: Develop investment thesis with rating and price target"""
        logger.info(f"Node 11: Developing investment thesis for {state['ticker']}")

        try:
            prompt = f"""Develop a comprehensive investment thesis for {state['company_name']} ({state['ticker']}):

CURRENT PRICE: ${state['current_price']:.2f}

EARNINGS TREND:
{state['earnings_trend']}

QUALITY ANALYSIS:
{state['quality_analysis']}

GUIDANCE ANALYSIS:
{state['guidance_analysis']}

COMPETITIVE ANALYSIS:
{state['competitive_analysis']}

VALUATION ANALYSIS:
{state['valuation_analysis']}

Based on all the analysis above, provide:

1. INVESTMENT RATING: Choose ONE of:
   - BUY (if expected upside > 15% with favorable risk/reward)
   - HOLD (if expected return 0-15% or mixed signals)
   - SELL (if downside risk > 10% or deteriorating fundamentals)

2. PRICE TARGET (12-month): Specific price based on:
   - Forward earnings estimates
   - Justified valuation multiple
   - Current price: ${state['current_price']:.2f}
   Format as: "$XXX.XX"

3. INVESTMENT THESIS (3-4 paragraphs):
   - Why this rating makes sense
   - Key drivers of the thesis
   - Risk/reward assessment

4. BULL CASE (3-4 key points):
   - What would drive outperformance
   - Upside catalysts
   - Positive scenarios

5. BEAR CASE (3-4 key points):
   - What could go wrong
   - Downside risks
   - Negative scenarios

6. KEY CATALYSTS (3-5 specific near-term events):
   - Upcoming earnings dates
   - Product launches
   - Regulatory decisions
   - Industry events
   Format each as a short phrase

7. KEY RISKS (3-5 specific risks):
   - Competitive threats
   - Execution risks
   - Market risks
   Format each as a short phrase

Be specific, quantitative, and decisive. Don't hedge excessively."""

            messages = [
                SystemMessage(content="You are a senior equity research analyst making actionable investment recommendations."),
                HumanMessage(content=prompt)
            ]

            response = self.llm.invoke(messages)
            thesis_text = response.content

            # Extract structured data from the thesis
            state["investment_thesis"] = thesis_text

            # Extract rating (look for BUY, HOLD, or SELL)
            rating_match = None
            for line in thesis_text.split('\n'):
                line_upper = line.upper()
                if 'RATING' in line_upper or 'RECOMMENDATION' in line_upper:
                    if 'BUY' in line_upper and 'SELL' not in line_upper:
                        rating_match = 'BUY'
                        break
                    elif 'SELL' in line_upper:
                        rating_match = 'SELL'
                        break
                    elif 'HOLD' in line_upper:
                        rating_match = 'HOLD'
                        break

            state["rating"] = rating_match if rating_match else "HOLD"

            # Extract price target (look for $ followed by numbers)
            import re
            price_pattern = r'\$(\d+(?:\.\d{2})?)'
            prices = re.findall(price_pattern, thesis_text)
            if prices:
                # Find the price target (usually the first significant price mentioned after "target")
                target_price = None
                for i, line in enumerate(thesis_text.split('\n')):
                    if 'TARGET' in line.upper() or 'PRICE TARGET' in line.upper():
                        prices_in_line = re.findall(price_pattern, line)
                        if prices_in_line:
                            target_price = float(prices_in_line[0])
                            break

                if target_price:
                    state["price_target"] = target_price
                else:
                    # Fallback: use first reasonable price found
                    for p in prices:
                        p_float = float(p)
                        # Price target should be within reasonable range of current price
                        if 0.5 * state['current_price'] < p_float < 3.0 * state['current_price']:
                            state["price_target"] = p_float
                            break

            # Extract catalysts (look for CATALYST or CATALYSTS section)
            catalysts = []
            in_catalyst_section = False
            for line in thesis_text.split('\n'):
                line_stripped = line.strip()
                if 'CATALYST' in line_stripped.upper():
                    in_catalyst_section = True
                    continue
                if in_catalyst_section:
                    if line_stripped and (line_stripped.startswith('-') or line_stripped.startswith('•') or line_stripped[0].isdigit()):
                        # Extract the catalyst text
                        catalyst = line_stripped.lstrip('-•0123456789. ').strip()
                        if catalyst and len(catalyst) > 10:  # Meaningful catalyst
                            catalysts.append(catalyst)
                    elif 'RISK' in line_stripped.upper() or 'BEAR' in line_stripped.upper():
                        break  # End of catalyst section

            state["key_catalysts"] = catalysts[:5] if catalysts else ["Next earnings report", "Industry trends", "Market conditions"]

            # Extract risks (look for RISK or RISKS section)
            risks = []
            in_risk_section = False
            for line in thesis_text.split('\n'):
                line_stripped = line.strip()
                if 'RISK' in line_stripped.upper() and 'KEY RISK' in line_stripped.upper():
                    in_risk_section = True
                    continue
                if in_risk_section:
                    if line_stripped and (line_stripped.startswith('-') or line_stripped.startswith('•') or line_stripped[0].isdigit()):
                        risk = line_stripped.lstrip('-•0123456789. ').strip()
                        if risk and len(risk) > 10:
                            risks.append(risk)
                    elif len(risks) >= 3 and (not line_stripped or line_stripped.startswith('#')):
                        break

            state["key_risks"] = risks[:5] if risks else ["Market volatility", "Execution risk", "Competitive pressure"]

            logger.info(f"✓ Investment thesis developed: {state['rating']} with ${state['price_target']:.2f} target")

        except Exception as e:
            logger.error(f"Error in develop_thesis: {e}")
            state["errors"].append(f"Thesis development error: {str(e)}")
            state["investment_thesis"] = "Error developing investment thesis"
            state["rating"] = "HOLD"
            state["price_target"] = state['current_price']
            state["key_catalysts"] = ["Unable to determine catalysts"]
            state["key_risks"] = ["Unable to determine risks"]

        return state

    def generate_report(self, state: EarningsAnalysisState) -> EarningsAnalysisState:
        """Node 12: Generate final formatted report"""
        logger.info(f"Node 12: Generating final report for {state['ticker']}")

        try:
            # Calculate upside/downside
            upside_pct = ((state['price_target'] - state['current_price']) / state['current_price']) * 100

            # Format execution time
            execution_time = time.time() - state['start_time']
            minutes = int(execution_time // 60)
            seconds = int(execution_time % 60)

            # Build the comprehensive report
            report = f"""
{'='*80}
EARNINGS-FOCUSED EQUITY RESEARCH REPORT
{'='*80}

COMPANY: {state['company_name']} ({state['ticker']})
SECTOR: {state['sector']} | INDUSTRY: {state['industry']}
CURRENT PRICE: ${state['current_price']:.2f} | MARKET CAP: ${state['market_cap']/1e9:.2f}B

INVESTMENT RATING: {state['rating']}
PRICE TARGET (12M): ${state['price_target']:.2f}
IMPLIED RETURN: {upside_pct:+.1f}%

Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}
Analysis Time: {minutes}m {seconds}s

{'='*80}
EXECUTIVE SUMMARY
{'='*80}

{state['investment_thesis']}

{'='*80}
QUARTERLY EARNINGS ANALYSIS
{'='*80}

{state['earnings_history']}

EARNINGS TREND ANALYSIS:
{state['earnings_trend']}

EARNINGS SURPRISES:
{state['earnings_surprises']}

{'='*80}
EARNINGS QUALITY ASSESSMENT
{'='*80}

{state['quality_analysis']}

{'='*80}
GUIDANCE & FORWARD ESTIMATES
{'='*80}

ANALYST ESTIMATES:
{state['analyst_estimates']}

GUIDANCE ANALYSIS:
{state['guidance_analysis']}

{'='*80}
COMPETITIVE POSITIONING
{'='*80}

PEER COMPARISON:
{state['peer_comparison']}

COMPETITIVE ANALYSIS:
{state['competitive_analysis']}

{'='*80}
VALUATION ASSESSMENT
{'='*80}

{state['valuation_analysis']}

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
MARKET CONTEXT
{'='*80}

{state['market_news']}

{'='*80}
BOTTOM LINE
{'='*80}

RATING: {state['rating']}
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
            logger.info(f"✓ Final report generated ({len(report)} characters)")

        except Exception as e:
            logger.error(f"Error in generate_report: {e}")
            state["errors"].append(f"Report generation error: {str(e)}")
            state["final_report"] = f"""
ERROR GENERATING REPORT

An error occurred while formatting the final report for {state['ticker']}.

Raw Analysis Available:
- Earnings Trend: {state['earnings_trend'][:200]}...
- Rating: {state['rating']}
- Price Target: ${state['price_target']:.2f}

Error: {str(e)}
"""

        return state

    def analyze(self, ticker: str, quarters_back: int = 8) -> str:
        """
        Direct analysis method for CLI usage.

        Args:
            ticker: Stock ticker symbol
            quarters_back: Number of quarters to analyze

        Returns:
            Complete earnings research report
        """
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
            "market_news": "",
            "peer_comparison": "",
            "earnings_trend": "",
            "quality_analysis": "",
            "guidance_analysis": "",
            "competitive_analysis": "",
            "valuation_analysis": "",
            "investment_thesis": "",
            "rating": "",
            "price_target": 0.0,
            "key_catalysts": [],
            "key_risks": [],
            "final_report": "",
            "start_time": time.time(),
            "errors": []
        }

        result = self.graph.invoke(initial_state)
        return result.get("final_report", "Error: No report generated")


# ============================================================================
# Factory Function
# ============================================================================

def create_earnings_agent(model: str = "gpt-5.2") -> EarningsAgent:
    """
    Factory function to create an earnings agent.
    Matches the pattern used by other agents in the system.

    Args:
        model: LLM model to use (default: gpt-5.2)

    Returns:
        Configured EarningsAgent instance
    """
    return EarningsAgent(model=model)
