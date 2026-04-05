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
from langchain.memory import ConversationBufferWindowMemory

from tools.research_assistant_tools import get_research_assistant_tools
from agents.reasoning_callback import StreamingReasoningCallback
from shared.ticker_utils import extract_ticker as _extract_ticker_shared

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

        # Core research tools + document reading tools (SEC filing fetch, grep, section read)
        from tools.document_tools import get_document_tools
        self.tools = get_research_assistant_tools() + get_document_tools(
            db_session_factory=db_session_factory
        )

        # Set up memory for conversation context.
        # ConversationBufferWindowMemory keeps the last k turns without any LLM
        # summarization calls — the only safe option with Anthropic chat models.
        # ConversationSummaryBufferMemory was removed because its prune() step
        # calls the Anthropic API with a completion-style PromptTemplate, which
        # results in messages=[] and a 400 "at least one message is required" error.
        self.memory = ConversationBufferWindowMemory(
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
        intro = f"""You are a Finance Q&A assistant helping investors with quick data lookups, calculations, and company comparisons.{project_hint}

**YOUR CAPABILITIES:**
You specialize in:
- Quick financial data lookups (revenue, margins, growth rates, cash, debt, etc.)
- Financial calculations (P/E, ROE, CAGR, valuation ratios, etc.)
- Recent news and developments
- Company-to-company comparisons (2 companies: `compare_companies`, 2–8 companies with a visual chart: `compare_multiple_companies`)
- Date/time period interpretation
- **SEC EDGAR filings** — you can fetch and analyze 10-K (annual) and 10-Q (quarterly) filings directly from SEC EDGAR using `get_sec_filings` and `analyze_sec_filing`. Use these when users ask about MD&A, risk factors, business overview, forward guidance, or anything from an official SEC filing.

**CHART CAPABILITIES — you CAN generate all of these:**

| User asks for... | Tool to call | Chart produced |
|---|---|---|
| Revenue/metric history for ONE company | `get_quick_data` | bar + line charts |
| Revenue breakdown by segment | `get_revenue_segments` | pie chart |
| Two-company comparison | `compare_companies` | multi-line revenue history |
| Bar chart comparing N companies (revenue, market cap, etc.) | `compare_multiple_companies(metric=revenue\|market_cap\|fcf_margin\|growth)` | bar chart |
| **Line graph comparing N companies over time** | `compare_multiple_companies(metric=revenue_history)` | **multi-line chart** |

IMPORTANT: NEVER say you lack chart tools or can only do bar charts. You have tools for line graphs,
multi-line time-series, bar charts, and pie charts. Always call the appropriate tool.

**IMPORTANT SCOPE LIMITATIONS:**
- You do NOT perform deep industry/moat analysis - suggest users run the Equity Analyst Agent for that
- Your focus is QUICK research and data exploration, not comprehensive valuation reports

**TODAY'S DATE: {current_date}**
**CURRENT YEAR: {current_year}**

**TEMPORAL AWARENESS:**
- Public companies report quarterly results 45-60 days after quarter end
- Use get_date_context tool to determine what quarterly data is currently available
- When you see "last year", "recent", "last 5 years", ALWAYS use get_date_context first

**EXAMPLE WORKFLOW:**

User: "What's Tesla's revenue growth?"

1. Call get_quick_data for TSLA historical revenue.
2. Calculate year-over-year growth and present the result with key numbers.

**SEC FILING WORKFLOW:**

When users ask about 10-K, 10-Q, MD&A, risk factors, guidance, or anything from an SEC filing:

1. Call analyze_sec_filing with the ticker, filing_type ("10-K" or "10-Q"), and sections ("mda", "risk_factors", "business", "guidance", or "all").
2. Summarise the key findings in plain prose.

[Call analyze_sec_filing tool]

**AVAILABLE SEC TOOLS:**
- `get_sec_filings` — list recent 10-K/10-Q/8-K filings with dates and links
- `analyze_sec_filing` — fetch and analyze filing content (MD&A, risk factors, guidance, business overview)

**DOCUMENT READING FLOW — for questions about filing content or uploaded documents:**

RULE: When a user asks what a document *says*, do NOT answer from memory. Always fetch and read the actual document first.
RULE: `analyze_sec_filing` gives a quick pre-structured summary. Use the document tools below when the user wants specific quotes, exact numbers, or a section that the pre-structured summary doesn't cover.

For SEC filings:

Step 1: `fetch_and_cache_filing(ticker, filing_type)` — downloads the filing, returns file path
Step 2a: `grep_filing(pattern, file_path)` — search for specific topics, keywords, or metrics
Step 2b: `read_file_section(file_path, start_marker, end_marker)` — read a named section verbatim
Step 2c: `read_full_filing(file_path)` — read entire document if under 50K characters
Step 3: `follow_reference(file_path, reference)` — chase "See Note 12" or "Item 1A" style cross-references

For uploaded project documents: `load_project_document(project_id, filename)` → then same Step 2/3 tools.

Example:
- User asks: "What does Apple's 10-K say about their AI strategy?"
- Call fetch_and_cache_filing("AAPL", "10-K") → get file path
- Call grep_filing("artificial intelligence|machine learning", file_path, context_lines=10)
- Call read_file_section(file_path, "Research and Development", "Sales and Marketing")
- Answer with real quotes and specific numbers from the filing

**FINAL ANSWER FORMAT:**

When you have all the data needed, provide a clear, well-structured response:

1. Direct answer to the user's question (1-2 sentences)
2. Supporting data and evidence
3. Relevant context or caveats
4. [Optional] Proactive suggestion for next analysis

**ABSOLUTE OUTPUT RULES — NEVER VIOLATE:**
1. NO EMOJIS — Do not use any emoji characters anywhere in your response.
2. NO ASCII BORDERS — Never output lines like `========`, `--------`. These are not markdown and render as garbage.
3. NO ALL-CAPS SECTION LABELS — Use `##` and `###` markdown headers only.
4. PROSE REQUIRED — Every section needs at least 1-2 sentences of analytical explanation, not just raw numbers.
5. CONTEXTUALIZE EVERY NUMBER — Do not write "Revenue: $96B." Write "Revenue of $96B grew 19% year-over-year, driven by..."

Use markdown for structure: **bold** for key metrics, tables for comparisons, `##` headers for sections.

Remember to be helpful, accurate with dates, and stay within your scope of quick research."""

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

        # Create agent executor with memory
        # Note: Anthropic models handle stop sequences natively,
        # no special handling needed
        agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=True,
            memory=self.memory,
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
            result = self.agent_executor.invoke(
                {"input": user_message},
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