"""
Market Analysis Agent

AI agent for analyzing market conditions, sentiment, news, and regime.
Provides comprehensive market overview to inform investment decisions.
"""

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tools.market_tools import get_market_tools
from agents.reasoning_callback import StreamingReasoningCallback
from typing import Optional


# Agent system message for tool calling pattern
MARKET_AGENT_PROMPT = """You are a professional Market Analyst providing comprehensive, detailed market analysis to help investors make informed decisions.

**YOUR ROLE:**
You are an expert market strategist who provides thorough, well-researched analysis with specific data, context, and actionable recommendations.

**CRITICAL - OUTPUT REQUIREMENTS:**
- Provide COMPREHENSIVE, DETAILED analysis - not brief summaries
- When tools return rich market data, present ALL the data with full context and interpretation
- Use extensive markdown formatting: headers (##, ###), bullet points, tables, bold
- Include specific numbers, percentages, and comparisons
- Add historical context and trend analysis
- Explain WHY things are happening, not just WHAT is happening
- Write AS MUCH as needed to fully explain the market situation

**ANALYSIS FRAMEWORK:**
1. **Market Overview** - Present all index data, breadth metrics, volatility levels with interpretation
2. **Sector Analysis** - Show detailed sector performance, rotation patterns, money flow
3. **Market Regime** - Explain current regime classification with supporting evidence
4. **Stock Screening** - Identify specific investment candidates based on fundamentals
5. **News & Catalysts** - Comprehensive coverage of market-moving developments
6. **Investment Implications** - Detailed, specific recommendations for portfolio positioning

**TOOLS AVAILABLE:**

*Market Analysis Tools:*
- get_market_overview: Comprehensive market snapshot (indices, breadth, VIX, regime)
- get_sector_rotation: Detailed sector performance and rotation analysis
- get_market_news: Latest market news and developments
- classify_market_regime: In-depth market regime classification

*Stock Screening Tools (NEW):*
- screen_stocks: Custom screening with flexible criteria (revenue, P/E, profitability, debt)
- get_value_stocks: Pre-filtered value opportunities (low P/E < 15, profitable, large cap)
- get_growth_stocks: Pre-filtered growth opportunities (strong revenue, profitable)
- get_dividend_stocks: Pre-filtered dividend-paying companies (DPS > 0, profitable)

**OUTPUT FORMATTING:**
- Start with an executive summary paragraph
- Use clear section headers (##, ###)
- Present data in tables when comparing multiple items
- Bold key insights and takeaways
- Use bullet points for lists
- Include a "Bottom Line" or "Investor Takeaways" section at the end

**INTERPRETATION GUIDELINES:**
- Explain what the data means for investors
- Compare to historical levels/averages
- Identify trends and inflection points
- Distinguish between noise and signal
- Acknowledge uncertainty but provide probabilistic analysis
- Give SPECIFIC portfolio actions (e.g., "overweight technology," "reduce duration," "add defensive hedges")

**STOCK SCREENING WORKFLOW:**
When users ask about finding stocks or investment opportunities, follow this top-down approach:

1. **Understand Market Context**: Use get_market_overview and get_sector_rotation
2. **Identify Strong Sectors**: Determine which sectors are performing well
3. **Screen for Candidates**: Use appropriate screener tool based on user preference:
   - Value investor → get_value_stocks
   - Growth investor → get_growth_stocks
   - Income investor → get_dividend_stocks
   - Custom criteria → screen_stocks
4. **Present Results**: Show screener results in table format with key metrics
5. **Suggest Next Steps**: Recommend using Finance Q&A or Equity Analyst for deep dive

**IMPORTANT - INDUSTRY NAMES:**
When screening by industry, use the EXACT industry classification from the financial data API:
- "Electric Vehicles" → Use "Auto Manufacturers" (includes Tesla, Rivian, etc.)
- "EV stocks" → Use "Auto Manufacturers"
- "Tech companies" → Use "Software - Application" or "Semiconductors"
- "Biotech" → Use "Biotechnology"
- "Pharma" → Use "Pharmaceuticals"
- "Banks" → Use "Banks - Regional" or "Banks - Diversified"
- "Oil companies" → Use "Oil & Gas E&P"

**Common Industry Names:**
Auto Manufacturers, Semiconductors, Software - Application, Software - Infrastructure,
Biotechnology, Pharmaceuticals, Banks - Regional, Oil & Gas E&P, Aerospace & Defense

**SCREENING EXAMPLES:**

User: "Find value stocks in a bull market"
You:
  1. get_market_overview → Confirm BULL market
  2. get_sector_rotation → Identify leading sectors
  3. get_value_stocks → Find undervalued opportunities
  4. Present results with context: "In this RISK_ON environment with Tech leading, here are 15 value stocks with P/E < 15..."

User: "Screen for profitable tech companies with low P/E"
You:
  1. screen_stocks with industry="Semiconductors", pe_ratio_max=20, net_income_min=0
  2. Present results in table format
  3. Recommend: "These 10 candidates look promising. Use Finance Q&A to explore NVDA, AMD, or GOOGL further."

User: "Find Electric Vehicle stocks with positive income"
You:
  1. screen_stocks with industry="Auto Manufacturers", net_income_min=0
  2. Present Tesla, Rivian, and other auto manufacturers
  3. Note: "Auto Manufacturers" industry includes traditional automakers AND EV-focused companies

**EXAMPLE GOOD OUTPUT:**
## Market Overview
The S&P 500 is trading at 4,500 (+1.2% today, +15% YTD), showing strong momentum...
[2-3 paragraphs with full context]

## Sector Rotation Analysis
Technology leads with +2.5% today, while Energy lags at -1.8%...
[Detailed table and analysis]

## Stock Screening Results
Based on the RISK_ON environment and Tech sector leadership, I screened for growth stocks...
[Present full screener results table]

## Investment Implications
Given the current RISK_ON environment and sector rotation into growth...
[Specific, detailed recommendations]

Remember: COMPREHENSIVE beats concise. Investors want thorough analysis, not brief summaries."""


class MarketAnalysisAgent:
    """
    AI agent for comprehensive market analysis

    Analyzes market conditions, sentiment, sector rotation, and news
    to provide investors with actionable market intelligence.
    """

    def __init__(self, model: str = "claude-sonnet-4-5-20250929", temperature: float = 0.1, show_reasoning: bool = True):
        """
        Initialize the Market Analysis Agent

        Args:
            model: Anthropic model to use (default: claude-sonnet-4-5-20250929)
            temperature: LLM temperature for analysis (default: 0.1 for consistent analysis)
            show_reasoning: Whether to display agent reasoning steps (default: True)
        """
        self.model = model
        self.temperature = temperature
        self.show_reasoning = show_reasoning

        # Initialize LLM
        self.llm = ChatAnthropic(
            model=model,
            temperature=temperature,
            max_retries=3,  # Retry failed API calls
            default_request_timeout=60.0,  # Request timeout in seconds
            max_tokens=8192,  # Max output tokens
        )

        # Get market analysis tools
        self.tools = get_market_tools()

        # Initialize reasoning callback
        self.reasoning_callback = StreamingReasoningCallback(verbose=show_reasoning)

        # Create chat prompt with tool calling pattern
        prompt = ChatPromptTemplate.from_messages([
            ("system", MARKET_AGENT_PROMPT),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

        # Create tool calling agent (uses OpenAI's native function calling)
        agent = create_tool_calling_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=prompt
        )

        # Create agent executor
        self.agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=10
        )

    def analyze(self, query: str) -> str:
        """
        Run market analysis based on user query

        Args:
            query: User's question or analysis request

        Returns:
            Market analysis and recommendations
        """
        try:
            # Reset callback state
            self.reasoning_callback.reset()

            # Run agent with reasoning callback
            result = self.agent_executor.invoke(
                {"input": query},
                {"callbacks": [self.reasoning_callback]}
            )
            output = result["output"]
            # Normalize Anthropic content blocks (list) to string
            if isinstance(output, list):
                output = "".join(
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in output
                )
            return output
        except Exception as e:
            return f"Error during market analysis: {str(e)}"

    def market_overview(self) -> str:
        """
        Get comprehensive market overview

        Provides quick snapshot of current market conditions including:
        - Major indices performance
        - Market breadth
        - Volatility levels
        - Market regime classification

        Returns:
            Comprehensive market overview
        """
        query = """Provide a comprehensive market overview including:
        1. Current performance of major indices (S&P 500, Nasdaq, Dow, Russell 2000)
        2. Market breadth analysis (advance/decline ratios, new highs/lows)
        3. Volatility assessment (VIX levels and interpretation)
        4. Market regime classification (BULL/BEAR/NEUTRAL, RISK_ON/RISK_OFF)
        5. Key takeaways for investors

        Be concise but thorough. Highlight what matters most for portfolio positioning.
        """
        return self.analyze(query)

    def sector_analysis(self, timeframe: str = "1M") -> str:
        """
        Analyze sector rotation and leadership

        Args:
            timeframe: Time period for analysis ('1D', '5D', '1M', '3M', 'YTD')

        Returns:
            Sector rotation analysis with recommendations
        """
        query = f"""Analyze current sector rotation patterns over the {timeframe} timeframe:
        1. Which sectors are leading and lagging?
        2. What does this rotation tell us about market positioning?
        3. Is money flowing into cyclicals or defensives?
        4. Is there a growth vs value rotation happening?
        5. What sectors should investors focus on based on current rotation?

        Provide specific, actionable sector recommendations.
        """
        return self.analyze(query)

    def market_regime_analysis(self) -> str:
        """
        Deep-dive market regime classification

        Returns:
            Detailed market regime analysis with investment implications
        """
        query = """Classify the current market regime and explain investment implications:
        1. Is this a BULL, BEAR, or NEUTRAL market?
        2. Is the market in RISK_ON or RISK_OFF mode?
        3. What signals support this classification?
        4. How confident should we be in this regime?
        5. What specific actions should investors take based on this regime?

        Be specific about portfolio positioning recommendations.
        """
        return self.analyze(query)

    def news_analysis(self, topic: Optional[str] = None) -> str:
        """
        Analyze latest market news and developments

        Args:
            topic: Optional specific topic to focus on (e.g., 'Fed', 'inflation', 'earnings')

        Returns:
            Market news analysis with implications
        """
        if topic:
            query = f"""Analyze the latest market news about {topic}:
            1. What are the key developments?
            2. How is the market reacting?
            3. What are the implications for investors?
            4. Should this change portfolio positioning?

            Be specific and actionable.
            """
        else:
            query = """Analyze the most important market news today:
            1. What are the major market-moving stories?
            2. How are markets reacting to these developments?
            3. What do investors need to know?
            4. Any actionable implications for portfolio management?

            Focus on what matters most for investors.
            """
        return self.analyze(query)

    def daily_briefing(self) -> str:
        """
        Generate comprehensive daily market briefing

        Combines market overview, sector rotation, regime analysis, and news
        into a single comprehensive briefing for investors.

        Returns:
            Daily market briefing
        """
        query = """Provide a comprehensive daily market briefing covering:

        **MARKET OVERVIEW**
        - Major indices performance
        - Market breadth and internals
        - Volatility levels

        **SECTOR ROTATION**
        - Leading and lagging sectors
        - Rotation patterns (cyclical vs defensive, growth vs value)

        **MARKET REGIME**
        - Current regime classification (BULL/BEAR/NEUTRAL)
        - Risk appetite (RISK_ON/RISK_OFF)

        **NEWS & CATALYSTS**
        - Key market-moving news
        - Economic developments

        **INVESTOR TAKEAWAYS**
        - What this means for portfolio positioning
        - Specific actionable recommendations
        - Key risks to monitor

        Format this as a professional morning briefing that an investor would read
        before markets open. Be concise but comprehensive.
        """
        return self.analyze(query)


def create_market_agent(model: str = "claude-sonnet-4-5-20250929", show_reasoning: bool = True) -> MarketAnalysisAgent:
    """
    Factory function to create Market Analysis Agent

    Args:
        model: Anthropic model to use (default: claude-sonnet-4-5-20250929)
        show_reasoning: Whether to display agent reasoning steps (default: True)

    Returns:
        Initialized MarketAnalysisAgent
    """
    return MarketAnalysisAgent(model=model, show_reasoning=show_reasoning)
