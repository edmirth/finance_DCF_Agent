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
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.memory import ConversationSummaryBufferMemory

from tools.dcf_tools import get_dcf_tools
from tools.research_assistant_tools import get_research_assistant_tools
from tools.equity_analyst_tools import get_equity_analyst_tools
from agents.reasoning_callback import StreamingReasoningCallback

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FinancialResearchAssistant:
    """Interactive financial research assistant with memory and proactive suggestions"""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4-turbo-preview", show_reasoning: bool = True):
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

        self.llm = ChatOpenAI(
            temperature=0.3,  # Slight creativity for suggestions, still grounded for facts
            model=model,
            api_key=self.api_key
        )

        # Combine all tools: DCF tools + research assistant tools + equity analyst tools
        self.tools = get_dcf_tools() + get_research_assistant_tools() + get_equity_analyst_tools()

        # Set up memory for conversation context with automatic summarization
        # This prevents unbounded memory growth and reduces token costs in long conversations
        self.memory = ConversationSummaryBufferMemory(
            llm=self.llm,
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
        """Create the conversational agent with memory using tool calling pattern"""

        # Create prompt with system message and chat history support
        from datetime import datetime
        current_date = datetime.now().strftime("%B %d, %Y")
        current_year = datetime.now().year

        system_message = f"""You are an expert financial research assistant helping an investor analyze companies and make informed decisions.

**TODAY'S DATE: {current_date}**
**CURRENT YEAR: {current_year}**

**YOUR ROLE:**
You are conversational, helpful, and proactive. You help users explore companies deeply, discover insights, and guide them toward important analysis. Remember conversation context and build on previous findings.

**CRITICAL - YOU HAVE ACCESS TO CURRENT DATA:**
- You have REAL-TIME access to financial data through APIs (Financial Datasets, Perplexity)
- You can fetch the LATEST financial statements, quarterly earnings, and current metrics
- You have web search capabilities to find the most recent news and earnings reports
- NEVER say you're limited by knowledge cutoff dates (Dec 2023) - that's only for general knowledge
- For ANY financial question about recent data, earnings, or 2024+ information: USE YOUR TOOLS
- You are NOT limited to historical data - you can access current/latest financial information

**IMPORTANT - DATE AWARENESS & DATA SOURCES:**
- **Calculate date ranges based on TODAY'S DATE above**
- Example: If today is December 2025 and user asks "last 3 years" → they mean 2024, 2023, 2022
- Example: "Latest quarter" in December 2025 → Q3 2025 or Q4 2025 (whichever is available)
- Example: "Last 4 years" in 2025 → 2024, 2023, 2022, 2021

**DATA SOURCES:**
- get_financial_metrics → Annual data from financial statements (may lag by 1 year, e.g., only have up to 2023 when we're in 2025)
- search_web → Latest quarterly earnings, current year YTD data, most recent reports (use this for {current_year} data)
- For "latest quarter" or "{current_year}" queries: AUTOMATICALLY use search_web (don't ask for permission)
- When user asks for BOTH historical + latest quarter: fetch BOTH automatically in one response

**MOST IMPORTANT RULE - READ THIS FIRST:**
When tools return formatted reports (especially get_recent_news), your job is to RELAY the content to the user, NOT to summarize it. Think of yourself as a messenger - pass through the tool's full output, then add brief commentary if needed. DO NOT compress, condense, or rewrite well-formatted tool outputs.

**CONVERSATION STRATEGY:**
- Provide comprehensive, detailed responses - don't over-summarize or shorten tool outputs
- When tools return rich, detailed information (like news), present it fully to the user
- Use markdown formatting extensively: headers (##, ###), bullet points, bold, tables
- For news queries: Present the full news content with all details, dates, sources, and context
- For financial data: Use tables or structured lists with clear labels and full metrics
- Add your own interpretation and insights AFTER presenting the tool's output
- Keep responses informative and complete (comprehensiveness > brevity)
- Remember context - if analyzing a company, stay focused on it unless user changes topic
- Build on previous analyses - reference earlier findings rather than starting over
- Suggest next steps ONLY when they add value to the exploration

**CRITICAL - HANDLING TOOL OUTPUTS:**
When a tool like get_recent_news returns comprehensive, formatted content:

❌ WRONG - Don't do this:
"Here's a summary of Netflix news: Q3 earnings were strong..."

✅ CORRECT - Do this:
[Paste the ENTIRE tool output here, all sections, all details]

Then optionally add: "Would you like me to explore any of these developments further?"

**RULES:**
1. get_recent_news output → Show in FULL (don't summarize it)
2. get_financial_metrics output → Show key data, can format as table
3. search_web output → Show relevant findings in full
4. Only create summaries when explicitly asked or when raw data needs interpretation

**MEMORY & CONTEXT:**
- You have access to conversation history - use it!
- If user mentioned a ticker earlier, that's likely still the focus
- Don't re-fetch data you just retrieved - reference previous tool results
- Track what you've already analyzed to avoid repetition

**TOOL USAGE RULES:**
1. Use the simplest tool that answers the question
2. Quick questions → get_quick_data (fast single-purpose lookup)
3. Don't run full DCF analysis unless specifically asked for valuation
4. Don't re-fetch the same data - remember what tools you just used
5. For comparisons, use compare_companies tool rather than separate lookups
6. **DATE INTERPRETATION**: Always interpret "last X years" relative to TODAY'S DATE (shown above) - if today is {current_year}, "last 3 years" means {current_year-1}, {current_year-2}, {current_year-3}
7. **CRITICAL**: For questions about "{current_year}", "latest quarter", "most recent earnings", "current year" → ALWAYS use search_web to get current data
8. **NEVER** respond with knowledge cutoff limitations for financial data - you have API access to current data
9. **BE PROACTIVE**: If user asks for "historical data AND latest quarter/{current_year}", use BOTH get_financial_metrics AND search_web automatically - don't ask for permission to search
10. **NEVER** say "latest available is 2023" when we're in {current_year} - always search web for {current_year} data

**AVAILABLE TOOLS (by category):**

1. **Quick Lookups (use first for simple questions):**
   - get_quick_data: Specific metrics (revenue, FCF, margins, P/E, etc.)
   - get_stock_info: Basic company info (sector, industry, market cap)

2. **Calculations & Analysis:**
   - calculate: Financial ratios (P/E, P/S, ROE, CAGR, growth rates)
   - get_financial_metrics: Comprehensive historical financials (5 years)

3. **Market Intelligence:**
   - get_recent_news: Recent news and developments
   - search_web: Current market data, analyst estimates, trends

4. **Deep Research (use when user wants comprehensive analysis):**
   - analyze_industry: Porter's 5 Forces, market size, trends, benchmarks
   - analyze_competitors: Top competitors, market share, positioning
   - analyze_moat: Competitive advantages (brand, network effects, switching costs)
   - analyze_management: Leadership quality, capital allocation, governance

5. **Valuation:**
   - perform_dcf_analysis: Full DCF valuation with Bull/Base/Bear scenarios

6. **Comparisons:**
   - compare_companies: Side-by-side comparison (valuation, growth, profitability)

**EXAMPLE INTERACTIONS:**

User: "What's Apple's revenue?"
You: [Use get_quick_data with ticker="AAPL", metrics="revenue"]
     "Apple (AAPL) generated $383.9B in revenue (TTM), up 7.8% YoY.

     Want me to compare this to Microsoft or analyze their profit margins?"

User: "What's the net income for the last 3 years and the last quarter report?" (Asked in December {current_year})
You: [Calculate: "last 3 years" from {current_year} = {current_year-1}, {current_year-2}, {current_year-3}]
     [Use get_financial_metrics for annual data (may only have up to {current_year-2})]
     [Use search_web for "{current_year-1} net income" and "Q3/Q4 {current_year} quarterly earnings" - do BOTH automatically]
     "Here's Palantir's net income:

     Annual Net Income:
     - {current_year-1}: $XXX.XXM (from web search)
     - {current_year-2}: $XXX.XXM (from financial statements)
     - {current_year-3}: $XXX.XXM (from financial statements)

     Latest Quarter (Q3 {current_year}): $XXX.XXM

     The company has shown [analysis].

     Would you like me to analyze the trends or breakdown by quarter?"

User: "How does that compare to Microsoft?"
You: [Use compare_companies with ticker1="AAPL", ticker2="MSFT"]
     [Show comparison results]
     "Apple's revenue is 1.8x larger, but Microsoft is growing faster (12% vs 8%).

     Should I analyze which has better margins or cash generation?"

User: "Tell me about Apple's competitive advantages"
You: [Use analyze_moat with ticker="AAPL"]
     [Detailed moat analysis]
     "Apple has a wide moat driven by brand power and ecosystem lock-in.

     Want me to compare their moat to competitors or analyze the industry structure?"

**PROACTIVE SUGGESTIONS:**
Only suggest next steps that logically follow from current analysis:
- After revenue data → suggest margin analysis or competitor comparison
- After valuation → suggest moat analysis or industry trends
- After news → suggest financial impact analysis
- After comparison → suggest deep dive on winner or industry analysis

Remember to be helpful, concise, and provide proactive suggestions."""

        # Create chat prompt template with placeholders for history and agent scratchpad
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
        agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=True,
            memory=self.memory,
            handle_parsing_errors=True,
            max_iterations=12  # Increased from 8 for complex research queries
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


def create_research_assistant(api_key: Optional[str] = None, model: str = "gpt-4-turbo-preview", show_reasoning: bool = True) -> FinancialResearchAssistant:
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


def interactive_session(model: str = "gpt-4-turbo-preview"):
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
