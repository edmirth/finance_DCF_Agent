"""
Market Analysis Agent

AI agent for analyzing market conditions, sentiment, news, and regime.
Provides comprehensive market overview to inform investment decisions.
"""

import logging
import threading
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tools.market_tools import get_market_tools
from agents.reasoning_callback import StreamingReasoningCallback
from shared.window_memory import WindowConversationMemory

logger = logging.getLogger(__name__)


MARKET_AGENT_PROMPT = """You are a professional Market Analyst. Provide comprehensive, data-rich analysis with specific numbers and context that helps investors make informed decisions.

**OUTPUT RULES — NEVER VIOLATE THESE:**
1. NO ASCII BORDERS — Never output lines like `========`, `--------`, `***`.
2. NO EMOJIS — Use bold text and markdown headers for emphasis instead.
3. NO ALL-CAPS SECTION LABELS — Use `##` and `###` headers only.
4. MANDATORY NARRATIVE PROSE — Every section must contain at least 2–3 sentences of analytical prose. Tables and bullets complement prose; they do not replace it.
5. EVERY DATA POINT NEEDS CONTEXT — Not "VIX is at 18." But "VIX at 18 is below its long-run average of ~20, indicating below-average implied volatility."
6. SPECIFIC NUMBERS IN EVERY CLAIM — Not "Technology is outperforming." But "Technology is up 2.5% today vs. S&P 500's 0.8%."

**TOOLS:**
- get_market_overview: Major indices, breadth, VIX, market regime
- get_sector_rotation: Sector performance and rotation patterns (timeframe: 1D/5D/1M/3M/YTD)
- get_market_news: Latest market-moving news and developments
- classify_market_regime: Detailed regime classification (BULL/BEAR/NEUTRAL, RISK_ON/OFF)
- get_macro_context: Treasury yields, yield curve, Fed funds rate, CPI, GDP
- get_sentiment_score: Composite 0–100 Fear & Greed score (VIX, momentum, breadth, new highs/lows)
- get_historical_context: 52-week range and percentile for VIX, S&P 500, Nasdaq
- screen_stocks: Custom stock screening (P/E, revenue, profitability, debt, growth)
- get_value_stocks: Pre-filtered value stocks (P/E < 15, profitable, large cap)
- get_growth_stocks: Pre-filtered growth stocks (strong revenue, profitable)
- get_dividend_stocks: Pre-filtered dividend-paying stocks

**WHEN TO CALL OPTIONAL TOOLS:**

get_sentiment_score — Call when user asks about sentiment, fear/greed, or during a daily briefing. Lead with it in briefings to set the tone.

get_macro_context — Call when user asks about interest rates, Fed policy, yield curve, inflation, recession signals, or the macro environment. Include in daily briefings.

get_historical_context — Call when user asks how current levels compare to recent history, whether VIX is elevated, or where indices sit in their 52-week range. Include in daily briefings.

**STOCK SCREENING APPROACH:**
When screening for stocks, follow this top-down sequence:
1. get_market_overview → understand regime (BULL/BEAR/RISK_ON/RISK_OFF)
2. get_sector_rotation → identify leading sectors
3. Use appropriate screener (value/growth/dividend/custom)
4. Present results as a table with key metrics
5. Recommend Finance Q&A or Equity Analyst for deep dives on specific names

Industry names use the financial API's classification: "Auto Manufacturers" (includes EVs), "Semiconductors", "Software - Application", "Software - Infrastructure", "Biotechnology", "Pharmaceuticals", "Banks - Regional", "Banks - Diversified", "Oil & Gas E&P", "Aerospace & Defense".

**OUTPUT FORMAT:**
- Open with an executive summary paragraph
- Use ## and ### section headers
- Tables for multi-item comparisons; prose for interpretation
- Bold key insights
- Close with "Investor Takeaways" or "Bottom Line" section
- Every recommendation must be specific: "overweight Technology", "reduce duration" — not vague suggestions"""


class MarketAnalysisAgent:
    """AI agent for comprehensive market analysis."""

    def __init__(self, model: str = "claude-sonnet-4-6", temperature: float = 0.1, show_reasoning: bool = True):
        """
        Args:
            show_reasoning: Print tool-call steps to stdout. Effective in CLI only — the API
                            attaches its own streaming callback and ignores this one.
        """
        self.model = model
        self.temperature = temperature
        self.show_reasoning = show_reasoning

        self.llm = ChatAnthropic(
            model=model,
            temperature=temperature,
            max_retries=3,
            default_request_timeout=60.0,
            max_tokens=8192,
        )

        self.tools = get_market_tools()

        # Memory retains the last 8 turns of conversation history.
        # In the API, agents are cached per session (SESSION_SCOPED_AGENT_TYPES in api_server.py
        # includes "market"), so memory accumulates correctly across requests in the same session.
        # Without a session_id, a fresh agent is created per request and memory is not retained.
        self.memory = WindowConversationMemory(
            k=8,
            memory_key="chat_history",
            return_messages=True,
            output_key="output",
        )

        self.reasoning_callback = StreamingReasoningCallback(verbose=show_reasoning)

        prompt = ChatPromptTemplate.from_messages([
            ("system", MARKET_AGENT_PROMPT),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

        agent = create_tool_calling_agent(llm=self.llm, tools=self.tools, prompt=prompt)

        self.agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=False,  # Avoid double-logging alongside StreamingReasoningCallback
            handle_parsing_errors=True,  # Retry malformed tool calls; max_iterations=15 gives headroom
            max_iterations=15,  # Daily briefing calls ~6 tools; each = 2 iterations (decide + process)
        )

        # Serialises concurrent invocations on the same cached instance (session-scoped agents).
        # AgentExecutor and ConversationBufferWindowMemory are not thread-safe.
        self._invoke_lock = threading.Lock()

    def _invoke(self, input_dict: dict, callbacks: list) -> str:
        """
        Single entry point for agent execution used by both analyze() and api_server.py.

        Acquires a per-instance lock to prevent concurrent invocations corrupting shared
        memory state. Resets reasoning_callback before each call so step counters don't
        accumulate across requests on a cached agent instance.
        """
        with self._invoke_lock:
            self.reasoning_callback.reset()
            payload = dict(input_dict)
            payload.setdefault(
                self.memory.memory_key,
                self.memory.load_memory_variables({}).get(self.memory.memory_key, []),
            )
            result = self.agent_executor.invoke(payload, {"callbacks": callbacks})
            output = result["output"]
            self.memory.save_context({"input": payload.get("input", "")}, {"output": output})
            return output

    def analyze(self, query: str) -> str:
        """Run market analysis based on user query (CLI path)."""
        try:
            return self._invoke({"input": query}, [self.reasoning_callback])
        except Exception as e:
            logger.exception("Market analysis failed for query: %.200s", query)
            return f"Error during market analysis: {str(e)}"


def create_market_agent(model: str = "claude-sonnet-4-6", show_reasoning: bool = True) -> MarketAnalysisAgent:
    return MarketAnalysisAgent(model=model, show_reasoning=show_reasoning)
