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
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_anthropic import ChatAnthropic
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.memory import ConversationBufferWindowMemory

from tools.research_assistant_tools import get_research_assistant_tools
from agents.reasoning_callback import StreamingReasoningCallback

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Common words to exclude from ticker extraction (module-level constant for efficiency)
COMMON_WORDS = {
    'THE', 'AND', 'FOR', 'ARE', 'WAS', 'BUT', 'NOT', 'YOU', 'ALL', 'CAN', 'HER',
    'ONE', 'OUR', 'OUT', 'DAY', 'GET', 'HAS', 'HIM', 'HIS', 'HOW', 'ITS', 'MAY',
    'NEW', 'NOW', 'OLD', 'SEE', 'TWO', 'WHO', 'BOY', 'DID', 'LET', 'PUT', 'SAY',
    'SHE', 'TOO', 'USE', 'WHY', 'WAY', 'YET', 'BIG', 'END', 'FAR', 'FEW', 'GOT',
    'HAD', 'HER', 'OWN', 'RAN', 'SAT', 'SAW', 'SET', 'SIX', 'TEN', 'TOP', 'TRY',
    'WIN', 'YES', 'AGO', 'AIR', 'ASK', 'BAD', 'BAG', 'BED', 'BOX', 'BUY', 'CAR',
    'CUT', 'DOG', 'EAT', 'EYE', 'FLY', 'FUN', 'GUN', 'HIT', 'HOT', 'JOB', 'KEY',
    'LAW', 'LAY', 'LEG', 'LET', 'LIE', 'LOT', 'LOW', 'MAP', 'MET', 'MIX', 'NOR',
    'ODD', 'OFF', 'OIL', 'PAY', 'PER', 'POT', 'RUN', 'SIT', 'SKY', 'SON', 'SUM',
    'TAX', 'TEA', 'THE', 'TIE', 'VOW', 'WAR', 'WET', 'WIN', 'WON', 'YET', 'ZIP',
    'TELL', 'ABOUT', 'WHAT', 'SHOW', 'GIVE', 'FIND', 'LOOK', 'HELP', 'INFO',
    'PRICE', 'STOCK', 'SHARE', 'VALUE', 'DATA', 'YEAR', 'LAST', 'NEXT', 'THIS',
    'THAT', 'WITH', 'FROM', 'HAVE', 'BEEN', 'WILL', 'WOULD', 'COULD', 'SHOULD',
    # Financial terms that could be false positives
    'CASH', 'DEBT', 'BETA', 'EBIT', 'CALL', 'PUTS', 'LONG', 'DOWN', 'RISK',
    'HIGH', 'LOSS', 'GAIN', 'SELL', 'HOLD', 'RATE', 'BOND', 'FUND', 'LOAN',
    'COST', 'FEES', 'SAFE', 'GROW', 'FALL', 'RISE', 'DROP', 'MOVE', 'BULL',
    'BEAR', 'TERM', 'FREE', 'FLOW', 'MARGIN', 'RATIO', 'GROWTH', 'INCOME',
    # Fiscal / reporting period abbreviations (common false positives)
    'FY', 'FQ', 'YTD', 'HTD', 'QTD', 'TTM', 'LTM',
    # SEC / document references
    'MD', 'MDA', 'QA', 'ITEM',
    # Common 2-letter words (Strategy 4 lowercases then uppercases, so these must be here)
    'IS', 'AN', 'OR', 'IT', 'AT', 'IN', 'ON', 'OF', 'BY', 'AS', 'BE', 'SO',
    'DO', 'UP', 'TO', 'IF', 'MY', 'NO', 'GO', 'HE', 'ME', 'WE',
}


class FinanceQAAgent:
    """Interactive Finance Q&A agent with memory and proactive suggestions"""

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-sonnet-4-5-20250929", show_reasoning: bool = True):
        """
        Initialize the Finance Q&A Agent

        Args:
            api_key: Anthropic API key (or uses ANTHROPIC_API_KEY env var)
            model: LLM model to use (default: claude-sonnet-4-5-20250929)
            show_reasoning: Whether to show agent reasoning steps (default: True)
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("Anthropic API key is required")

        self.model_name = model
        self.show_reasoning = show_reasoning

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

        # Use only research assistant core tools (quick data, calculations, news, comparisons, date context)
        # Removed DCF and Equity Analyst tools to reduce tool overload from 13 → 5 tools
        self.tools = get_research_assistant_tools()

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

        # Build the system message in parts to avoid f-string conflicts with template variables
        intro = f"""You are a Finance Q&A assistant helping investors with quick data lookups, calculations, and company comparisons.

**YOUR CAPABILITIES:**
You specialize in:
- Quick financial data lookups (revenue, margins, growth rates, cash, debt, etc.)
- Financial calculations (P/E, ROE, CAGR, valuation ratios, etc.)
- Recent news and developments
- Company-to-company comparisons
- Date/time period interpretation
- **SEC EDGAR filings** — you can fetch and analyze 10-K (annual) and 10-Q (quarterly) filings directly from SEC EDGAR using `get_sec_filings` and `analyze_sec_filing`. Use these when users ask about MD&A, risk factors, business overview, forward guidance, or anything from an official SEC filing.

**IMPORTANT SCOPE LIMITATIONS:**
- You do NOT perform DCF (intrinsic value) analysis - suggest users run the DCF Agent for that
- You do NOT perform deep industry/moat analysis - suggest users run the Equity Analyst Agent for that
- Your focus is QUICK research and data exploration, not comprehensive valuation reports

**TODAY'S DATE: {current_date}**
**CURRENT YEAR: {current_year}**

**CRITICAL: EXTERNALIZE YOUR THINKING**

You MUST externalize your reasoning using XML tags so users can follow your thought process.

**BEFORE EVERY ACTION**, wrap your reasoning in <thinking> tags:

<thinking>
I need to understand what the user is asking. They want to know about [topic].
Let me break this down:
- Key entities: [companies, metrics, time periods]
- What data do I need? [specific data points]
- Which tool should I use? [tool name and why]
</thinking>

**AFTER EVERY TOOL RESULT**, reflect using <reflection> tags:

<reflection>
The data shows [key findings]. This tells me [interpretation].
Next, I should [next step] because [reasoning].
</reflection>

**PLANNING FORMAT:**

When you need multiple steps, present your plan:

<thinking>
To answer this question, I'll follow this plan:
1. [First action] - using [tool] to get [data]
2. [Second action] - this will tell us [what]
3. [Third action] - to complete the analysis
</thinking>

**TEMPORAL AWARENESS:**
- Public companies report quarterly results 45-60 days after quarter end
- Use get_date_context tool to determine what quarterly data is currently available
- When you see "last year", "recent", "last 5 years", ALWAYS use get_date_context first

**EXAMPLE WORKFLOW:**

User: "What's Tesla's revenue growth?"

<thinking>
The user wants Tesla's revenue growth rate. I need to:
1. Get Tesla's financial data including historical revenue
2. Calculate the year-over-year growth rate
Let me start by fetching Tesla's financial metrics...
</thinking>

[Call get_quick_data tool]

<reflection>
Tesla's revenue was $96.8B in 2023 vs $81.5B in 2022.
That's a growth rate of approximately 18.8%.
I have the data needed to answer the user's question.
</reflection>

This externalized thinking helps users understand your reasoning process.

**SEC FILING WORKFLOW:**

When users ask about 10-K, 10-Q, MD&A, risk factors, guidance, or anything from an SEC filing:

<thinking>
The user wants SEC filing content. I should:
1. Call analyze_sec_filing with the ticker, filing_type ("10-K" or "10-Q"), and sections ("mda", "risk_factors", "business", "guidance", or "all")
I have this tool available and should use it immediately.
</thinking>

[Call analyze_sec_filing tool]

**AVAILABLE SEC TOOLS:**
- `get_sec_filings` — list recent 10-K/10-Q/8-K filings with dates and links
- `analyze_sec_filing` — fetch and analyze filing content (MD&A, risk factors, guidance, business overview)

**FINAL ANSWER FORMAT:**

When you have all the data needed, provide a clear, well-structured response:

1. Direct answer to the user's question (1-2 sentences)
2. Supporting data and evidence
3. Relevant context or caveats
4. [Optional] Proactive suggestion for next analysis

Use markdown formatting for readability:
- **Bold** for key metrics
- Tables for comparisons
- Bullet points for lists

Remember to be helpful, accurate with dates, and stay within your scope of quick research."""

        # Tool calling agent doesn't need explicit JSON format instructions
        # OpenAI handles function calling natively
        _chart_instructions = (
            "\n\n**CHART PLACEHOLDERS:**\n"
            "Some tool outputs include [CHART_INSTRUCTION: Place {{{{CHART:id}}}} ...].\n"
            "Follow the instruction exactly: place {{{{CHART:chart_id}}}} on its own line at the exact point where the chart is relevant.\n"
            "Do NOT reproduce ---CHART_DATA--- blocks or [CHART_INSTRUCTION] text in your response. Only use the placeholder."
        )
        system_message = intro + _chart_instructions

        # Create tool calling prompt template
        # This uses OpenAI's native function calling for reliable tool execution
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_message),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

        # Create tool calling agent (uses OpenAI's native function calling)
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
        """
        Extract ticker symbol from message using multiple strategies

        Returns the most likely ticker or None if none found
        """
        # Strategy 1: Explicit $ prefix (highest confidence - e.g., $AAPL or $aapl)
        # Case-insensitive to handle lowercase input
        dollar_match = re.search(r'\$([A-Za-z]{1,5})\b', message)
        if dollar_match:
            return dollar_match.group(1).upper()

        # Strategy 2: Parentheses pattern (e.g., "Apple (AAPL)" or "apple (aapl)")
        paren_match = re.search(r'\(([A-Za-z]{2,5})\)', message)
        if paren_match:
            return paren_match.group(1).upper()

        # Strategy 3: All caps 2-5 letters, excluding common words
        # Find all potential tickers (uppercase only for this strategy - indicates intentional ticker)
        potential_tickers = re.findall(r'\b([A-Z]{2,5})\b', message)

        # Filter out common words (using module-level COMMON_WORDS constant)
        for ticker in potential_tickers:
            if ticker not in COMMON_WORDS:
                return ticker

        # Strategy 4: Check for lowercase ticker-like patterns at the end of the message
        # E.g., "Tell me about aapl" - look for standalone word that looks like a ticker
        words = message.lower().split()
        for word in reversed(words):  # Check from end of message first
            # Remove punctuation
            clean_word = re.sub(r'[^\w]', '', word)
            if 2 <= len(clean_word) <= 5 and clean_word.isalpha() and clean_word.upper() not in COMMON_WORDS:
                return clean_word.upper()

        return None

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


def create_finance_qa_agent(api_key: Optional[str] = None, model: str = "claude-sonnet-4-5-20250929", show_reasoning: bool = True) -> FinanceQAAgent:
    """
    Factory function to create a Finance Q&A Agent

    Args:
        api_key: Anthropic API key (optional, uses env var if not provided)
        model: LLM model to use
        show_reasoning: Whether to display agent reasoning steps (default: True)

    Returns:
        FinanceQAAgent instance
    """
    return FinanceQAAgent(api_key=api_key, model=model, show_reasoning=show_reasoning)


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
    print("\nNote: For DCF valuation, use the DCF Agent (--mode dcf)")
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