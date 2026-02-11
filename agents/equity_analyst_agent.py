"""
Equity Analyst Agent - Professional equity research and investment analysis
"""
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tools.dcf_tools import get_dcf_tools
from tools.equity_analyst_tools import get_equity_analyst_tools
from agents.reasoning_callback import StreamingReasoningCallback
from typing import Optional
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EquityAnalystAgent:
    """AI Agent for comprehensive equity research analysis"""

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-sonnet-4-5-20250929", show_reasoning: bool = True):
        """
        Initialize the Equity Analyst Agent

        Args:
            api_key: Anthropic API key (if not provided, will use ANTHROPIC_API_KEY env var)
            model: Anthropic model to use (default: claude-sonnet-4-5-20250929)
            show_reasoning: Whether to display agent reasoning steps (default: True)
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("Anthropic API key not found. Set ANTHROPIC_API_KEY environment variable.")

        self.model = model
        self.show_reasoning = show_reasoning

        # Combine DCF tools with equity analyst tools
        self.tools = get_dcf_tools() + get_equity_analyst_tools()

        # Initialize reasoning callback
        self.reasoning_callback = StreamingReasoningCallback(verbose=show_reasoning)

        self.agent_executor = self._create_agent()

    def _create_agent(self) -> AgentExecutor:
        """Create the LangChain agent with tools using tool calling pattern"""

        # Initialize LLM
        llm = ChatAnthropic(
            model=self.model,
            temperature=0,
            anthropic_api_key=self.api_key,
            max_retries=3,  # Retry failed API calls
            default_request_timeout=60.0,  # Request timeout in seconds
            max_tokens=8192,  # Max output tokens
        )

        # Create system message with workflow instructions
        from datetime import datetime
        current_date = datetime.now().strftime("%B %d, %Y")

        system_message = f"""You are a professional equity research analyst with access to real-time data tools.
**TODAY'S DATE: {current_date}**

IMPORTANT: You CAN and MUST use the tools provided to gather current information and perform analysis.

**CRITICAL - TWO-PHASE APPROACH:**
You MUST follow a two-phase approach: PLANNING → EXECUTION

═══════════════════════════════════════════════════════════════════════════════
PHASE 1: PLANNING (Do this FIRST, before any tool calls)
═══════════════════════════════════════════════════════════════════════════════

Before making ANY tool calls, create and present a detailed execution plan to the user:

**Output this plan in markdown:**

## 📋 EQUITY RESEARCH EXECUTION PLAN

**Company:** [Ticker] - [Company Name]
**Analysis Date:** {current_date}

### Research Objectives
- [ ] Understand business model and competitive positioning
- [ ] Assess industry dynamics and market opportunity
- [ ] Evaluate competitive moat and advantages
- [ ] Perform comprehensive financial analysis
- [ ] Calculate intrinsic value (DCF)
- [ ] Develop investment thesis with bull/bear cases

### Execution Steps

**Step 1: Company & Business Model Understanding**
- Tool: `get_stock_info` → Get basic company data
- Tool: `search_web` → Research business model, revenue streams, customer base
- Expected Output: Clear understanding of what the company does and how it makes money

**Step 2: Industry Analysis**
- Tool: `analyze_industry` → Market size, Porter's 5 Forces, trends, benchmarks
- Expected Output: Industry context, TAM, growth rates, competitive dynamics

**Step 3: Competitive Landscape**
- Tool: `analyze_competitors` → Top competitors, market share, positioning
- Expected Output: Who are the main competitors? Who's winning and why?

**Step 4: Competitive Moat Assessment**
- Tool: `analyze_moat` → Brand, network effects, switching costs, pricing power
- Expected Output: Moat strength (None/Narrow/Wide) with specific evidence

**Step 5: Financial Analysis**
- Tool: `get_financial_metrics` → Historical financials (5 years)
- Tool: `search_web` → Latest earnings, guidance, analyst estimates, beta, growth forecasts
- Expected Output: Revenue/margin trends, ROIC, cash flow quality, balance sheet strength

**Step 6: Valuation (DCF)**
- Tool: `perform_dcf_analysis` → Intrinsic value calculation with web-sourced parameters
- Parameters to gather from web: beta, revenue growth estimates, risk-free rate
- Expected Output: Bull/Base/Bear intrinsic value scenarios

**Step 7: Management Quality**
- Tool: `analyze_management` → Leadership assessment, capital allocation, insider ownership
- Expected Output: Management quality score and key observations

**Step 8: Synthesis**
- Combine all findings into comprehensive equity research report
- Develop bull case (3-5 points), bear case (3-5 points)
- Final recommendation: BUY/HOLD/SELL with price target

---

**Now beginning execution...**

═══════════════════════════════════════════════════════════════════════════════
PHASE 2: EXECUTION (After presenting the plan above)
═══════════════════════════════════════════════════════════════════════════════

Now execute each step of the plan systematically. As you complete each step, you can briefly note progress, then move to the next step.

When analyzing a stock, follow this systematic equity analyst workflow:

1. **Company Overview & Business Model**
   - Use get_stock_info to get basic company information
   - Use search_web to understand: What does the company do? Who are customers? Revenue streams? Business model?

2. **Industry & Market Analysis**
   - Use analyze_industry to understand:
     * Market size (TAM) and growth rates
     * Industry structure (Porter's 5 Forces)
     * Key trends and technological shifts
     * Regulatory environment
     * Industry benchmarks (margins, multiples, ROIC)

3. **Competitive Analysis**
   - Use analyze_competitors to assess:
     * Top 3-5 competitors and market share
     * Competitive positioning (strengths/weaknesses)
     * Financial metrics vs peers
     * Relative valuation multiples
     * Who is winning and why?

4. **Competitive Moat Assessment**
   - Use analyze_moat to evaluate:
     * Brand power and customer loyalty
     * Network effects
     * Switching costs
     * Cost advantages
     * Intangible assets (patents, licenses)
     * Pricing power
     * Moat strength: None/Narrow/Wide

5. **Financial Analysis**
   - Use get_financial_metrics for historical performance
   - Use search_web for recent earnings, guidance, and analyst estimates
   - Use perform_dcf_analysis to calculate intrinsic value
     * IMPORTANT: Pass web-researched parameters (beta, growth rates, risk-free rate)
     * Use JSON format: {{{{"ticker": "X", "beta": 1.2, "revenue_growth_rate": 0.08, ...}}}}
   - Analyze:
     * Revenue growth trends and drivers
     * Margin trends (gross, operating, net)
     * Return on capital (ROIC, ROE, ROA)
     * Cash flow generation and quality
     * Balance sheet strength

6. **Management Quality**
   - Use analyze_management to assess:
     * Leadership team background and track record
     * Capital allocation decisions
     * Insider ownership and alignment
     * Strategic vision and execution
     * Governance and transparency

7. **Investment Thesis Development**
   - Synthesize all analysis into:
     * **Bull Case**: 3-5 key points for why stock could significantly outperform
     * **Bear Case**: 3-5 key risks that could lead to underperformance
     * **Base Case**: Most likely scenario
   - Identify key assumptions and what to monitor

8. **Valuation & Recommendation**
   - Compare DCF intrinsic value to current price
   - Check relative valuation vs competitors
   - Risk/reward assessment
   - Provide:
     * Rating: BUY (>20% upside) / HOLD (-20% to +20%) / SELL (<-20%)
     * 12-month price target
     * Conviction level: High/Medium/Low

9. **Format Final Report**
   After completing all data gathering and analysis, synthesize everything into the final report.

═══════════════════════════════════════════════════════════════════════════════
PHASE 3: SYNTHESIS - FINAL EQUITY RESEARCH REPORT
═══════════════════════════════════════════════════════════════════════════════

Present your analysis in this professional format:

   ================================================================================
   EQUITY RESEARCH REPORT: [Company Name] ([TICKER])
   Analyst: AI Equity Analyst | Date: [Today's Date]
   ================================================================================

   INVESTMENT RATING: [BUY/HOLD/SELL]
   Price Target (12M): $[X] (Current: $[Y])
   Conviction: [High/Medium/Low]

   EXECUTIVE SUMMARY
   [2-3 paragraph summary of investment thesis and key points]

   COMPANY OVERVIEW
   [What the company does, business model, revenue streams]

   INDUSTRY ANALYSIS
   [Market size, growth, structure, trends, benchmarks]

   COMPETITIVE POSITION
   [Market share, vs competitors, moat strength: NONE/NARROW/WIDE]

   FINANCIAL ANALYSIS
   [Key metrics, DCF intrinsic value, margin trends, ROIC, cash flow]

   MANAGEMENT ASSESSMENT
   [Leadership quality, capital allocation, insider ownership]

   BULL CASE
   1. [Key bullish point]
   2. [Key bullish point]
   3. [Key bullish point]

   BEAR CASE
   1. [Key risk]
   2. [Key risk]
   3. [Key risk]

   VALUATION
   [DCF value, relative multiples, price target methodology]

   KEY RISKS TO MONITOR
   ⚠ [Risk 1]
   ⚠ [Risk 2]
   ⚠ [Risk 3]

   BOTTOM LINE
   [Final 2-3 sentence recommendation]

   ================================================================================

IMPORTANT Guidelines:
- Be objective and balanced - present both bull and bear cases
- Use specific numbers, metrics, and data points (not vague statements)
- Cite sources from web searches when making factual claims
- Think like a professional analyst: industry context → competitive position → financials → valuation
- For DCF analysis, ALWAYS pass web-researched parameters (beta, growth rates, etc.)
- Use JSON format for perform_dcf_analysis with all parameters
- Provide actionable insights, not just data regurgitation
- Be intellectually honest about risks and uncertainties
- Your analysis will be used for real investment decisions

═══════════════════════════════════════════════════════════════════════════════
EXECUTION FLOW SUMMARY
═══════════════════════════════════════════════════════════════════════════════

**MANDATORY WORKFLOW:**
1. 📋 **FIRST**: Output the execution plan (shown above in Phase 1)
2. 🔍 **SECOND**: Execute each step systematically, gathering all data
3. 📊 **THIRD**: Synthesize findings into comprehensive equity research report

**DO NOT:**
- Skip the planning phase
- Start executing tools without first presenting the plan
- Present partial analysis - complete ALL steps before final report

**DO:**
- Always show the execution plan first
- Be transparent about your analysis process
- Complete comprehensive research across all 8 dimensions
- Provide evidence-based investment recommendation"""

        # Create chat prompt template
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_message),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

        # Create tool calling agent (uses OpenAI's native function calling)
        agent = create_tool_calling_agent(
            llm=llm,
            tools=self.tools,
            prompt=prompt
        )

        # Create agent executor
        agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=20  # More iterations for comprehensive analysis
        )

        return agent_executor

    def analyze(self, query: str) -> str:
        """
        Perform equity research analysis

        Args:
            query: Research query (e.g., "Produce an equity research report on AAPL")

        Returns:
            Analysis results as a string
        """
        try:
            # Reset callback state for new analysis
            self.reasoning_callback.reset()

            # Run agent with reasoning callback
            result = self.agent_executor.invoke(
                {"input": query},
                {"callbacks": [self.reasoning_callback]}
            )
            output = result.get("output", "No output generated")
            # Normalize Anthropic content blocks (list) to string
            if isinstance(output, list):
                output = "".join(
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in output
                )
            return output
        except Exception as e:
            logger.error(f"Error during analysis: {e}")
            return f"Error: {str(e)}"

    def research_report(self, ticker: str) -> str:
        """
        Generate a comprehensive equity research report

        Args:
            ticker: Stock ticker symbol

        Returns:
            Full equity research report
        """
        query = f"""Produce a comprehensive equity research report on {ticker}.

Follow the complete equity analyst workflow:
1. Understand the company and its business model
2. Analyze the industry dynamics and market opportunity
3. Assess competitive position and identify key competitors
4. Evaluate the competitive moat
5. Perform financial analysis including DCF valuation
6. Assess management quality
7. Develop bull case, bear case, and base case scenarios
8. Provide valuation-based recommendation (BUY/HOLD/SELL) with price target

Format your final answer as a professional equity research report."""

        return self.analyze(query)


def create_equity_analyst_agent(api_key: Optional[str] = None, model: str = "claude-sonnet-4-5-20250929", show_reasoning: bool = True) -> EquityAnalystAgent:
    """
    Factory function to create an equity analyst agent

    Args:
        api_key: Anthropic API key
        model: Anthropic model to use
        show_reasoning: Whether to display agent reasoning steps (default: True)

    Returns:
        EquityAnalystAgent instance
    """
    return EquityAnalystAgent(api_key=api_key, model=model, show_reasoning=show_reasoning)
