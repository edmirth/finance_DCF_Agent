"""
Finance Q&A Agent

An interactive, conversational agent for quick financial Q&A that:
- Answers questions about specific financial data
- Performs quick calculations
- Explains recent news and reports
- Provides proactive suggestions on what to analyze next
- Maintains conversation context/memory
- Enables deep-dive "rabbit hole" exploration
- Compares companies and benchmarks against market
"""

import os
import re
import logging
from typing import Optional, Dict

# Tags that must never appear in user-facing output.
# <thinking> blocks are internal reasoning and should be removed entirely.
# <reflection> tags are just wrappers — keep their content but drop the tags.
# </parameter>, </invoke> etc. are raw Anthropic tool-call XML that can leak
# when the model mixes tool-call syntax into plain-text output.
_THINKING_RE = re.compile(r'<thinking>.*?</thinking>', re.DOTALL | re.IGNORECASE)
_WRAPPER_TAGS_RE = re.compile(
    r'</?(?:reflection|parameter|invoke|function_calls|function|tool_use'
    r'|tool_result|antml:[a-z_]+)[^>]*>',
    re.IGNORECASE
)


def _strip_internal_tags(text: str) -> str:
    """Remove internal reasoning/tool-call XML tags from agent output.

    - Strips <thinking>…</thinking> blocks entirely (internal chain-of-thought).
    - Strips <reflection>, </reflection> wrapper tags but keeps their content.
    - Strips stray tool-call tags: </parameter>, </invoke>, <function_calls>, etc.
    """
    text = _THINKING_RE.sub('', text)
    text = _WRAPPER_TAGS_RE.sub('', text)
    # Collapse runs of blank lines that stripping may leave behind
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_anthropic import ChatAnthropic
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder

from tools.research_assistant_tools import get_research_assistant_tools
from agents.reasoning_callback import StreamingReasoningCallback
from shared.ticker_utils import extract_ticker as _extract_ticker_shared
from shared.window_memory import WindowConversationMemory

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FinanceQAAgent:
    """Interactive Finance Q&A agent with memory and proactive suggestions"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-5-20250929",
        show_reasoning: bool = True,
        project_id: Optional[str] = None,
        db_session_factory=None,
    ):
        """
        Initialize the Finance Q&A Agent

        Args:
            api_key: Anthropic API key (or uses ANTHROPIC_API_KEY env var)
            model: LLM model to use (default: claude-sonnet-4-5-20250929)
            show_reasoning: Whether to show agent reasoning steps (default: True)
            project_id: Optional project UUID — injected into the prompt so the agent
                knows which project to use with load_project_document
            db_session_factory: Optional synchronous SQLAlchemy session factory for
                LoadProjectDocumentTool to query uploaded project documents
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("Anthropic API key is required")

        self.model_name = model
        self.show_reasoning = show_reasoning
        self.project_id = project_id
        self.db_session_factory = db_session_factory

        # Initialize LLM for conversational research
        self.llm_base = ChatAnthropic(
            temperature=0,  # Deterministic reasoning (like DCF and Analyst agents)
            model=model,
            anthropic_api_key=self.api_key,
            streaming=True,  # Enable token-by-token streaming
            max_retries=3,  # Retry failed API calls
            default_request_timeout=60.0,  # Request timeout in seconds
            max_tokens=4096,  # Max output tokens
        )

        # No stop-sequence hack needed for Anthropic models
        self.llm = self.llm_base

        # Full tool suite: research + equity analyst + earnings + stock + document tools.
        # Deduplicate by name — research tools take precedence for any shared tools (e.g. SEC).
        from tools.document_tools import get_document_tools
        from tools.stock_tools import get_stock_tools
        from tools.equity_analyst_tools import get_equity_analyst_tools
        from tools.earnings_tools import get_earnings_tools

        _tool_map: dict = {}
        # Load in priority order: research first, then analyst, earnings, stock.
        # Later sources only fill gaps — they never overwrite earlier entries.
        for tool in (
            get_research_assistant_tools()
            + get_document_tools(db_session_factory=db_session_factory)
            + get_equity_analyst_tools()
            + get_earnings_tools()
            + get_stock_tools()
        ):
            if tool.name not in _tool_map:
                _tool_map[tool.name] = tool
        self.tools = list(_tool_map.values())

        # Keep a lightweight local window of recent turns. We inject this
        # directly as `chat_history` on each invoke instead of relying on
        # LangChain's deprecated memory abstractions.
        self.memory = WindowConversationMemory(
            k=10,  # Keep last 10 conversation turns
            memory_key="chat_history",
            return_messages=True,
            output_key="output",
        )

        # Initialize reasoning callback
        self.reasoning_callback = StreamingReasoningCallback(verbose=show_reasoning)

        # Create the agent with error handling
        try:
            self.agent_executor = self._create_agent()
        except Exception as e:
            logger.error(f"Failed to create agent executor: {e}")
            raise RuntimeError(
                f"Failed to initialize Finance Q&A agent: {str(e)}. "
                "Please check your Anthropic API key and model availability."
            ) from e

        # Track context
        self.current_ticker = None
        self.conversation_count = 0

        logger.info(f"Finance Q&A Agent initialized with model: {model}")
        logger.info(f"Available tools: {[tool.name for tool in self.tools]}")
        logger.info(f"Reasoning display: {'enabled' if show_reasoning else 'disabled'}")

    def _create_agent(self) -> AgentExecutor:
        """Create the conversational agent with memory using structured chat pattern with planning"""

        # Create prompt with system message and chat history support
        from datetime import datetime
        current_date = datetime.now().strftime("%B %d, %Y")
        current_year = datetime.now().year

        # Inject project_id hint when available
        project_hint = ""
        if self.project_id:
            project_hint = f"\n**ACTIVE PROJECT ID: {self.project_id}** — Use this value as `project_id` when calling `load_project_document`.\n"

        # Build the system message in parts to avoid f-string conflicts with template variables
        intro = f"""You are a personal equity analyst working alongside investors — retail investors and professional analysts alike. Your job is to help them think through investment decisions, not to generate reports they passively read.{project_hint}

**TODAY'S DATE: {current_date}**
**CURRENT YEAR: {current_year}**

---

## HOW YOU WORK

**When a ticker is mentioned for the first time in a conversation:**

1. Call `get_stock_info` and `get_financial_metrics` immediately to ground yourself in the facts.
2. Respond with a brief, 4–6 sentence snapshot: current price, one key financial metric (revenue or earnings trend), one notable risk or opportunity, and one valuation data point if available.
3. End with a single open question: "What are you trying to figure out — valuation, competitive position, earnings quality, something else?"

Do NOT generate a full report unprompted. The user will tell you where they want to go.

**For follow-up questions:**

- Pull only the tools needed for that specific question. Don't re-run everything.
- Give focused, direct answers — 2–4 sentences plus supporting data.
- When citing management commentary or SEC filings, always include the source: who said it, when, and in what context. Show the actual quote when available.
- If you have low confidence on something, say so explicitly rather than hedging with vague language.

**When the user forms a thesis, challenge it:**

If a user says "I'm bullish on margins," find the data point that puts pressure on that view. Show them both sides. A good analyst doesn't just confirm — they stress-test.

---

## YOUR TOOLS

**Financial data:**
- `get_stock_info` — price, market cap, sector, basic company context
- `get_financial_metrics` — revenue, margins, FCF, growth rates, debt
- `get_quick_data` — fast lookup for specific metrics
- `get_revenue_segments` — revenue breakdown by business segment

**Earnings & analyst views:**
- `get_quarterly_earnings` — quarterly revenue, EPS, margins trend (4–8 quarters)
- `get_earnings_surprises` — beat/miss history vs. analyst consensus
- `get_earnings_call_insights` — verbatim management quotes and guidance from earnings transcripts. USE THIS when user asks what management said about anything.
- `get_analyst_estimates` — forward EPS and revenue consensus
- `get_price_targets` — analyst price targets and range
- `get_analyst_ratings` — buy/hold/sell distribution

**Competitive & qualitative:**
- `analyze_industry` — industry size, trends, growth dynamics
- `analyze_competitors` — competitive positioning vs. peers
- `analyze_moat` — competitive advantage assessment
- `analyze_management` — management quality and capital allocation track record
- `perform_multiples_valuation` — relative valuation via P/E, EV/EBITDA, P/S vs. sector peers

**SEC primary source:**
- `get_sec_filings` — list recent 10-K/10-Q/8-K filings
- `analyze_sec_filing` — structured summary of MD&A, risk factors, guidance, business overview
- `fetch_and_cache_filing` + `grep_filing` + `read_file_section` — when the user wants exact quotes or specific passages from a filing

**Company comparison:**
- `compare_companies` — two-company side-by-side
- `compare_multiple_companies` — 2–8 companies on revenue, market cap, FCF margin, or growth

**Web search:**
- `search_web` — current events, recent news, analyst commentary not in structured data

---

## CITATION RULES — NON-NEGOTIABLE

When you use `get_earnings_call_insights` or SEC filing tools and find a relevant quote:

- Show the actual quote in a blockquote, attributed to the speaker, role, and date.
- Do not paraphrase when you have the primary source. Paraphrasing loses the nuance.
- Example format:
  > "Data center demand remains strong heading into next year." — Jensen Huang, CEO, Q4 2024 Earnings Call

This is what makes your analysis trustworthy versus a generic AI chat response.

---

## TEMPORAL AWARENESS

- Public companies report quarterly results 45–60 days after quarter end.
- Use `get_date_context` to determine what data is currently available before citing "recent" figures.
- When a user says "last year" or "recently," resolve the actual date range before pulling data.

---

## CHART CAPABILITIES

| User asks for... | Tool | Output |
|---|---|---|
| Metric history for one company | `get_quick_data` | Bar + line chart |
| Revenue by segment | `get_revenue_segments` | Pie chart |
| Two-company comparison | `compare_companies` | Multi-line chart |
| N-company comparison | `compare_multiple_companies` | Bar or multi-line chart |

Never say you can't produce charts. Always call the appropriate tool.

---

## OUTPUT RULES — NEVER VIOLATE

1. No emojis.
2. No ASCII borders (`========`, `--------`).
3. No all-caps section labels — use `##` markdown headers only.
4. Every number needs context: not "Revenue: $96B" but "Revenue of $96B, up 19% year-over-year."
5. Keep responses focused. If a question has a 3-sentence answer, give 3 sentences. Don't pad.
6. When citing primary sources (earnings calls, SEC filings), quote directly — don't summarize away the specificity.

---

## DOCUMENT READING (SEC filings and uploaded documents)

RULE: When a user asks what a document *says*, fetch and read it first. Do not answer from memory.

For SEC filings:
1. `fetch_and_cache_filing(ticker, filing_type)` → get file path
2. `grep_filing(pattern, file_path)` — search for specific topics
3. `read_file_section(file_path, start_marker, end_marker)` — read a named section verbatim
4. `follow_reference(file_path, reference)` — chase cross-references like "See Note 12"

For uploaded project documents: `load_project_document(project_id, filename)` → then same tools."""

        # Tool calling agent doesn't need explicit JSON format instructions
        # Anthropic handles function calling natively
        _chart_instructions = (
            "\n\n**CHART PLACEHOLDERS:**\n"
            "Some tool outputs include [CHART_INSTRUCTION: Place {{{{CHART:id}}}} ...].\n"
            "Follow the instruction exactly: place {{{{CHART:chart_id}}}} on its own line at the exact point where the chart is relevant.\n"
            "Do NOT reproduce ---CHART_DATA--- blocks or [CHART_INSTRUCTION] text in your response. Only use the placeholder."
        )
        system_message = intro + _chart_instructions

        # Create tool calling prompt template
        # This uses Anthropic's native tool calling for reliable tool execution
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_message),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

        # Create tool calling agent (uses Anthropic's native tool calling)
        agent = create_tool_calling_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=prompt
        )

        # Create agent executor without LangChain memory integration.
        # We inject `chat_history` manually on each call and persist the turn
        # into self.memory after a successful response.
        agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=15,  # Increased to allow for planning + execution
            return_intermediate_steps=True,  # Capture the plan
            max_execution_time=300  # 5 minute timeout to prevent indefinite hangs
        )

        return agent_executor

    def _extract_ticker(self, message: str) -> Optional[str]:
        """Delegate to shared.ticker_utils.extract_ticker."""
        return _extract_ticker_shared(message)

    def chat(self, user_message: str) -> str:
        """
        Have a conversation with the research assistant

        Args:
            user_message: User's question or request

        Returns:
            Assistant's response with analysis and suggestions
        """
        try:
            self.conversation_count += 1

            # Extract ticker with improved logic
            extracted_ticker = self._extract_ticker(user_message)
            if extracted_ticker:
                self.current_ticker = extracted_ticker

            logger.info(f"\n{'='*80}")
            logger.info(f"Conversation #{self.conversation_count}")
            if self.current_ticker:
                logger.info(f"Current focus: {self.current_ticker}")
            logger.info(f"{'='*80}\n")

            # Reset callback state for new conversation turn
            self.reasoning_callback.reset()

            # Run the agent with reasoning callback
            chat_history = self.memory.load_memory_variables({}).get(self.memory.memory_key, [])
            result = self.agent_executor.invoke(
                {"input": user_message, self.memory.memory_key: chat_history},
                {"callbacks": [self.reasoning_callback]}
            )

            # Safely extract output with fallback
            if isinstance(result, dict) and "output" in result:
                output = result["output"]
            elif isinstance(result, str):
                output = result
            else:
                logger.warning(f"Unexpected result format: {type(result)}")
                output = result

            # Normalize Anthropic content blocks (list) to string
            if isinstance(output, list):
                output = "".join(
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in output
                )
            elif not isinstance(output, str):
                output = str(output) if output else "I couldn't generate a response. Please try again."

            # Strip any internal reasoning/tool-call XML tags that leaked into output
            output = _strip_internal_tags(output)
            self.memory.save_context({"input": user_message}, {"output": output})

            return output

        except Exception as e:
            logger.error(f"Error in conversation: {str(e)}")
            return f"I encountered an error: {str(e)}\n\nPlease try rephrasing your question or ask something else."

    def reset_conversation(self):
        """Clear conversation memory and start fresh"""
        self.memory.clear()
        self.current_ticker = None
        self.conversation_count = 0
        # Also reset the reasoning callback to clear any stale state
        self.reasoning_callback.reset()
        logger.info("Conversation memory cleared")

    def get_conversation_context(self) -> Dict:
        """Get current conversation context"""
        try:
            memory_vars = self.memory.load_memory_variables({})
        except Exception as e:
            logger.warning(f"Failed to load memory variables: {e}")
            memory_vars = {"error": str(e)}

        return {
            "current_ticker": self.current_ticker,
            "conversation_count": self.conversation_count,
            "memory": memory_vars
        }


def create_finance_qa_agent(
    api_key: Optional[str] = None,
    model: str = "claude-sonnet-4-5-20250929",
    show_reasoning: bool = True,
    project_id: Optional[str] = None,
    db_session_factory=None,
) -> FinanceQAAgent:
    """
    Factory function to create a Finance Q&A Agent

    Args:
        api_key: Anthropic API key (optional, uses env var if not provided)
        model: LLM model to use
        show_reasoning: Whether to display agent reasoning steps (default: True)
        project_id: Optional project UUID to inject into the agent prompt
        db_session_factory: Optional synchronous SQLAlchemy session factory for
            loading uploaded project documents

    Returns:
        FinanceQAAgent instance
    """
    return FinanceQAAgent(
        api_key=api_key,
        model=model,
        show_reasoning=show_reasoning,
        project_id=project_id,
        db_session_factory=db_session_factory,
    )


def interactive_session(model: str = "claude-sonnet-4-5-20250929"):
    """
    Run an interactive research session in the terminal

    Args:
        model: LLM model to use
    """
    print("=" * 80)
    print("FINANCE Q&A")
    print("=" * 80)
    print("\nAn AI-powered Q&A assistant for quick financial data, calculations,")
    print("company comparisons, and news.")
    print("\nFeatures:")
    print("  • Answer questions about financial data")
    print("  • Perform quick calculations (P/E, ROE, CAGR, etc.)")
    print("  • Explain recent news and developments")
    print("  • Compare companies side-by-side")
    print("  • Proactive suggestions on what to explore next")
    print("\nCommands:")
    print("  • Type your question to get started")
    print("  • Type 'reset' to clear conversation memory")
    print("  • Type 'context' to see conversation context")
    print("  • Type 'quit' or 'exit' to end session")
    print("=" * 80)
    print()

    try:
        assistant = create_finance_qa_agent(model=model)

        while True:
            # Get user input
            try:
                user_input = input("\nYou: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n\nGoodbye!")
                break

            if not user_input:
                continue

            # Handle commands
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("\nGoodbye!")
                break

            if user_input.lower() == 'reset':
                assistant.reset_conversation()
                print("\n[OK] Conversation memory cleared. Starting fresh!\n")
                continue

            if user_input.lower() == 'context':
                context = assistant.get_conversation_context()
                print(f"\nConversation Context:")
                print(f"   Current Ticker: {context['current_ticker'] or 'None'}")
                print(f"   Messages Exchanged: {context['conversation_count']}")
                continue

            # Get response from assistant
            print("\nAssistant:")
            response = assistant.chat(user_input)
            print(response)
            print()

    except KeyboardInterrupt:
        print("\n\nSession interrupted. Goodbye!")
    except Exception as e:
        print(f"\n\nError: {str(e)}")
        logger.error(f"Session error: {str(e)}", exc_info=True)


if __name__ == "__main__":
    # Run interactive session
    interactive_session()
