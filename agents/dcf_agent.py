"""
LangChain DCF Analysis Agent
"""
from langchain.agents import AgentExecutor, create_react_agent
from langchain_anthropic import ChatAnthropic
from langchain.prompts import PromptTemplate
from langchain.callbacks.base import BaseCallbackHandler
from tools.dcf_tools import get_dcf_tools
from typing import Optional, List
from anthropic import APIError, RateLimitError, AuthenticationError
import os
import re
import logging
import threading

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Valid Anthropic models for DCF analysis
VALID_MODELS = [
    "claude-sonnet-4-5-20250929", "claude-opus-4-6",
    "claude-haiku-4-5-20251001",
]

# Tools referenced in the prompt template (for validation)
REQUIRED_TOOLS = [
    "get_company_context", "get_stock_info", "get_financial_metrics",
    "get_market_parameters", "analyze_competitors", "search_web",
    "perform_dcf_analysis", "perform_multiples_valuation", "get_dcf_comparison",
    "format_dcf_report"
]

# API key format pattern for Anthropic
ANTHROPIC_API_KEY_PATTERN = re.compile(r'^sk-ant-[a-zA-Z0-9_-]{20,}$')

# Bug #13 Fix: Class-level tool cache with thread safety
_tools_cache = None
_tools_cache_lock = threading.Lock()


def _get_cached_tools():
    """Get tools from cache or create new ones (thread-safe)."""
    global _tools_cache
    with _tools_cache_lock:
        if _tools_cache is None:
            _tools_cache = get_dcf_tools()
        return _tools_cache


def _clear_tools_cache():
    """Clear the tools cache (useful for testing)."""
    global _tools_cache
    with _tools_cache_lock:
        _tools_cache = None


class DCFAnalysisAgent:
    """AI Agent for performing DCF analysis on stocks"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-5-20250929",
        callbacks: Optional[List[BaseCallbackHandler]] = None,
        verbose: bool = True,
        max_execution_time: Optional[int] = 300  # 5 minutes default timeout
    ):
        """
        Initialize the DCF Analysis Agent

        Args:
            api_key: Anthropic API key (if not provided, will use ANTHROPIC_API_KEY env var)
            model: Anthropic model to use (default: claude-sonnet-4-5-20250929)
            callbacks: Optional list of callback handlers for streaming output
            verbose: Whether to enable verbose logging (default: True)
            max_execution_time: Maximum execution time in seconds (default: 300)
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("Anthropic API key not found. Set ANTHROPIC_API_KEY environment variable.")

        # Validate API key format
        if not ANTHROPIC_API_KEY_PATTERN.match(self.api_key):
            logger.warning(
                "API key does not match expected Anthropic format (sk-ant-...). "
                "Proceeding anyway, but authentication may fail."
            )

        # Bug #3 Fix: Validate model name
        if model not in VALID_MODELS:
            logger.warning(
                f"Model '{model}' not in known valid models: {VALID_MODELS}. "
                "Proceeding anyway, but API call may fail."
            )

        self.model = model
        self.callbacks = callbacks
        self.verbose = verbose
        self.max_execution_time = max_execution_time
        self.tools = _get_cached_tools()  # Bug #13 Fix: Use cached tools

        # Bug #4 Fix: Validate that all required tools exist
        self._validate_tools()

        self.agent_executor = self._create_agent()

    def _validate_tools(self) -> None:
        """Validate that all tools referenced in the prompt exist."""
        tool_names = {tool.name for tool in self.tools}
        missing_tools = set(REQUIRED_TOOLS) - tool_names

        if missing_tools:
            logger.warning(
                f"Tools referenced in prompt but not found: {missing_tools}. "
                "Agent may not work as expected."
            )

        extra_tools = tool_names - set(REQUIRED_TOOLS)
        if extra_tools:
            logger.info(f"Additional tools available: {extra_tools}")

    def _create_agent(self) -> AgentExecutor:
        """Create the LangChain agent with tools"""

        # Initialize LLM with configured model
        llm = ChatAnthropic(
            model=self.model,
            temperature=0,
            anthropic_api_key=self.api_key,
            callbacks=self.callbacks,  # Bug #1 Fix: Pass callbacks to LLM
            max_retries=3,  # Retry failed API calls
            default_request_timeout=60.0,  # Request timeout in seconds
            max_tokens=8192,  # Max output tokens
        )

        # Create agent prompt with Financial Chain-of-Thought (CoT) framework
        template = """You are a professional financial analyst AI agent specialized in performing institutional-grade DCF (Discounted Cash Flow) analysis using Financial Chain-of-Thought reasoning.

Your DCF model uses the proper Unlevered Free Cash Flow (UFCF) methodology:
UFCF = NOPAT + D&A - CapEx - ΔWorking Capital
WACC = (E/V × Re) + (D/V × Rd × (1 - Tax Rate))

You have access to the following tools:

{tools}

Tool Names: {tool_names}

================================================================================
FINANCIAL CHAIN-OF-THOUGHT (CoT) FRAMEWORK
================================================================================

You MUST follow this 3-phase structured reasoning process:

## PHASE 1: DATA-COT (Data Collection & Validation)
--------------------------------------------------------------------------------
Objective: Gather comprehensive data before any analysis

Tool Sequence:
1. get_company_context - Understand business model, recent news, catalysts
2. get_stock_info - Basic company information
3. get_financial_metrics - Historical financials and operating ratios
4. get_market_parameters - Beta, risk-free rate, growth estimates (CRITICAL for DCF!)
5. analyze_competitors - Competitive positioning and peer comparison
6. search_web - Industry outlook, competitive dynamics (qualitative research only)

After EACH tool, reflect on data quality:
- Data Reflection: "What did I learn? Is the data reliable? Any gaps?"
- If data is missing or questionable, note it for later adjustment

**IMPORTANT**: Use get_market_parameters for DCF assumptions (beta, risk-free rate, growth).
Use search_web ONLY for qualitative research (industry trends, competitive dynamics, news).

## PHASE 2: CONCEPT-COT (Financial Analysis)
--------------------------------------------------------------------------------
Objective: Synthesize data into analytical insights

Structure your analysis around these concepts:

**Growth Analysis (CRITICAL - Use Forward-Looking Estimates):**
- SEARCH for analyst consensus revenue estimates for next 2 years (DO NOT use historical CAGR)
- Determine industry average growth rate for fade target (Years 3-5)
- Key growth drivers and sustainability assessment

**Profitability Analysis:**
- EBIT margin trends and comparison to peers
- Operating leverage and scalability
- Path to margin improvement or deterioration

**Capital Efficiency:**
- ROIC vs WACC (value creation/destruction)
- CapEx intensity and reinvestment needs
- Working capital efficiency (as % of revenue)

**Risk Profile Assessment:**
- Beta appropriateness for this company
- Business model stability
- Financial leverage and liquidity

Concept Reflection: "What are the key value drivers? What risks could materially impact valuation?"

## PHASE 3: THESIS-COT (Valuation & Recommendation)
--------------------------------------------------------------------------------
Objective: Build investment thesis with justified assumptions

Tool Sequence for Phase 3:
1. perform_dcf_analysis - With parameters from get_market_parameters
2. perform_multiples_valuation - P/E, EV/EBITDA, P/S, P/B peer comparison (TRIANGULATION!)
3. get_dcf_comparison - Cross-validate with FMP DCF values
4. format_dcf_report - Generate professional structured output

**VALUATION TRIANGULATION (Best Practice):**
- DCF gives intrinsic value based on cash flows
- Multiples give relative value based on peer comparison
- Use BOTH to increase confidence in valuation
- Large divergence between DCF and Multiples warrants investigation

**DCF Assumption Determination (FORWARD-LOOKING):**
Use values from get_market_parameters tool for:
- near_term_growth_rate: [X%] - Analyst consensus forecasts (Years 1-2)
- long_term_growth_rate: [X%] - Industry average for Years 3-5 fade target
- terminal_growth_rate: [X%] - GDP + inflation (~2.5%)
- beta: [X] - From get_market_parameters
- risk_free_rate: [X%] - Current 10-year Treasury yield from get_market_parameters

Set manually based on analysis:
- market_risk_premium: [X%] - 5-5.5% for mega-cap quality, 6-7% for others

**IMPORTANT: DO NOT use historical CAGR for growth projections!**
The get_market_parameters tool fetches analyst consensus growth estimates automatically.

**Scenario Construction:**
- Bull Case: What must go right? Probability assessment
- Base Case: Most likely outcome
- Bear Case: What could go wrong? Probability assessment

**Investment Recommendation:**
- Clear Buy/Hold/Sell with conviction level (High/Medium/Low)
- Upside/downside vs current price
- Key catalysts to watch
- Time horizon considerations

**Final Report:**
Use format_dcf_report to generate a professional, institutional-grade report with all findings.

================================================================================
RISK ASSESSMENT FRAMEWORK
================================================================================

You MUST assess and rate risks in your final analysis:

**Industry Risks:** (Rate: Low/Medium/High)
- Regulatory Risk: Government/policy impacts
- Competitive Risk: Market share threats
- Disruption Risk: Technology/business model threats
- Cyclicality Risk: Economic sensitivity

**Company Risks:** (Rate: Low/Medium/High)
- Execution Risk: Can management deliver on plans?
- Management Risk: Quality and alignment
- Balance Sheet Risk: Leverage and liquidity concerns
- Concentration Risk: Customer/product/geographic

**Valuation Risks:** (Rate: Low/Medium/High)
- Assumption Sensitivity: How much do results change with small input changes?
- Growth Sustainability: Can current growth rates persist?
- Multiple Compression: Risk of valuation de-rating

================================================================================
TOOL USAGE GUIDELINES
================================================================================

**get_company_context** (USE FIRST):
- Input: Just the ticker symbol (e.g., AAPL)
- Purpose: Business model, recent news, upcoming catalysts, key risks

**get_stock_info**:
- Input: Just the ticker symbol (e.g., AAPL)
- Purpose: Sector, industry, market cap, current price

**get_financial_metrics**:
- Input: Just the ticker symbol (e.g., AAPL)
- Provides: Revenue, EBIT, FCF, CapEx, D&A, Working Capital, Tax rate, Operating ratios

**get_market_parameters** (CRITICAL FOR DCF ASSUMPTIONS):
- Input: {{"ticker": "AAPL", "company_name": "Apple Inc", "industry": "Consumer Electronics"}}
- Purpose: Fetch validated DCF assumptions via FRED API and Tavily search
- Returns: beta, risk_free_rate, near_term_growth_rate, industry_growth_rate
- USE THIS instead of search_web for DCF numeric parameters!
- All values are validated and ready to pass to perform_dcf_analysis

**analyze_competitors**:
- Input: {{"company": "Company Name", "ticker": "TICK", "industry": "Industry Name"}}
- Purpose: Peer comparison, market share, competitive positioning

**search_web** (QUALITATIVE RESEARCH ONLY):
- Input: Your search query as a string
- Use for: Industry outlook, competitive dynamics, strategic news, management quality
- DO NOT use for: Beta, risk-free rate, growth estimates (use get_market_parameters instead)

**perform_dcf_analysis**:
- REQUIRED from get_market_parameters: near_term_growth_rate, beta, risk_free_rate
- Set manually: terminal_growth_rate (2.5%), market_risk_premium (5.5-7%)
- Recommended: long_term_growth_rate (from get_market_parameters industry_growth_rate)
- Auto-calculated: ebit_margin, tax_rate, capex_to_revenue, depreciation_to_revenue, nwc_to_revenue, cost_of_debt
- AUTO-METHODOLOGY: Automatically selects Levered DCF (FCFE) when D/E > 1.0
- PASS EXPLICITLY to ensure correct WACC: current_price (from get_stock_info), shares_outstanding (from get_financial_metrics, in millions)

**perform_multiples_valuation** (ALTERNATIVE/COMPLEMENT TO DCF):
- Input: {{"ticker": "AAPL", "peer_tickers": "MSFT,GOOGL,META"}} (peer_tickers optional)
- Purpose: Valuation using P/E, EV/EBITDA, P/S, P/B multiples compared to peers/industry
- Returns: Company multiples, peer averages, implied fair values, weighted average valuation
- WHEN TO USE MULTIPLES vs DCF:
  * Multiples BETTER for: Banks/financials, REITs, mature stable companies, cyclical businesses
  * DCF BETTER for: High-growth companies, predictable cash flow companies
  * USE BOTH for triangulation (cross-validation approach)
- AUTOMATICALLY fetches peer multiples via Tavily search
- Weighted methodology: P/E (30%), EV/EBITDA (35%), P/S (25%), P/B (10%)

**get_dcf_comparison** (USE AFTER perform_dcf_analysis):
- Input: Just the ticker symbol (e.g., AAPL)
- Purpose: Cross-validate your DCF with FMP's DCF values (standard and levered)
- Returns: FMP Standard DCF, FMP Levered DCF, and divergence analysis
- Note: Use as sanity check. If divergence >20%, investigate assumption differences.

**format_dcf_report** (USE AS FINAL STEP):
- Input: All DCF results, assumptions, and analysis narratives
- Purpose: Generate professional, institutional-grade formatted report
- Returns: Structured report with executive summary, scenarios, assumptions, and thesis
- ALWAYS use this as the final step to present results professionally

**CRITICAL - Growth Rate Selection (Forward-Looking):**
- near_term_growth_rate: Years 1-2 from get_market_parameters (analyst consensus)
- long_term_growth_rate: Years 3-5 fade target from get_market_parameters (industry average)
- terminal_growth_rate: GDP + inflation (~2.5%) - set manually

DO NOT use historical CAGR! The get_market_parameters tool fetches analyst consensus automatically.

**AUTO-LEVERED DCF Selection:**
- If D/E ratio > 1.0, system automatically uses Levered DCF (FCFE method)
- Levered DCF discounts FCFE at Cost of Equity (not WACC)
- More appropriate for highly leveraged companies (financials, auto, REITs)

**Market Risk Premium Selection (set manually based on company quality):**
- 5.0-5.5%: Mega-cap quality stocks (AAPL, MSFT, GOOGL) with strong moats
- 5.5-6.5%: Large-cap established companies
- 6.5-7.5%: Mid-cap or moderate business risk
- 7.5%+: High-growth, unprofitable, or high-risk companies

**Workflow Example:**

1. Call get_market_parameters with ticker, company_name, industry
2. Use returned values (beta, risk_free_rate, near_term_growth_rate, industry_growth_rate)
3. Set terminal_growth_rate (2.5%) and market_risk_premium (based on quality) manually
4. Call perform_dcf_analysis with all parameters
5. Call get_dcf_comparison for cross-validation
6. Call format_dcf_report with all results

Example for mega-cap quality stock (values from get_market_parameters + stock info):
Action Input: {{"ticker": "AAPL", "near_term_growth_rate": 0.05, "long_term_growth_rate": 0.04, "terminal_growth_rate": 0.025, "beta": 1.10, "risk_free_rate": 0.045, "market_risk_premium": 0.055, "current_price": 227.52, "shares_outstanding": 15441.0}}

Example for high-growth stock (values from get_market_parameters + stock info):
Action Input: {{"ticker": "PLTR", "near_term_growth_rate": 0.25, "long_term_growth_rate": 0.12, "terminal_growth_rate": 0.025, "beta": 1.55, "risk_free_rate": 0.045, "market_risk_premium": 0.07, "current_price": 85.40, "shares_outstanding": 2100.0}}

================================================================================
CHART PLACEHOLDERS
================================================================================

When a tool output includes [CHART_INSTRUCTION: Place {{{{CHART:id}}}} ...], follow the instruction.
Place {{{{CHART:chart_id}}}} on its own line at the relevant point in your response.
Do NOT reproduce ---CHART_DATA--- blocks in your response.

================================================================================
OUTPUT FORMAT
================================================================================

Use the following format EXACTLY. Never deviate from it:

Question: the input question you must answer

Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action (JSON inline — NEVER wrap in code fences)
Observation: the result of the action

CRITICAL FORMAT RULES (violations cause tool calls to fail):
- Write "Action:" and "Action Input:" exactly as shown — no bold (**), no markdown
- For tools that take only a ticker: write the ticker directly, e.g.:  Action Input: AAPL
- For tools that take multiple fields: write inline JSON without code fences, e.g.:
    Action Input: {{"ticker": "AAPL", "company_name": "Apple Inc", "industry": "Technology"}}
  NEVER wrap Action Input in ```json ... ``` code fences
- Call one tool at a time, wait for the real Observation, then decide the next step

Data Reflection: [After each data tool, reflect on data quality and insights]

... (this Thought/Action/Action Input/Observation can repeat N times)

Concept Reflection: [After completing Phase 2, synthesize key insights]

Thought: I now know the final answer

ABSOLUTE OUTPUT RULES FOR FINAL ANSWER — NEVER VIOLATE:
1. NO ASCII BORDERS — Never output lines like `========`, `--------`. These appear as raw garbage.
2. NO EMOJIS — Do not use any emoji characters anywhere in the Final Answer.
3. MANDATORY PROSE IN EVERY SECTION — Every major section must contain at least 2–3 sentences of analytical narrative. Tables and bullet points complement prose; they do not replace it.
4. EVERY CLAIM NEEDS A SPECIFIC NUMBER — Do not write "margins are improving." Write "EBIT margin expanded from 18% in FY2022 to 24% in FY2024."
5. USE ONLY ## AND ### HEADERS — No all-caps section labels as plain text.

Final Answer: [A complete, professional markdown report that embeds the full output from format_dcf_report, then adds a brief 2–3 sentence analyst commentary paragraph at the end synthesizing the single most important takeaway and the top risk to the investment case.]

Begin!

Question: {input}
Thought: {agent_scratchpad}"""

        prompt = PromptTemplate(
            template=template,
            input_variables=["input", "agent_scratchpad", "tools", "tool_names"]
        )

        # Create agent
        agent = create_react_agent(
            llm=llm,
            tools=self.tools,
            prompt=prompt
        )

        # Create agent executor
        # max_iterations increased to 20 for Financial CoT with 10 required tool calls
        agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=self.verbose,  # Bug #1 Fix: Use configurable verbose
            handle_parsing_errors=True,
            max_iterations=20,
            max_execution_time=self.max_execution_time,  # Bug #6 Fix: Add timeout
            callbacks=self.callbacks,  # Bug #1 Fix: Pass callbacks to executor
            return_intermediate_steps=True,  # Required for recovery fallback in analyze()
        )

        return agent_executor

    def analyze(self, query: str, callbacks: Optional[List[BaseCallbackHandler]] = None) -> str:
        """
        Analyze a stock using the agent

        Args:
            query: User query (e.g., "Perform DCF analysis on AAPL")
            callbacks: Optional runtime callbacks (overrides instance callbacks)

        Returns:
            Analysis results as a string
        """
        # Bug #7 Fix: Specific exception handling for common errors
        try:
            invoke_config = {"input": query}
            if callbacks:
                invoke_config["callbacks"] = callbacks

            result = self.agent_executor.invoke(invoke_config)

            # Ensure output is a string — Anthropic returns list of content blocks
            output = result.get("output", "")
            if isinstance(output, list):
                output = "".join(
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in output
                )
            elif not isinstance(output, str):
                output = str(output)

            # ReAct agents return result["output"] = Final Answer text only.
            # When the agent delegates presentation to format_dcf_report, it writes
            # a short Final Answer ("The report has been formatted above") while the
            # full report sits in intermediate_steps as the tool observation.
            # Recover it here when the output is suspiciously short.
            if len(output.strip()) < 200:
                steps = result.get("intermediate_steps", [])
                # First preference: format_dcf_report observation
                for action, observation in reversed(steps):
                    if (
                        getattr(action, "tool", "") == "format_dcf_report"
                        and len(str(observation)) > 200
                    ):
                        output = str(observation)
                        logger.debug("Recovered full report from format_dcf_report observation")
                        break
                # Fallback: use the longest observation overall (likely the report)
                if len(output.strip()) < 200 and steps:
                    longest = max(steps, key=lambda s: len(str(s[1])))
                    if len(str(longest[1])) > 1000:
                        output = str(longest[1])
                        logger.debug("Recovered report from longest intermediate observation")

            return output if output.strip() else "No output generated"

        except AuthenticationError as e:
            error_msg = f"Authentication failed. Please check your Anthropic API key. Details: {e}"
            logger.error(error_msg)
            return f"Error: {error_msg}"

        except RateLimitError as e:
            error_msg = f"Rate limit exceeded. Please wait and try again. Details: {e}"
            logger.error(error_msg)
            return f"Error: {error_msg}"

        except APIError as e:
            error_msg = f"Anthropic API error: {e}"
            logger.error(error_msg)
            return f"Error: {error_msg}"

        except TimeoutError as e:
            error_msg = f"Analysis timed out after {self.max_execution_time} seconds. Try a simpler query."
            logger.error(error_msg)
            return f"Error: {error_msg}"

        except ValueError as e:
            error_msg = f"Invalid input or configuration: {e}"
            logger.error(error_msg)
            return f"Error: {error_msg}"

        except Exception as e:
            # Log full exception for debugging but return cleaner message
            logger.exception(f"Unexpected error during analysis: {e}")
            return f"Error: An unexpected error occurred during analysis. Please check logs for details. ({type(e).__name__}: {e})"

    def quick_dcf(self, ticker: str) -> str:
        """
        Perform a quick DCF analysis on a ticker

        Args:
            ticker: Stock ticker symbol

        Returns:
            DCF analysis results
        """
        # Bug #8 Fix: Updated query to use forward-looking approach consistent with prompt
        query = (
            f"Perform a complete DCF analysis on {ticker}. "
            "Follow the Financial Chain-of-Thought framework: "
            "1) Use get_company_context and get_stock_info for business overview, "
            "2) Use get_financial_metrics for historical data, "
            "3) Use get_market_parameters to fetch forward-looking analyst consensus estimates "
            "(DO NOT use historical CAGR for growth projections), "
            "4) Perform DCF analysis with the fetched parameters, "
            "5) Use perform_multiples_valuation for triangulation (DCF + Multiples cross-validation), "
            "6) Use format_dcf_report to generate the final professional report."
        )
        return self.analyze(query)

    def multiples_valuation(self, ticker: str, peer_tickers: str = "") -> str:
        """
        Perform a multiples-based valuation on a ticker

        Args:
            ticker: Stock ticker symbol
            peer_tickers: Comma-separated peer tickers (optional)

        Returns:
            Multiples valuation results
        """
        peer_str = f" using peers: {peer_tickers}" if peer_tickers else ""
        query = (
            f"Perform a multiples-based valuation on {ticker}{peer_str}. "
            "Use the perform_multiples_valuation tool to calculate P/E, EV/EBITDA, P/S, and P/B "
            "based valuations compared to peer/industry averages. "
            "Provide a clear recommendation based on whether the stock is overvalued or undervalued."
        )
        return self.analyze(query)

    # Bug #15 Fix: Context manager support for resource management
    def __enter__(self):
        """Enter context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager and cleanup resources."""
        self.close()
        return False  # Don't suppress exceptions

    def close(self) -> None:
        """
        Clean up resources held by the agent.

        Call this when done using the agent to ensure proper cleanup.
        """
        # Clear instance references
        self.agent_executor = None
        self.tools = None
        self.callbacks = None
        logger.debug("DCFAnalysisAgent resources cleaned up")


def create_dcf_agent(
    api_key: Optional[str] = None,
    model: str = "claude-sonnet-4-5-20250929",
    callbacks: Optional[List[BaseCallbackHandler]] = None,
    verbose: bool = True,
    max_execution_time: Optional[int] = 300
) -> DCFAnalysisAgent:
    """
    Factory function to create a DCF analysis agent

    Args:
        api_key: Anthropic API key (uses ANTHROPIC_API_KEY env var if not provided)
        model: Anthropic model to use (default: claude-sonnet-4-5-20250929)
        callbacks: Optional list of callback handlers for streaming/logging
        verbose: Whether to enable verbose agent output (default: True)
        max_execution_time: Maximum execution time in seconds (default: 300)

    Returns:
        DCFAnalysisAgent instance
    """
    return DCFAnalysisAgent(
        api_key=api_key,
        model=model,
        callbacks=callbacks,
        verbose=verbose,
        max_execution_time=max_execution_time
    )
