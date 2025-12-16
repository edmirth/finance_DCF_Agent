"""
Financial Research Assistant Agent

An interactive, conversational agent for financial research that:
- Answers questions about specific financial data
- Performs quick calculations
- Explains recent news and reports
- Provides proactive suggestions on what to analyze next
- Maintains conversation context/memory
- Enables deep-dive "rabbit hole" exploration
- Compares companies and benchmarks against market
"""

import os
import logging
from typing import Optional, List, Dict
from langchain.agents import AgentExecutor, create_structured_chat_agent
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.memory import ConversationSummaryBufferMemory

from tools.research_assistant_tools import get_research_assistant_tools
from agents.reasoning_callback import StreamingReasoningCallback

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FinancialResearchAssistant:
    """Interactive financial research assistant with memory and proactive suggestions"""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-5.2", show_reasoning: bool = True):
        """
        Initialize the Financial Research Assistant

        Args:
            api_key: OpenAI API key (or uses OPENAI_API_KEY env var)
            model: LLM model to use (default: gpt-4-turbo-preview)
            show_reasoning: Whether to show agent reasoning steps (default: True)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key is required")

        self.model_name = model
        self.show_reasoning = show_reasoning

        # Initialize LLM for conversational research
        self.llm_base = ChatOpenAI(
            temperature=0.3,  # Slight creativity for suggestions, still grounded for facts
            model=model,
            api_key=self.api_key
        )

        # For models that don't support 'stop' parameter (like gpt-5.x), bind with empty stop sequences
        # This prevents the ReAct agent from adding stop sequences
        if "gpt-5" in model or "o1" in model or "o3" in model:
            self.llm = self.llm_base.bind(stop=[])
        else:
            self.llm = self.llm_base

        # Use only research assistant core tools (quick data, calculations, news, comparisons, date context)
        # Removed DCF and Equity Analyst tools to reduce tool overload from 13 → 5 tools
        self.tools = get_research_assistant_tools()

        # Set up memory for conversation context with automatic summarization
        # This prevents unbounded memory growth and reduces token costs in long conversations
        # Note: Memory uses base LLM (not bound version)
        self.memory = ConversationSummaryBufferMemory(
            llm=self.llm_base,
            memory_key="chat_history",
            return_messages=True,
            output_key="output",
            max_token_limit=2000  # Keep last 2000 tokens + summary of older messages
        )

        # Initialize reasoning callback
        self.reasoning_callback = StreamingReasoningCallback(verbose=show_reasoning)

        # Create the agent
        self.agent_executor = self._create_agent()

        # Track context
        self.current_ticker = None
        self.conversation_count = 0

        logger.info(f"Financial Research Assistant initialized with model: {model}")
        logger.info(f"Available tools: {[tool.name for tool in self.tools]}")
        logger.info(f"Reasoning display: {'enabled' if show_reasoning else 'disabled'}")

    def _create_agent(self) -> AgentExecutor:
        """Create the conversational agent with memory using structured chat pattern with planning"""

        # Create prompt with system message and chat history support
        from datetime import datetime
        current_date = datetime.now().strftime("%B %d, %Y")
        current_year = datetime.now().year

        # Build the system message in parts to avoid f-string conflicts with template variables
        intro = f"""You are an expert financial research assistant helping investors with quick data lookups, calculations, and company comparisons.

**YOUR CAPABILITIES:**
You specialize in:
- Quick financial data lookups (revenue, margins, growth rates, cash, debt, etc.)
- Financial calculations (P/E, ROE, CAGR, valuation ratios, etc.)
- Recent news and developments
- Company-to-company comparisons
- Date/time period interpretation

**IMPORTANT SCOPE LIMITATIONS:**
- You do NOT perform DCF (intrinsic value) analysis - suggest users run the DCF Agent for that
- You do NOT perform deep industry/moat analysis - suggest users run the Equity Analyst Agent for that
- Your focus is QUICK research and data exploration, not comprehensive valuation reports

**TODAY'S DATE: {current_date}**
**CURRENT YEAR: {current_year}**

**CRITICAL: ALWAYS MAKE A PLAN FIRST**

Before using ANY tools, create a step-by-step plan considering:
1. What is the user asking for?
2. What specific data do I need?
3. Are there temporal references (use get_date_context first if so)?
4. What tool sequence is needed?
5. Is this within my capabilities?

**TEMPORAL AWARENESS:**
- Public companies report quarterly results 45-60 days after quarter end
- Q4 data from {current_year} is NOT available yet
- When you see "last year", "recent", "last 5 years", ALWAYS use get_date_context first

Remember to be helpful, accurate with dates, and stay within your scope of quick research."""

        # Template portion with tool placeholders (not f-string)
        template_end = """

You have access to the following tools:

{tools}

Use a json blob to specify a tool by providing an action key (tool name) and an action_input key (tool input).

Valid "action" values: "Final Answer" or {tool_names}

Provide only ONE action per $JSON_BLOB, as shown:

```
{{
  "action": $TOOL_NAME,
  "action_input": $INPUT
}}
```

Follow this format:

Question: input question to answer
Thought: consider previous and subsequent steps
Action:
```
$JSON_BLOB
```
Observation: action result
... (repeat Thought/Action/Observation N times)
Thought: I know what to respond
Action:
```
{{
  "action": "Final Answer",
  "action_input": "Final response to human"
}}
```

IMPORTANT: Your FINAL response must ALSO use the JSON blob format above with action="Final Answer"."""

        system_message = intro + template_end

        # Create structured chat prompt template
        # This agent type is specifically designed for tools with structured JSON inputs
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_message),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            ("human", "{input}\n\n{agent_scratchpad}"),
        ])

        # Create structured chat agent (handles JSON inputs properly)
        agent = create_structured_chat_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=prompt
        )

        # Create agent executor with memory
        # Note: For models that don't support stop sequences (gpt-5.x, o1, o3),
        # we need to ensure the executor doesn't try to add them
        agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=True,
            memory=self.memory,
            handle_parsing_errors=True,
            max_iterations=15,  # Increased to allow for planning + execution
            return_intermediate_steps=True,  # Capture the plan
            max_execution_time=None
        )

        return agent_executor

    def _extract_ticker(self, message: str) -> Optional[str]:
        """
        Extract ticker symbol from message using multiple strategies

        Returns the most likely ticker or None if none found
        """
        import re

        # Strategy 1: Explicit $ prefix (highest confidence - e.g., $AAPL)
        dollar_match = re.search(r'\$([A-Z]{1,5})\b', message)
        if dollar_match:
            return dollar_match.group(1)

        # Strategy 2: Parentheses pattern (e.g., "Apple (AAPL)")
        paren_match = re.search(r'\(([A-Z]{2,5})\)', message)
        if paren_match:
            return paren_match.group(1)

        # Strategy 3: All caps 2-5 letters, excluding common words
        # More comprehensive exclusion list
        common_words = {
            'THE', 'AND', 'FOR', 'ARE', 'WAS', 'BUT', 'NOT', 'YOU', 'ALL', 'CAN', 'HER',
            'ONE', 'OUR', 'OUT', 'DAY', 'GET', 'HAS', 'HIM', 'HIS', 'HOW', 'ITS', 'MAY',
            'NEW', 'NOW', 'OLD', 'SEE', 'TWO', 'WHO', 'BOY', 'DID', 'LET', 'PUT', 'SAY',
            'SHE', 'TOO', 'USE', 'WHY', 'WAY', 'YET', 'BIG', 'END', 'FAR', 'FEW', 'GOT',
            'HAD', 'HER', 'OWN', 'RAN', 'SAT', 'SAW', 'SET', 'SIX', 'TEN', 'TOP', 'TRY',
            'WIN', 'YES', 'AGO', 'AIR', 'ASK', 'BAD', 'BAG', 'BED', 'BOX', 'BUY', 'CAR',
            'CUT', 'DOG', 'EAT', 'EYE', 'FLY', 'FUN', 'GUN', 'HIT', 'HOT', 'JOB', 'KEY',
            'LAW', 'LAY', 'LEG', 'LET', 'LIE', 'LOT', 'LOW', 'MAP', 'MET', 'MIX', 'NOR',
            'ODD', 'OFF', 'OIL', 'PAY', 'PER', 'POT', 'RUN', 'SIT', 'SKY', 'SON', 'SUM',
            'TAX', 'TEA', 'THE', 'TIE', 'VOW', 'WAR', 'WET', 'WIN', 'WON', 'YET', 'ZIP'
        }

        # Find all potential tickers
        potential_tickers = re.findall(r'\b([A-Z]{2,5})\b', message)

        # Filter out common words
        for ticker in potential_tickers:
            if ticker not in common_words:
                return ticker

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

            return result["output"]

        except Exception as e:
            logger.error(f"Error in conversation: {str(e)}")
            return f"I encountered an error: {str(e)}\n\nPlease try rephrasing your question or ask something else."

    def reset_conversation(self):
        """Clear conversation memory and start fresh"""
        self.memory.clear()
        self.current_ticker = None
        self.conversation_count = 0
        logger.info("Conversation memory cleared")

    def get_conversation_context(self) -> Dict:
        """Get current conversation context"""
        return {
            "current_ticker": self.current_ticker,
            "conversation_count": self.conversation_count,
            "memory": self.memory.load_memory_variables({})
        }


def create_research_assistant(api_key: Optional[str] = None, model: str = "gpt-5.2", show_reasoning: bool = True) -> FinancialResearchAssistant:
    """
    Factory function to create a Financial Research Assistant

    Args:
        api_key: OpenAI API key (optional, uses env var if not provided)
        model: LLM model to use
        show_reasoning: Whether to display agent reasoning steps (default: True)

    Returns:
        FinancialResearchAssistant instance
    """
    return FinancialResearchAssistant(api_key=api_key, model=model, show_reasoning=show_reasoning)


def interactive_session(model: str = "gpt-5.2"):
    """
    Run an interactive research session in the terminal

    Args:
        model: LLM model to use
    """
    print("=" * 80)
    print("FINANCIAL RESEARCH ASSISTANT")
    print("=" * 80)
    print("\nAn AI-powered research assistant for exploring companies and making")
    print("informed investment decisions.")
    print("\nFeatures:")
    print("  • Answer questions about financial data")
    print("  • Perform quick calculations")
    print("  • Explain recent news and developments")
    print("  • Compare companies")
    print("  • Deep-dive analysis with DCF valuation")
    print("  • Proactive suggestions on what to explore next")
    print("\nCommands:")
    print("  • Type your question to get started")
    print("  • Type 'reset' to clear conversation memory")
    print("  • Type 'context' to see conversation context")
    print("  • Type 'quit' or 'exit' to end session")
    print("=" * 80)
    print()

    try:
        assistant = create_research_assistant(model=model)

        while True:
            # Get user input
            try:
                user_input = input("\n💬 You: ").strip()
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
                print("\n✓ Conversation memory cleared. Starting fresh!\n")
                continue

            if user_input.lower() == 'context':
                context = assistant.get_conversation_context()
                print(f"\n📊 Conversation Context:")
                print(f"   Current Ticker: {context['current_ticker'] or 'None'}")
                print(f"   Messages Exchanged: {context['conversation_count']}")
                continue

            # Get response from assistant
            print("\n🤖 Assistant:")
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